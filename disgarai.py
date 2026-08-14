import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
import jwt

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB = os.path.join(BASE_DIR, "quizcord_users.db")
CIRCLES_DB = os.path.join(BASE_DIR, "quizcord_circles.db")
MESSAGES_DB = os.path.join(BASE_DIR, "quizcord_messages.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
DOWNLOAD_DIR = os.path.join(STATIC_DIR, "download")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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

def get_db(path: str):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_users_db():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT,
        password_hash TEXT NOT NULL,
        avatar_color TEXT DEFAULT '#ff7b72',
        status TEXT DEFAULT 'offline',
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS friendships (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        friend_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, friend_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS direct_chats (
        id TEXT PRIMARY KEY,
        user1_id TEXT NOT NULL,
        user2_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user1_id, user2_id)
    )""")
    conn.commit()
    conn.close()

def init_circles_db():
    conn = sqlite3.connect(CIRCLES_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS circles (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        color TEXT DEFAULT '#a78bfa',
        icon_url TEXT,
        invite_code TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS circle_members (
        id TEXT PRIMARY KEY,
        circle_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(circle_id, user_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS topics (
        id TEXT PRIMARY KEY,
        circle_id TEXT NOT NULL,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'text',
        position INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

def init_messages_db():
    conn = sqlite3.connect(MESSAGES_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT NOT NULL,
        user_id TEXT,
        user_name TEXT NOT NULL,
        user_color TEXT,
        content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        file_url TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS unread (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        room_id TEXT NOT NULL,
        count INTEGER DEFAULT 1,
        last_message_id INTEGER,
        UNIQUE(user_id, room_id)
    )""")
    conn.commit()
    conn.close()

init_users_db()
init_circles_db()
init_messages_db()

def _get_history(room_id: str, limit: int = 50):
    conn = get_db(MESSAGES_DB)
    c = conn.cursor()
    c.execute("SELECT id, room_id, user_id, user_name, user_color, content, msg_type, file_url, timestamp FROM messages WHERE room_id = ? ORDER BY timestamp DESC LIMIT ?", (room_id, limit))
    rows = c.fetchall()
    conn.close()
    msgs = []
    for r in rows:
        d = dict(r)
        d["user"] = {"name": d.pop("user_name"), "color": d.pop("user_color")}
        msgs.append(d)
    return list(reversed(msgs))

class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.user_info = {}
        self.ws_by_user = {}
        self.voice_users = {}

    def connect(self, room_id, ws, user):
        self.rooms.setdefault(room_id, []).append(ws)
        self.user_info[ws] = user
        self.ws_by_user[user["id"]] = ws

    def disconnect(self, room_id, ws):
        if room_id in self.rooms and ws in self.rooms[room_id]:
            self.rooms[room_id].remove(ws)
        user = self.user_info.pop(ws, {})
        self.ws_by_user.pop(user.get("id"), None)
        if room_id in self.voice_users and user.get("id") in self.voice_users.get(room_id, {}):
            del self.voice_users[room_id][user["id"]]
            if not self.voice_users[room_id]:
                del self.voice_users[room_id]
        if room_id in self.rooms and not self.rooms[room_id]:
            del self.rooms[room_id]
        return user

    async def broadcast(self, room_id, msg, exclude=None):
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

    async def send_to_user(self, user_id, msg):
        ws = self.ws_by_user.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except:
                pass

    def get_users(self, room_id):
        if room_id not in self.rooms:
            return []
        return [self.user_info[ws] for ws in self.rooms[room_id] if ws in self.user_info]

    def get_voice_users(self, room_id):
        return list(self.voice_users.get(room_id, {}).values())

class NotifManager:
    def __init__(self):
        self.conns = {}

    def connect(self, user_id, ws):
        self.conns[user_id] = ws

    def disconnect(self, user_id):
        self.conns.pop(user_id, None)

    async def send(self, user_id, msg):
        ws = self.conns.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except:
                pass

manager = RoomManager()
notif_manager = NotifManager()

def get_token_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return ""

def require_user(request: Request):
    token = get_token_from_request(request)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido")
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE id = ?", (payload["sub"],))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return dict(row)

@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/api/version")
def get_version():
    return {
        "version": "1.1.1-beta",
        "download_url": "https://luminachat.duckdns.org/static/download/LuminaChat.zip",
        "release_notes": "Cosmic Aero theme, frameless client, alpaca loading animation"
    }

@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), display_name: str = Form(None), color: str = Form("#ff7b72")):
    uid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(USERS_DB)
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
    conn = get_db(USERS_DB)
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
def me(request: Request):
    return require_user(request)

@app.get("/api/users/search")
def search_users(request: Request, q: str = ""):
    require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE username LIKE ? OR display_name LIKE ? LIMIT 20",
        (f"%{q}%", f"%{q}%"))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/friends")
def list_friends(request: Request):
    user = require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT f.id, f.friend_id as fid, f.status, u.display_name, u.username, u.avatar_color FROM friendships f JOIN users u ON u.id = f.friend_id WHERE f.user_id = ? AND f.status = 'accepted'", (user["id"],))
    sent = [dict(r) for r in c.fetchall()]
    c.execute("SELECT f.id, f.user_id as fid, f.status, u.display_name, u.username, u.avatar_color FROM friendships f JOIN users u ON u.id = f.user_id WHERE f.friend_id = ? AND f.status = 'accepted'", (user["id"],))
    received = [dict(r) for r in c.fetchall()]
    c.execute("SELECT f.id, f.friend_id as fid, f.status, u.display_name, u.username, u.avatar_color FROM friendships f JOIN users u ON u.id = f.friend_id WHERE f.user_id = ? AND f.status = 'pending'", (user["id"],))
    pending_sent = [dict(r) for r in c.fetchall()]
    c.execute("SELECT f.id, f.user_id as fid, f.status, u.display_name, u.username, u.avatar_color FROM friendships f JOIN users u ON u.id = f.user_id WHERE f.friend_id = ? AND f.status = 'pending'", (user["id"],))
    pending_received = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"friends": sent + received, "pending_sent": pending_sent, "pending_received": pending_received}

@app.post("/api/friends/request")
async def add_friend(request: Request, username: str = Form(...)):
    user = require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE username = ?", (username.lower(),))
    target = c.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    tid = target["id"]
    if tid == user["id"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Nao pode adicionar voce mesmo")
    c.execute("SELECT * FROM friendships WHERE user_id = ? AND friend_id = ?", (user["id"], tid))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Solicitacao ja existe")
    c.execute("SELECT * FROM friendships WHERE user_id = ? AND friend_id = ?", (tid, user["id"]))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Solicitacao ja existe")
    fid = str(uuid.uuid4())[:8]
    c.execute("INSERT INTO friendships (id, user_id, friend_id, status) VALUES (?, ?, ?, 'pending')", (fid, user["id"], tid))
    conn.commit()
    conn.close()
    await notif_manager.send(tid, {
        "type": "friend_request",
        "from": {"id": user["id"], "username": user["username"], "display_name": user.get("display_name") or user["username"], "avatar_color": user.get("avatar_color", "#ff7b72")}
    })
    return {"ok": True}

@app.post("/api/friends/accept")
async def accept_friend(request: Request, friend_id: str = Form(...)):
    user = require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("UPDATE friendships SET status = 'accepted' WHERE user_id = ? AND friend_id = ? AND status = 'pending'", (friend_id, user["id"]))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Solicitacao nao encontrada")
    dm_id = str(uuid.uuid4())[:8]
    u1, u2 = sorted([user["id"], friend_id])
    c.execute("INSERT OR IGNORE INTO direct_chats (id, user1_id, user2_id) VALUES (?, ?, ?)", (dm_id, u1, u2))
    conn.commit()
    conn.close()
    await notif_manager.send(friend_id, {
        "type": "friend_accepted",
        "by": {"id": user["id"], "username": user["username"], "display_name": user.get("display_name") or user["username"], "avatar_color": user.get("avatar_color", "#ff7b72")}
    })
    return {"ok": True}

@app.post("/api/friends/reject")
def reject_friend(request: Request, friend_id: str = Form(...)):
    user = require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("DELETE FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)",
        (user["id"], friend_id, friend_id, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/circles")
def list_circles(request: Request):
    user = require_user(request)
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("SELECT c.* FROM circles c JOIN circle_members m ON m.circle_id = c.id WHERE m.user_id = ? ORDER BY c.created_at DESC", (user["id"],))
    circles = [dict(r) for r in c.fetchall()]
    conn.close()
    return circles

@app.post("/api/circles")
def create_circle(request: Request, name: str = Form(...), color: str = Form("#a78bfa")):
    user = require_user(request)
    cid = str(uuid.uuid4())[:8]
    invite = str(uuid.uuid4())[:12]
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("INSERT INTO circles (id, name, owner_id, color, invite_code) VALUES (?, ?, ?, ?, ?)", (cid, name, user["id"], color, invite))
    mid = str(uuid.uuid4())[:8]
    c.execute("INSERT INTO circle_members (id, circle_id, user_id, role) VALUES (?, ?, ?, 'owner')", (mid, cid, user["id"]))
    tid = str(uuid.uuid4())[:8]
    c.execute("INSERT INTO topics (id, circle_id, name, type, position) VALUES (?, ?, ?, 'text', 0)", (tid, cid, "geral"))
    conn.commit()
    conn.close()
    return {"id": cid, "name": name, "color": color, "invite_code": invite}

@app.post("/api/circles/join")
def join_circle(request: Request, code: str = Form(...)):
    user = require_user(request)
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM circles WHERE invite_code = ?", (code,))
    circle = c.fetchone()
    if not circle:
        conn.close()
        raise HTTPException(status_code=404, detail="Codigo invalido")
    c.execute("SELECT * FROM circle_members WHERE circle_id = ? AND user_id = ?", (circle["id"], user["id"]))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Ja esta no circulo")
    mid = str(uuid.uuid4())[:8]
    c.execute("INSERT INTO circle_members (id, circle_id, user_id, role) VALUES (?, ?, ?, 'member')", (mid, circle["id"], user["id"]))
    conn.commit()
    conn.close()
    return {"id": circle["id"], "name": circle["name"]}

@app.get("/api/circles/by-invite/{code}")
def get_circle_by_invite(code: str):
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("SELECT id, name, color, icon_url, invite_code FROM circles WHERE invite_code = ?", (code,))
    circle = c.fetchone()
    conn.close()
    if not circle:
        raise HTTPException(status_code=404, detail="Codigo invalido")
    return dict(circle)


@app.get("/api/circles/{circle_id}")
def get_circle(circle_id: str, request: Request):
    user = require_user(request)
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM circles WHERE id = ?", (circle_id,))
    circle = c.fetchone()
    if not circle:
        conn.close()
        raise HTTPException(status_code=404, detail="Circulo nao encontrado")
    c.execute("SELECT * FROM circle_members WHERE circle_id = ? AND user_id = ?", (circle_id, user["id"]))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Nao e membro")
    c.execute("SELECT user_id, role FROM circle_members WHERE circle_id = ?", (circle_id,))
    member_rows = c.fetchall()
    c.execute("SELECT * FROM topics WHERE circle_id = ? ORDER BY position", (circle_id,))
    topics = [dict(r) for r in c.fetchall()]
    conn.close()
    user_ids = [m["user_id"] for m in member_rows]
    members = []
    if user_ids:
        conn2 = get_db(USERS_DB)
        c2 = conn2.cursor()
        placeholders = ','.join('?' * len(user_ids))
        c2.execute(f"SELECT id, username, display_name, avatar_color FROM users WHERE id IN ({placeholders})", user_ids)
        user_map = {u["id"]: dict(u) for u in c2.fetchall()}
        conn2.close()
        for m in member_rows:
            u = user_map.get(m["user_id"], {})
            members.append({
                "id": m["user_id"],
                "username": u.get("username", ""),
                "display_name": u.get("display_name", ""),
                "avatar_color": u.get("avatar_color", "#888"),
                "role": m["role"]
            })
    return {"circle": dict(circle), "members": members, "topics": topics}

@app.post("/api/circles/{circle_id}/topics")
def create_topic(circle_id: str, request: Request, name: str = Form(...), type: str = Form("text")):
    user = require_user(request)
    conn = get_db(CIRCLES_DB)
    c = conn.cursor()
    c.execute("SELECT role FROM circle_members WHERE circle_id = ? AND user_id = ?", (circle_id, user["id"]))
    row = c.fetchone()
    if not row or row["role"] not in ("owner", "mod"):
        conn.close()
        raise HTTPException(status_code=403, detail="Sem permissao")
    tid = str(uuid.uuid4())[:8]
    c.execute("SELECT MAX(position) as mp FROM topics WHERE circle_id = ?", (circle_id,))
    pos = (c.fetchone()["mp"] or 0) + 1
    c.execute("INSERT INTO topics (id, circle_id, name, type, position) VALUES (?, ?, ?, ?, ?)", (tid, circle_id, name, type, pos))
    conn.commit()
    conn.close()
    return {"id": tid, "name": name, "type": type}

@app.get("/api/dm-chats")
def list_dm_chats(request: Request):
    user = require_user(request)
    conn = get_db(USERS_DB)
    c = conn.cursor()
    c.execute("""SELECT d.id, d.user1_id, d.user2_id,
        CASE WHEN d.user1_id = ? THEN d.user2_id ELSE d.user1_id END as peer_id,
        u.display_name, u.username, u.avatar_color
        FROM direct_chats d
        JOIN users u ON u.id = CASE WHEN d.user1_id = ? THEN d.user2_id ELSE d.user1_id END
        WHERE d.user1_id = ? OR d.user2_id = ?""", (user["id"], user["id"], user["id"], user["id"]))
    chats = [dict(r) for r in c.fetchall()]
    conn.close()
    conn2 = get_db(MESSAGES_DB)
    c2 = conn2.cursor()
    for ch in chats:
        c2.execute("SELECT count FROM unread WHERE user_id = ? AND room_id = ?", (user["id"], "dm:" + ch["id"]))
        row = c2.fetchone()
        ch["unread"] = row["count"] if row else 0
    conn2.close()
    return chats

@app.get("/api/dm-chats/{chat_id}/history")
def dm_history(chat_id: str, request: Request, limit: int = 50):
    user = require_user(request)
    conn = get_db(MESSAGES_DB)
    c = conn.cursor()
    c.execute("DELETE FROM unread WHERE user_id = ? AND room_id = ?", (user["id"], "dm:" + chat_id))
    conn.commit()
    conn.close()
    return _get_history(f"dm:{chat_id}", limit)

@app.get("/api/topics/{topic_id}/history")
def topic_history(topic_id: str, request: Request, limit: int = 50):
    user = require_user(request)
    conn = get_db(MESSAGES_DB)
    c = conn.cursor()
    c.execute("DELETE FROM unread WHERE user_id = ? AND room_id = ?", (user["id"], "topic:" + topic_id))
    conn.commit()
    conn.close()
    return _get_history(f"topic:{topic_id}", limit)

@app.get("/api/unread")
def get_unread(request: Request):
    user = require_user(request)
    conn = get_db(MESSAGES_DB)
    c = conn.cursor()
    c.execute("SELECT room_id, count FROM unread WHERE user_id = ?", (user["id"],))
    rows = {r["room_id"]: r["count"] for r in c.fetchall()}
    conn.close()
    return rows

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"url": f"/static/uploads/{fname}"}

@app.websocket("/ws/notifications")
async def notif_ws(ws: WebSocket):
    await ws.accept()
    raw = await ws.receive_text()
    try:
        data = json.loads(raw)
    except:
        await ws.close(); return
    token = data.get("token")
    if not token:
        await ws.close(); return
    payload = decode_token(token)
    if not payload:
        await ws.close(); return
    user_id = payload["sub"]
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("UPDATE users SET status = 'online', last_seen = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    notif_manager.connect(user_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notif_manager.disconnect(user_id)
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute("UPDATE users SET status = 'offline', last_seen = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

@app.websocket("/ws/{room_id}")
async def ws_endpoint(room_id: str, ws: WebSocket):
    await ws.accept()
    raw = await ws.receive_text()
    try:
        data = json.loads(raw)
    except:
        await ws.close(); return

    user = None
    token = data.get("token")
    if token:
        payload = decode_token(token)
        if payload:
            conn = get_db(USERS_DB)
            c = conn.cursor()
            c.execute("SELECT id, username, display_name, avatar_color FROM users WHERE id = ?", (payload["sub"],))
            row = c.fetchone()
            conn.close()
            if row:
                user = {"id": row["id"], "name": row["display_name"] or row["username"], "color": row["avatar_color"], "is_guest": False}

    if not user:
        await ws.close()
        return

    manager.connect(room_id, ws, user)

    await ws.send_text(json.dumps({"type": "handshake", "user_id": user["id"], "user": user}))
    await manager.broadcast(room_id, {"type": "user_joined", "user": user, "users": manager.get_users(room_id)}, exclude=ws)
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

            if mtype == "voice_join":
                manager.voice_users.setdefault(room_id, {})[user["id"]] = user
                await manager.broadcast(room_id, {"type": "voice_user_joined", "user": user, "voice_users": manager.get_voice_users(room_id)})
                continue

            if mtype == "voice_leave":
                if room_id in manager.voice_users and user["id"] in manager.voice_users[room_id]:
                    del manager.voice_users[room_id][user["id"]]
                    if not manager.voice_users[room_id]:
                        del manager.voice_users[room_id]
                await manager.broadcast(room_id, {"type": "voice_user_left", "user": user, "voice_users": manager.get_voice_users(room_id)})
                continue

            if mtype == "voice_offer":
                await manager.send_to_user(data["target"], {"type": "voice_offer", "from": user["id"], "offer": data["offer"]})
                continue

            if mtype == "voice_answer":
                await manager.send_to_user(data["target"], {"type": "voice_answer", "from": user["id"], "answer": data["answer"]})
                continue

            if mtype == "voice_ice":
                await manager.send_to_user(data["target"], {"type": "voice_ice", "from": user["id"], "candidate": data["candidate"]})
                continue

            content = data.get("content", "")
            file_url = data.get("file_url")
            db_type = "image" if file_url else "text"

            conn = sqlite3.connect(MESSAGES_DB)
            c = conn.cursor()
            c.execute("INSERT INTO messages (room_id, user_id, user_name, user_color, content, msg_type, file_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (room_id, user["id"] if not user.get("is_guest") else None, user["name"], user["color"], content, db_type, file_url))
            msg_id = c.lastrowid
            conn.commit()
            conn.close()

            room_users = manager.get_users(room_id)
            conn = sqlite3.connect(MESSAGES_DB)
            c = conn.cursor()
            for u in room_users:
                if u["id"] != user["id"]:
                    c.execute("INSERT INTO unread (user_id, room_id, count, last_message_id) VALUES (?, ?, 1, ?) ON CONFLICT(user_id, room_id) DO UPDATE SET count = count + 1, last_message_id = excluded.last_message_id",
                        (u["id"], room_id, msg_id))
            conn.commit()
            conn.close()

            await manager.broadcast(room_id, {"type": "message", "user": user, "content": content, "file_url": file_url, "msg_type": db_type, "timestamp": datetime.utcnow().isoformat() + "Z"})

    except WebSocketDisconnect:
        pass
    finally:
        user_left = manager.disconnect(room_id, ws)
        await manager.broadcast(room_id, {"type": "user_left", "user": user_left, "users": manager.get_users(room_id)})
        if room_id in manager.voice_users and user_left.get("id") in manager.voice_users.get(room_id, {}):
            del manager.voice_users[room_id][user_left["id"]]
            if not manager.voice_users[room_id]:
                del manager.voice_users[room_id]
            await manager.broadcast(room_id, {"type": "voice_user_left", "user": user_left, "voice_users": manager.get_voice_users(room_id)})
