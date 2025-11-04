import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# ==================================================
#                 BACKEND - RENDER
# ==================================================
app = FastAPI()

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
        for connection in self.active_connections[:]:
            if connection == sender:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# --------------------------------------------------
# HTML PRINCIPAL (CHAT + NAVEGADOR)
# --------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)


def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Quizcord Chat</title>
        <style>
            body {
                font-family: Arial;
                margin: 0; padding: 0;
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            #messages {
                flex: 1;
                overflow-y: auto;
                padding: 10px;
                background: #1e1e1e;
                color: #fff;
            }
            #input-area {
                display: flex;
                background: #111;
                padding: 10px;
            }
            input {
                flex: 1;
                padding: 10px;
                border: none;
                outline: none;
                border-radius: 5px;
                margin-right: 10px;
            }
            button {
                padding: 10px;
                background: #5865F2;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>

        <div id="messages"></div>

        <div id="input-area">
            <input id="msgBox" type="text" placeholder="Digite uma mensagem..." />
            <button onclick="sendMsg()">Enviar</button>
        </div>

        <script>
            const ws = new WebSocket("wss://" + window.location.host + "/ws");

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                const div = document.createElement("div");
                div.textContent = msg.user + ": " + msg.text;
                document.getElementById("messages").appendChild(div);
            };

            function sendMsg() {
                let txt = document.getElementById("msgBox").value;
                if (txt.trim() !== "") {
                    ws.send(JSON.stringify({ user: "Usuário", text: txt }));
                    document.getElementById("msgBox").value = "";
                }
            }

            document.getElementById("msgBox").addEventListener("keydown", e => {
                if (e.key === "Enter") sendMsg();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --------------------------------------------------
# WEBSOCKET
# --------------------------------------------------
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
        print(f"Erro inesperado no WS (Servidor Render): {e}")
        manager.disconnect(websocket)

# ==================================================
#              CLIENTE LOCAL (PyQt5)
# ==================================================
"""
O código PyQt5 NÃO deve ser usado no Render. 
Para rodar localmente, crie outro arquivo, por exemplo: client.py

Exemplo:

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
import sys

RENDER_URL = "https://SEU-NOME-DO-APP.onrender.com"

class MainWindow(QMainWindow):
    def __init__(self, url):
        super().__init__()
        self.setWindowTitle("Quizcord - Cliente Global")
        self.setGeometry(100, 100, 1024, 768)
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(url))
        self.setCentralWidget(self.browser)

def start_app(url):
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(url)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    start_app(RENDER_URL)
"""

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("disgarai:app", host="0.0.0.0", port=port)
# ==================================================
# Para deploy Render: usar somente o app FastAPI
# Comando local para teste: uvicorn disgarai:app --host 0.0.0.0 --port 8000 --reload
# ==================================================
