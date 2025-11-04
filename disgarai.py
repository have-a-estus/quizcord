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

# ---------------- HTML PRINCIPAL ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Quizcord Chat</title>
        <style>
            body { font-family: Arial; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
            #messages { flex: 1; overflow-y: auto; padding: 10px; background: #1e1e1e; color: #fff; }
            #input-area { display: flex; background: #111; padding: 10px; }
            input { flex: 1; padding: 10px; border: none; outline: none; border-radius: 5px; margin-right: 10px; }
            button { padding: 10px; background: #5865F2; color: white; border: none; border-radius: 5px; cursor: pointer; }
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

# ---------------- WEBSOCKET ----------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    # Entrou
    connect_message = json.dumps({
        "user": "Servidor",
        "text": f"Novo usuário entrou. Conexões ativas: {len(manager.active_connections)}"
    })
    await manager.broadcast(connect_message, sender=websocket)
    await websocket.send_text(connect_message)

    try:
        while True:
            data = await websocket.receive_text()

            # Envia de volta pro remetente (agora aparece!)
            await websocket.send_text(data)

            # Envia para todos os outros
            await manager.broadcast(data, sender=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        disconnect_message = json.dumps({
            "user": "Servidor",
            "text": f"Um usuário saiu. Conexões ativas: {len(manager.active_connections)}"
        })
        await manager.broadcast(disconnect_message)
