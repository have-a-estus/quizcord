import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

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
        for connection in self.active_connections[:]:
            if connection == sender:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# -------------------- HTML PAGE --------------------
@app.get("/", response_class=HTMLResponse)
def home():
    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Quizcord Chat</title>
        <style>
            body { margin: 0; background: #181818; font-family: Arial, sans-serif; color: #fff;}
            #messages { height: 85vh; overflow-y: auto; padding: 10px; }
            #input-area { display: flex; padding: 10px; background: #111; }
            input { flex: 1; padding: 10px; border-radius: 5px; border: none; outline: none; }
            button { margin-left: 10px; padding: 10px; background: #5865F2; color: #fff; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div id="messages"></div>
        <div id="input-area">
            <input id="msgBox" placeholder="Digite uma mensagem...">
            <button onclick="sendMsg()">Enviar</button>
        </div>

        <script>
            const ws = new WebSocket("wss://" + window.location.host + "/ws");
            const box = document.getElementById("messages");

            ws.onmessage = (event) => {
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch {
                    data = { user: "Servidor", text: event.data };
                }

                const div = document.createElement("div");
                div.textContent = data.user + ": " + data.text;
                box.appendChild(div);
                box.scrollTop = box.scrollHeight;
            };

            function sendMsg() {
                const input = document.getElementById("msgBox");
                if (input.value.trim() !== "") {
                    ws.send(JSON.stringify({ user: "Usuário", text: input.value }));
                    input.value = "";
                }
            }

            document.getElementById("msgBox").addEventListener("keydown", e => {
                if (e.key === "Enter") sendMsg();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

# -------------------- WEBSOCKET --------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    connect_data = json.dumps({
        "user": "Servidor",
        "text": f"Novo usuário entrou. Conexões: {len(manager.active_connections)}"
    })
    await websocket.send_text(connect_data)
    await manager.broadcast(connect_data, sender=websocket)

    try:
        while True:
            data = await websocket.receive_text()

            # Garante que é JSON
            try:
                parsed = json.loads(data)
            except:
                parsed = {"user":"Usuário","text":data}

            message_json = json.dumps(parsed)

            # Responde a quem enviou
            await websocket.send_text(message_json)

            # Envia para todos os outros
            await manager.broadcast(message_json, sender=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        disconnect_data = json.dumps({
            "user": "Servidor",
            "text": f"Um usuário saiu. Conexões: {len(manager.active_connections)}"
        })
        await manager.broadcast(disconnect_data)
