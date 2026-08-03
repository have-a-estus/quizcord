import json
import os
import sqlite3
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "quizcord.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ─── BANCO ───
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        user_color TEXT,
        content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        file_url TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

def _get_history(room_id: str, limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, room_id, user_name, user_color, content, msg_type, file_url, timestamp
        FROM messages WHERE room_id = ? ORDER BY timestamp DESC LIMIT ?
    """, (room_id, limit))
    rows = c.fetchall()
    conn.close()
    msgs = []
    for r in rows:
        d = dict(r)
        d["user"] = {"name": d.pop("user_name"), "color": d.pop("user_color")}
        msgs.append(d)
    return list(reversed(msgs))

# ─── WEBSOCKET MANAGER ───
class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
        self.user_info: Dict[WebSocket, dict] = {}

    def connect(self, room_id: str, ws: WebSocket, user: dict):
        self.rooms.setdefault(room_id, []).append(ws)
        self.user_info[ws] = user

    def disconnect(self, room_id: str, ws: WebSocket):
        if room_id in self.rooms and ws in self.rooms[room_id]:
            self.rooms[room_id].remove(ws)
        user = self.user_info.pop(ws, {})
        if room_id in self.rooms:
            if not self.rooms[room_id]:
                del self.rooms[room_id]
        return user

    async def broadcast(self, room_id: str, msg: dict, exclude: WebSocket = None):
        if room_id not in self.rooms:
            return
        text = json.dumps(msg)
        for conn in self.rooms[room_id][:]:
            if conn == exclude:
                continue
            try:
                await conn.send_text(text)
            except:
                pass

    def get_users(self, room_id: str) -> List[dict]:
        if room_id not in self.rooms:
            return []
        return [self.user_info[ws] for ws in self.rooms[room_id] if ws in self.user_info]

manager = RoomManager()

# ─── ROTAS HTTP ───
@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/api/rooms")
def list_rooms():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM rooms ORDER BY created_at DESC")
    rooms = [dict(r) for r in c.fetchall()]
    conn.close()
    return rooms

@app.post("/api/rooms")
def create_room(name: str = Form(...)):
    rid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO rooms (id, name) VALUES (?, ?)", (rid, name))
    conn.commit()
    conn.close()
    return {"id": rid, "name": name}

@app.get("/api/rooms/{room_id}/history")
def api_history(room_id: str, limit: int = 50):
    return _get_history(room_id, limit)

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"url": f"/static/uploads/{fname}"}

# ─── WEBSOCKET ───
@app.websocket("/ws/{room_id}")
async def ws_endpoint(room_id: str, ws: WebSocket):
    # ✅ ACEITA PRIMEIRO — antes de qualquer receive_text()
    await ws.accept()

    # Handshake: primeira mensagem do cliente com nome e cor
    raw = await ws.receive_text()
    try:
        info = json.loads(raw)
    except:
        await ws.close()
        return

    user = {
        "id": str(uuid.uuid4())[:8],
        "name": info.get("name", "Anônimo")[:32],
        "color": info.get("color", "#5865F2")
    }

    manager.connect(room_id, ws, user)

    # Avisa todo mundo que entrou
    await manager.broadcast(room_id, {
        "type": "user_joined",
        "user": user,
        "users": manager.get_users(room_id)
    }, exclude=ws)

    # Envia histórico + lista de usuários para quem acabou de entrar
    await ws.send_text(json.dumps({"type": "history", "messages": _get_history(room_id, 50)}))
    await ws.send_text(json.dumps({"type": "users", "users": manager.get_users(room_id)}))

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            mtype = data.get("type", "message")

            if mtype == "typing":
                await manager.broadcast(room_id, {"type": "typing", "user": user}, exclude=ws)
                continue

            content = data.get("content", "")
            file_url = data.get("file_url")
            db_type = "image" if file_url else "text"

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO messages (room_id, user_name, user_color, content, msg_type, file_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (room_id, user["name"], user["color"], content, db_type, file_url))
            conn.commit()
            conn.close()

            await manager.broadcast(room_id, {
                "type": "message",
                "user": user,
                "content": content,
                "file_url": file_url,
                "msg_type": db_type,
                "timestamp": datetime.now().isoformat()
            })

    except WebSocketDisconnect:
        pass
    finally:
        user_left = manager.disconnect(room_id, ws)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "user": user_left,
            "users": manager.get_users(room_id)
        })