import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# SERVE A PASTA STATIC
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str, sender: WebSocket = None):
        for conn in self.active_connections[:]:
            if conn == sender:
                continue
            try:
                await conn.send_text(message)
            except:
                self.disconnect(conn)


manager = ConnectionManager()


# ✅ AGORA SERVE O HTML DO FIGMA
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse("static/index.html")


# ✅ WEBSOCKET
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    join_msg = json.dumps({
        "user": "Servidor",
        "text": f"Novo usuário conectado. Conexões: {len(manager.active_connections)}"
    })

    await websocket.send_text(join_msg)
    await manager.broadcast(join_msg, sender=websocket)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                parsed = json.loads(data)
            except:
                parsed = {"user": "Usuário", "text": data}

            message_json = json.dumps(parsed)

            # volta para quem enviou
            await websocket.send_text(message_json)

            # envia para os outros
            await manager.broadcast(message_json, sender=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        left_msg = json.dumps({
            "user": "Servidor",
            "text": f"Usuário saiu. Conexões: {len(manager.active_connections)}"
        })
        await manager.broadcast(left_msg)
