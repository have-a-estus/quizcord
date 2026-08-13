import json
import os
import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
import jwt

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "quizcord.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ─── AUTH CONFIG ───
SECRET_KEY = "quizcord-secret-key-mude-em-producao"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except:
        return None

# ─── BANCO ───
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT,
        password_hash TEXT NOT NULL,
        avatar_color TEXT DEFAULT '#5865F2',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT NOT NULL,
        user_id TEXT,
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
        SELECT id, room_id, user_id, user_name, user_color, content, msg_type, file_url, timestamp
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
        self.ws_by_user: Dict[str, WebSocket] = {}
        self.voice_users: Dict[str, Dict[str, dict]] = {}

    def connect(self, room_id: str, ws: WebSocket, user: dict):
        self.rooms.setdefault(room_id, []).append(ws)
        self.user_info[ws] = user
        self.ws_by_user[user["id"]] = ws

    def disconnect(self, room_id: str, ws: WebSocket):
        if room_id in self.rooms and ws in self.rooms[room_id]:
            self.rooms[room_id].remove(ws)
        user = self.user_info.pop(ws, {})
        self.ws_by_user.pop(user.get("id"), None)
        if room_id in self.voice_users and user.get("id") in self.voice_users.get(room_id, {}):
            del self.voice_users[room_id][user["id"]]
            if not self.voice_users[room_id]:
                del self.voice_users[room_id]
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

    async def send_to_user(self, user_id: str, msg: dict):
        ws = self.ws_by_user.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except:
                pass

    def get_users(self, room_id: str) -> List[dict]:
        if room_id not in self.rooms:
            return []
        return [self.user_info[ws] for ws in self.rooms[room_id] if ws in self.user_info]

    def get_voice_users(self, room_id: str) -> List[dict]:
        return list(self.voice_users.get(room_id, {}).values())

manager = RoomManager()

# ─── ROTAS HTTP ───
@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), display_name: str = Form(None), color: str = Form("#5865F2")):
    uid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (id, username, display_name, password_hash, avatar_color) VALUES (?, ?, ?, ?, ?)",
                  (uid, username.lower(), display_name or username, get_password_hash(password), color))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username ja existe")
    conn.close()
    token = create_access_token({"sub": uid, "username": username.lower()})
    return {"token": token, "user": {"id": uid, "username": username, "display_name": display_name or username, "color": color}}

@app.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username.lower(),))
    row = c.fetchone()
    conn.close()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuario ou senha invalidos")
    user = dict(row)
    token = create_access_token({"sub": user["id"], "username": user["username"]})
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "display_name": user["display_name"] or user["username"], "color": user["avatar_color"]}}

@app.get("/api/me")
def me(token: str):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE id = ?", (payload["sub"],))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    user = dict(row)
    return {"id": user["id"], "username": user["username"], "display_name": user["display_name"] or user["username"], "color": user["avatar_color"]}

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
    await ws.accept()

    raw = await ws.receive_text()
    try:
        data = json.loads(raw)
    except:
        await ws.close()
        return

    # Tenta autenticar por token
    user = None
    token = data.get("token")
    if token:
        payload = decode_token(token)
        if payload:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE id = ?", (payload["sub"],))
            row = c.fetchone()
            conn.close()
            if row:
                user = {
                    "id": row["id"],
                    "name": row["display_name"] or row["username"],
                    "color": row["avatar_color"],
                    "is_guest": False
                }

    # Se não autenticou, modo convidado
    if not user:
        user = {
            "id": str(uuid.uuid4())[:8],
            "name": data.get("name", "Convidado")[:32],
            "color": data.get("color", "#5865F2"),
            "is_guest": True
        }

    manager.connect(room_id, ws, user)

    await ws.send_text(json.dumps({"type": "handshake", "user_id": user["id"], "user": user}))

    await manager.broadcast(room_id, {
        "type": "user_joined",
        "user": user,
        "users": manager.get_users(room_id)
    }, exclude=ws)

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

            # ─── CANAL DE VOZ ───
            if mtype == "voice_join":
                manager.voice_users.setdefault(room_id, {})[user["id"]] = user
                await manager.broadcast(room_id, {
                    "type": "voice_user_joined",
                    "user": user,
                    "voice_users": manager.get_voice_users(room_id)
                })
                continue

            if mtype == "voice_leave":
                if room_id in manager.voice_users and user["id"] in manager.voice_users[room_id]:
                    del manager.voice_users[room_id][user["id"]]
                    if not manager.voice_users[room_id]:
                        del manager.voice_users[room_id]
                await manager.broadcast(room_id, {
                    "type": "voice_user_left",
                    "user": user,
                    "voice_users": manager.get_voice_users(room_id)
                })
                continue

            if mtype == "voice_offer":
                await manager.send_to_user(data["target"], {
                    "type": "voice_offer",
                    "from": user["id"],
                    "offer": data["offer"]
                })
                continue

            if mtype == "voice_answer":
                await manager.send_to_user(data["target"], {
                    "type": "voice_answer",
                    "from": user["id"],
                    "answer": data["answer"]
                })
                continue

            if mtype == "voice_ice":
                await manager.send_to_user(data["target"], {
                    "type": "voice_ice",
                    "from": user["id"],
                    "candidate": data["candidate"]
                })
                continue

            # ─── CHAT NORMAL ───
            content = data.get("content", "")
            file_url = data.get("file_url")
            db_type = "image" if file_url else "text"

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO messages (room_id, user_id, user_name, user_color, content, msg_type, file_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (room_id, user["id"] if not user.get("is_guest") else None, user["name"], user["color"], content, db_type, file_url))
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
        if room_id in manager.voice_users and user_left.get("id") in manager.voice_users.get(room_id, {}):
            del manager.voice_users[room_id][user_left["id"]]
            if not manager.voice_users[room_id]:
                del manager.voice_users[room_id]
            await manager.broadcast(room_id, {
                "type": "voice_user_left",
                "user": user_left,
                "voice_users": manager.get_voice_users(room_id)
            })