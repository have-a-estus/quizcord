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
def home():
    html_content = """ 
    <!-- HTML completo que você enviou anteriormente -->
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

# ==================================================
# Para deploy Render: usar somente o app FastAPI
# Comando local para teste: uvicorn disgarai:app --host 0.0.0.0 --port 8000 --reload
# ==================================================
