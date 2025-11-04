import sys
import threading
import uvicorn
import time
import json
import socket
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLineEdit, QPushButton
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl

# --- APENAS A DEF de app=FastAPI() PRECISA PERMANECER PARA QUE O RENDER RODE O BACKEND ---
app = FastAPI()

# --- CLASSE DE GERENCIAMENTO DE CONEXÕES ---
class ConnectionManager:
    """Gerencia conexões WebSocket ativas e permite o broadcast de mensagens."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str, sender: WebSocket = None):
        """Faz o broadcast de uma mensagem para todas as conexões, exceto o 'sender'."""
        for connection in self.active_connections[:]: 
            if connection == sender:
                continue
                
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# --- ROTA PRINCIPAL (HTML COM RECONEXÃO) ---
@app.get("/", response_class=HTMLResponse)
def home():
    """Retorna o HTML principal com a interface de chat em tempo real."""
    
    # O HTML foi atualizado para incluir a interface de abas (Chat e Navegador)
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Quizcord - Cliente Global</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            /* Reset básico para o corpo da aplicação */
            body { 
                margin: 0;
                padding: 0;
                font-family: ui-sans-serif, system-ui; 
                background-color: #2c2f33; /* Cor de fundo do Discord */
                display: flex;
                height: 100vh;
                overflow: hidden;
            }
            .sidebar-app {
                width: 72px; /* Largura padrão da barra de servidores do Discord */
                background-color: #202225; /* Cor da barra lateral (servidores) */
                flex-shrink: 0;
                padding-top: 10px;
            }
            .channel-list {
                width: 240px; /* Largura da lista de canais/amigos */
                background-color: #2f3136; /* Cor da coluna de canais */
                flex-shrink: 0;
                padding: 10px 0;
            }
            .main-content {
                flex-grow: 1; /* Ocupa o restante do espaço */
                background-color: #36393f; /* Cor da área de chat/conteúdo */
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            
            /* Estilos do botão de navegação */
            .nav-button {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 50px;
                height: 50px;
                margin: 0 auto 8px auto;
                border-radius: 50%;
                color: #dcddde;
                cursor: pointer;
                transition: background-color 0.2s, border-radius 0.2s;
            }
            .nav-button:hover {
                border-radius: 30%;
                background-color: #4f545c;
            }
            .nav-button.active {
                background-color: #7289da; /* Cor primária do Discord */
                border-radius: 30%;
            }
            .nav-button.active:hover {
                background-color: #7289da;
            }
            
            /* Estilos para a área de conteúdo (Chat ou Navegador) */
            #chat-container, #browser-container {
                height: 100%;
                width: 100%;
                padding: 1rem;
                box-sizing: border-box;
                display: none; /* Escondido por padrão */
            }
            
            /* Estilos do Chat */
            .chat-log { 
                flex-grow: 1;
                overflow-y: auto; 
                padding: 10px; 
                background: #36393f;
                color: #dcddde;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            .message-input-area {
                display: flex;
                padding-bottom: 10px;
            }
            .message-item { margin: 5px 0; }
            .my-message { color: #5865f2; font-weight: bold; }
            .other-message { color: #8a8e94; }
            .system-message { color: #e74c3c; font-weight: bold; }
            
            /* Estilos do Navegador */
            .browser-bar {
                display: flex;
                margin-bottom: 10px;
            }
            .browser-bar input {
                flex-grow: 1;
                padding: 8px;
                border-radius: 4px;
                border: none;
                margin-right: 5px;
                background-color: #40444b;
                color: white;
            }
            .browser-bar button {
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
                background-color: #5865f2;
                color: white;
                cursor: pointer;
            }
            .browser-iframe {
                width: 100%;
                height: calc(100% - 40px); /* Ajusta altura com base na barra de URL */
                border: none;
                background-color: white;
                border-radius: 8px;
            }

        </style>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    </head>
    <body>
        
        <!-- Barra Lateral de Aplicações (72px) -->
        <div class="sidebar-app">
            
            <!-- Botão Chat (Padrão) -->
            <div class="nav-button active" id="btn-chat" onclick="showContent('chat')">
                <i class="fas fa-comment-dots text-2xl"></i>
            </div>
            
            <!-- Seu Botão Navegador -->
            <div class="nav-button" id="btn-browser" onclick="showContent('browser')">
                <i class="fas fa-globe text-2xl"></i>
            </div>
            
            <!-- Outros botões (Amigos, Nitro, etc.) iriam aqui -->
        </div>

        <!-- Lista de Canais (240px) -->
        <div class="channel-list p-3">
            <h2 class="text-white text-lg font-semibold mb-4">Aplicações</h2>
            <div class="text-gray-400 text-sm mb-2 hover:text-white cursor-pointer transition"># Chat Global</div>
            <div class="text-gray-400 text-sm hover:text-white cursor-pointer transition"># Navegador Web</div>
        </div>

        <!-- Conteúdo Principal (Chat ou Navegador) -->
        <div class="main-content">
            
            <!-- CONTEÚDO DO CHAT (Visível por padrão) -->
            <div id="chat-container">
                <div class="flex items-center justify-between mb-4">
                    <h1 class="text-white text-2xl font-bold">Chat Global</h1>
                    <div id="status" class="text-sm font-bold text-yellow-500">Status: Conectando...</div>
                </div>

                <div id="messageLog" class="chat-log"></div>
                
                <input type="text" id="usernameInput" value="Web_User" placeholder="Seu nome..." class="w-full p-2 mb-2 rounded bg-gray-600 text-white placeholder-gray-400">
                
                <div class="message-input-area">
                    <input type="text" id="messageInput" placeholder="Digite sua mensagem..." class="p-3 rounded-l w-full bg-gray-600 text-white placeholder-gray-400 focus:outline-none" onkeyup="if(event.key === 'Enter') sendMessage()">
                    <button id="sendButton" onclick="sendMessage()" class="p-3 rounded-r bg-green-600 hover:bg-green-700 text-white font-bold transition">Enviar</button>
                </div>
            </div>
            
            <!-- CONTEÚDO DO NAVEGADOR (Escondido por padrão) -->
            <div id="browser-container">
                <div class="browser-bar">
                    <input type="text" id="urlInput" value="https://google.com" placeholder="Digite uma URL (ex: https://twitch.tv)">
                    <button onclick="navigate()">Navegar</button>
                </div>
                <iframe id="webFrame" src="about:blank" class="browser-iframe"></iframe>
            </div>
            
        </div>

        <script>
            // Variável Global para armazenar a URL do Servidor Render. 
            // O host real será determinado pelo navegador do cliente (PyQtWebEngine).
            // O Render usará o WSS:// (seguro)
            const ws_protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws_url = `${ws_protocol}//${window.location.host}/ws`;

            const statusDiv = document.getElementById('status');
            const logDiv = document.getElementById('messageLog');
            const input = document.getElementById('messageInput');
            const usernameInput = document.getElementById('usernameInput');
            
            let socket;
            let reconnectAttempts = 0;
            const MAX_RECONNECT_ATTEMPTS = 10;
            const RECONNECT_INTERVAL_MS = 3000;
            
            // --- LÓGICA DE NAVEGAÇÃO ENTRE ABAS ---
            function showContent(tabName) {
                const chatContainer = document.getElementById('chat-container');
                const browserContainer = document.getElementById('browser-container');
                
                document.getElementById('btn-chat').classList.remove('active');
                document.getElementById('btn-browser').classList.remove('active');

                if (tabName === 'chat') {
                    chatContainer.style.display = 'flex';
                    browserContainer.style.display = 'none';
                    document.getElementById('btn-chat').classList.add('active');
                } else if (tabName === 'browser') {
                    chatContainer.style.display = 'none';
                    browserContainer.style.display = 'flex';
                    document.getElementById('btn-browser').classList.add('active');
                    // Garante que o iframe não esteja vazio ao trocar
                    const urlInput = document.getElementById('urlInput');
                    if (document.getElementById('webFrame').src === 'about:blank') {
                        navigate();
                    }
                }
            }

            function navigate() {
                const urlInput = document.getElementById('urlInput').value;
                const iframe = document.getElementById('webFrame');
                
                // Adiciona https:// se não houver protocolo
                let fullUrl = urlInput;
                if (!fullUrl.match(/^(http|https):\/\//)) {
                    fullUrl = 'https://' + fullUrl;
                }
                iframe.src = fullUrl;
                console.log('Navegando para:', fullUrl);
            }

            // Garante que o Chat é a aba inicial
            showContent('chat');
            
            // --- FUNÇÃO DE CONEXÃO PRINCIPAL (CHAT) ---
            function connectWebSocket() {
                if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
                    return;
                }
                
                statusDiv.textContent = `Status: Tentativa ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS}: Conectando...`;
                statusDiv.classList.remove('text-green-500', 'text-red-500');
                statusDiv.classList.add('text-yellow-500');

                try {
                    socket = new WebSocket(ws_url);
                } catch (error) {
                    handleConnectionError(error);
                    return;
                }

                socket.onopen = function(e) {
                    statusDiv.textContent = "Status: CONECTADO.";
                    statusDiv.classList.remove('text-yellow-500', 'text-red-500');
                    statusDiv.classList.add('text-green-500');
                    reconnectAttempts = 0;
                };

                socket.onmessage = function(event) {
                    const messageData = JSON.parse(event.data);
                    
                    let userClass = 'other-message';
                    if (messageData.user === "Servidor") {
                        userClass = 'system-message'; 
                    } else if (messageData.user === usernameInput.value) {
                         userClass = 'my-message';
                    }
                    
                    appendLog(messageData.user, messageData.text, userClass);
                };

                socket.onclose = function(event) {
                    handleConnectionError("Conexão encerrada. Tentando reconectar...");
                };

                socket.onerror = function(error) {
                    handleConnectionError("ERRO na conexão.");
                };
            }
            
            // --- FUNÇÃO DE TRATAMENTO DE ERRO COM RECONEXÃO ---
            function handleConnectionError(message) {
                statusDiv.textContent = "Status: DESCONECTADO.";
                statusDiv.classList.remove('text-green-500', 'text-yellow-500');
                statusDiv.classList.add('text-red-500');
                
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    setTimeout(() => {
                        connectWebSocket();
                    }, RECONNECT_INTERVAL_MS);
                } else {
                    appendLog("Sistema", "Máximo de tentativas de reconexão atingido.", 'system-message');
                }
            }

            // --- FUNÇÃO ENVIAR MENSAGEM ---
            function sendMessage() {
                const message = input.value;
                const user = usernameInput.value || "Anônimo";
                
                if (message.trim() && socket && socket.readyState === WebSocket.OPEN) {
                    const dataToSend = {
                        user: user,
                        text: message.trim()
                    };
                    
                    socket.send(JSON.stringify(dataToSend));
                    
                    // Adiciona a mensagem localmente para o remetente
                    appendLog(user, message.trim(), 'my-message'); 
                    input.value = ''; 
                } else if (message.trim()) {
                    appendLog("Sistema", "Não conectado. Aguarde a reconexão.", 'system-message');
                }
            }
            
            // --- FUNÇÃO PARA ADICIONAR LOG ---
            function appendLog(user, text, className) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message-item text-sm ${className}`;
                messageDiv.innerHTML = `<span class="font-semibold">${user}:</span> ${text}`;
                
                logDiv.appendChild(messageDiv);
                logDiv.scrollTop = logDiv.scrollHeight;
            }
            
            // Inicia a primeira tentativa de conexão
            connectWebSocket();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- ENDPOINT DE WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # O Render/Gunicorn irá iniciar este código no servidor global
    await manager.connect(websocket)
    
    connect_message = json.dumps({
        "user": "Servidor", 
        "text": f"Novo usuário entrou. Conexões ativas: {len(manager.active_connections)}"
    })
    await manager.broadcast(connect_message, sender=websocket)
    
    try:
        while True:
            data = await websocket.receive_text() 
            await manager.broadcast(data, sender=websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        disconnect_message = json.dumps({
            "user": "Servidor", 
            "text": f"Um usuário saiu. Conexões ativas: {len(manager.active_connections)}"
        })
        await manager.broadcast(disconnect_message) 
        
    except Exception as e:
        # AQUI É O SERVIDOR GLOBAL
        print(f"Erro inesperado no WS (Servidor Render): {e}")
        manager.disconnect(websocket)

# ************************************************
# *** CÓDIGO PYQT: SOMENTE CLIENTE (Desktop) ***
# ************************************************

# Variável que você deve alterar manualmente após o deploy no Render
# EXEMPLO: 'https://quizcord-global.onrender.com'
RENDER_URL = "https://SEU-NOME-DO-APP.onrender.com" 

# --- CLASSE DA JANELA PYQT ---
class MainWindow(QMainWindow):
    """Janela principal que hospeda o QWebEngineView."""
    def __init__(self, url):
        super().__init__()
        self.setWindowTitle("Quizcord - Cliente Global")
        self.setGeometry(100, 100, 1024, 768) 
        
        # O cliente agora se conecta à URL externa (do Render)
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(url))
        self.setCentralWidget(self.browser)

# --- FUNÇÃO PARA INICIAR O APP PYQT ---
def start_app(url):
    """Inicializa a aplicação PyQt."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        
    window = MainWindow(url)
    window.show()
    sys.exit(app.exec_())

# --- BLOCO PRINCIPAL (CLIENTE) ---
if __name__ == "__main__":
    
    # 1. Tente usar a URL de produção (Render)
    prod_url = RENDER_URL
    
    # 2. Se estiver testando localmente, use localhost
    local_url = "http://127.0.0.1:8000"
    
    # Se você não alterou o RENDER_URL, ele tentará usar o localhost.
    if RENDER_URL == "https://SEU-NOME-DO-APP.onrender.com":
        final_url = local_url
        print("AVISO: Usando URL local. Lembre-se de alterar 'RENDER_URL' no código para o deploy final.")
    else:
        final_url = prod_url
        
    print(f"ATENÇÃO: Este código DEIXOU de ser um servidor. Tentando acessar: {final_url}")
    
    # Se você for testar o EXE localmente, precisará rodar o servidor FastAPI manualmente
    # Ex: uvicorn disgarai:app --host 0.0.0.0 --port 8000
    
    # Inicia o cliente PyQt conectando à URL (Render ou Local)
    start_app(final_url)
