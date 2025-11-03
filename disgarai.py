import sys
import threading
import uvicorn
import time
import json
import socket
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl

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
    # O conteúdo HTML permanece o mesmo, com a lógica de reconexão do JavaScript
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Quizcord - Dos Brabos</title>
        <style>
            /* ... (Seus estilos) ... */
            body { 
                font-family: 'Inter', sans-serif; 
                text-align: center; 
                padding-top: 50px; 
                background-color: #ecf0f1; 
                margin: 0;
            }
            .container { 
                background: white; 
                padding: 30px; 
                border-radius: 12px; 
                box-shadow: 0 8px 16px rgba(0,0,0,0.2); 
                display: inline-block; 
                max-width: 90%;
                width: 600px;
                text-align: left;
            }
            h1 { color: #2980b9; margin-bottom: 20px; text-align: center; }
            .status { margin-bottom: 20px; font-weight: bold; text-align: center; }
            .log { height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; background: #f9f9f9; border-radius: 4px; font-size: 0.9em; margin-bottom: 15px;}
            #messageInput { width: 80%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            #sendButton { width: 18%; padding: 10px; background-color: #2ecc71; color: white; border: none; border-radius: 4px; cursor: pointer; float: right; }
            #sendButton:hover { background-color: #27ae60; }
            .message-item { margin: 5px 0; padding: 5px; border-bottom: 1px dotted #eee; }
            
            .my-message { color: #2980b9; font-weight: bold; }
            .my-message-text { color: #2980b9; }
            .other-message { color: #34495e; }
            .error-message { color: #e74c3c; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Chat Global (Discord Lite)</h1>
            <div id="status" class="status" style="color: #e74c3c;">Status: Conectando...</div>
            
            <div id="messageLog" class="log"></div>
            
            <input type="text" id="usernameInput" value="Usuário_Web" placeholder="Seu nome..." style="width: 100%; margin-bottom: 10px;">
            <input type="text" id="messageInput" placeholder="Digite sua mensagem..." onkeyup="if(event.key === 'Enter') sendMessage()">
            <button id="sendButton" onclick="sendMessage()">Enviar</button>
            <div style="clear: both;"></div>
        </div>

        <script>
            // --- VARIÁVEIS DE CONEXÃO E RECONEXÃO ---
            const statusDiv = document.getElementById('status');
            const logDiv = document.getElementById('messageLog');
            const input = document.getElementById('messageInput');
            const usernameInput = document.getElementById('usernameInput');
            
            // --- CORREÇÃO CRUCIAL AQUI ---
            // Detecta se a página foi carregada via HTTPS (Ngrok) ou HTTP (Localhost)
            const isSecure = window.location.protocol === 'https:';
            const ws_protocol = isSecure ? 'wss:' : 'ws:';
            const ws_url = `${ws_protocol}//${window.location.host}/ws`;

            let socket;
            let reconnectAttempts = 0;
            const MAX_RECONNECT_ATTEMPTS = 10;
            const RECONNECT_INTERVAL_MS = 3000;

            // --- FUNÇÃO DE CONEXÃO PRINCIPAL ---
            function connectWebSocket() {
                if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
                    return; // Já conectado ou conectando
                }
                
                statusDiv.textContent = `Status: Tentativa ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS}: Conectando...`;
                statusDiv.style.color = "#f39c12"; // Amarelo para indicar tentativa

                try {
                    // O Ngrok lida com a conexão WSS -> WS
                    socket = new WebSocket(ws_url);
                } catch (error) {
                    handleConnectionError(error);
                    return;
                }

                socket.onopen = function(e) {
                    statusDiv.textContent = "Status: CONECTADO. Digite para conversar.";
                    statusDiv.style.color = "#2ecc71";
                    reconnectAttempts = 0; // Resetar após sucesso
                };

                socket.onmessage = function(event) {
                    const messageData = JSON.parse(event.data);
                    
                    let userClass = 'other-message';
                    let textClass = 'other-message';
                    
                    if (messageData.user === "Servidor") {
                        userClass = 'my-message'; 
                        textClass = 'my-message-text';
                    }
                    
                    appendLog(messageData.user, messageData.text, userClass, textClass);
                };

                socket.onclose = function(event) {
                    if (event.code === 1006 || reconnectAttempts > 0) {
                        handleConnectionError("Conexão encerrada. Tentando reconectar...");
                    } else {
                        statusDiv.textContent = "Status: DESCONECTADO.";
                        statusDiv.style.color = "#e74c3c";
                    }
                };

                socket.onerror = function(error) {
                    handleConnectionError("ERRO na conexão.");
                };
            }
            
            // --- FUNÇÃO DE TRATAMENTO DE ERRO COM RECONEXÃO ---
            function handleConnectionError(message) {
                statusDiv.textContent = "Status: DESCONECTADO.";
                statusDiv.style.color = "#e74c3c";
                // Corrigido para mostrar a mensagem de erro do servidor no log, não o 'SecurityError' do console
                if (typeof message === 'object' && message.type === 'error') {
                     appendLog("Servidor", "Erro de segurança ao iniciar o WebSocket.", 'error-message', 'error-message');
                } else {
                    appendLog("Servidor", message, 'error-message', 'error-message');
                }
                
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    setTimeout(() => {
                        connectWebSocket();
                    }, RECONNECT_INTERVAL_MS);
                } else {
                    appendLog("Servidor", "Máximo de tentativas de reconexão atingido.", 'error-message', 'error-message');
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
                    appendLog(user, message.trim(), 'my-message', 'my-message-text'); 
                    
                    input.value = ''; 
                } else if (message.trim()) {
                    appendLog("Sistema", "Não conectado. Aguarde a reconexão.", 'error-message', 'error-message');
                }
            }
            
            // --- FUNÇÃO PARA ADICIONAR LOG ---
            function appendLog(user, text, userClassName, textClassName) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message-item';
                
                const userSpan = document.createElement('span');
                userSpan.textContent = user + ": ";
                userSpan.className = userClassName;
                
                const textSpan = document.createElement('span');
                textSpan.textContent = text;
                textSpan.className = textClassName; 
                
                messageDiv.appendChild(userSpan);
                messageDiv.appendChild(textSpan);
                
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
        print(f"Erro inesperado no WS: {e}")
        manager.disconnect(websocket)


# --- FUNÇÃO PARA INICIAR O SERVIDOR (Simples) ---
def start_server():
    """Inicia o servidor Uvicorn para ouvir em todas as interfaces de rede (0.0.0.0)."""
    # Host: 0.0.0.0 permite conexão de outros dispositivos na mesma rede.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning") 

# --- CLASSE DA JANELA PYQT ---
class MainWindow(QMainWindow):
    """Janela principal que hospeda o QWebEngineView."""
    def __init__(self, url):
        super().__init__()
        self.setWindowTitle("Quizcord")
        self.setGeometry(100, 100, 1024, 768) 
        
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

# --- FUNÇÃO DE VERIFICAÇÃO DE PORTA ---
def is_port_open(host, port):
    """Verifica se a porta está ativa usando um socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5) # Define um timeout curto para a tentativa
    try:
        # Tentar conectar a 127.0.0.1 em vez de 0.0.0.0, pois 0.0.0.0 não é um IP de conexão válido
        s.connect(("127.0.0.1", port)) 
        s.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False

# --- BLOCO PRINCIPAL ---
if __name__ == "__main__":
    
    # 1. Inicia o servidor FastAPI em outra thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # MUDANÇA ANTERIOR: O host 0.0.0.0 deve ser usado para que o Uvicorn ESCUTE em todas as interfaces.
    # Mas o cliente PyQt deve se conectar a 127.0.0.1 para que o sistema operacional saiba onde procurar.
    # Vamos manter a variável de host para a URL final como 127.0.0.1 (IP real de loopback).
    fastapi_host = "127.0.0.1" 
    fastapi_port = 8000
    fastapi_url = f"http://{fastapi_host}:{fastapi_port}" 
    
    # 2. Espera ativa pelo servidor (máximo de 10 segundos)
    print(f"Aguardando o servidor em http://{fastapi_host}:{fastapi_port} iniciar...")
    max_wait = 10
    start_time = time.time()
    server_ready = False
    
    while time.time() - start_time < max_wait:
        # A verificação de porta usa 127.0.0.1 agora.
        if is_port_open("127.0.0.1", fastapi_port): 
            server_ready = True
            break
        time.sleep(0.5) # Espera 500ms antes de tentar novamente

    if not server_ready:
        print(f"\n--- ERRO ---")
        print(f"O servidor Uvicorn não iniciou na porta {fastapi_port} após {max_wait} segundos.")
        print("Verifique se a porta 8000 não está sendo usada por outro programa.")
        sys.exit(1)
        
    print(f"\n--- SERVIDOR ATIVO ---")
    print(f"Iniciando Cliente PyQt. Acessando: {fastapi_url}")
    
    # 3. Inicia o cliente PyQt
    start_app(fastapi_url)
