# === FIX DNS + EVENTLET ===
import socket

from pymongo import MongoClient
original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ['localhost', '127.0.0.1']:
        return original_getaddrinfo('127.0.0.1', port, family, type, proto, flags)
    return original_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo
# ===========================
import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import init_db, rooms, user_sessions, messages, db_lock
from rooms import create_room, verify_pin, get_room, get_room_messages
from auth import verify_admin
import redis
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecreto2025'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
# === REDIS ===
redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
r = redis.from_url(redis_url)

# === MONGO ===
mongo_url = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
client = MongoClient(mongo_url)

# === INICIALIZAR DB SOLO EN DESARROLLO ===
if os.getenv("RAILWAY_ENVIRONMENT") != "production":  # ← AÑADE ESTO
    init_db()

active_sessions = {}

# === RUTAS REST ===
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if verify_admin(data['username'], data['password']):
        session['admin'] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route('/api/admin/rooms', methods=['POST'])
def create_room_api():
    if not session.get('admin'):
        return jsonify({"error": "No autorizado"}), 401
    data = request.json
    room_id = create_room(data['name'], data['pin'], data['type'])
    return jsonify({"room_id": room_id})

@app.route('/test')
def test_route():
    return {"status": "ok"}

# === SOCKET EVENTS ===
@socketio.on('join_room')
def handle_join(data):
    room_id = data['room_id']
    pin = data['pin']
    nickname = data['nickname']
    ip = request.remote_addr
    sid = request.sid

    print(f"Intentando unir: {nickname} a sala {room_id} con PIN '{pin}' desde IP {ip}")

    if not verify_pin(room_id, pin):
        print(f"PIN INCORRECTO para sala {room_id}")
        emit('error', {'msg': 'PIN incorrecto'})
        return

    # === BLOQUEO POR SID (NO POR IP) ===
    lock_key_ip = f"lock:{ip}:{room_id}"
    # lock_key = f"lock:sid:{sid}"
    if r.get(lock_key_ip):
        emit('error', {'msg': 'Ya estás conectado en esta pestaña'})
        return
    r.setex(lock_key_ip, 3600, sid)
    # r.setex(lock_key, 3600, "1")  # 1 hora

    join_room(room_id)
    active_sessions[sid] = {
        'room_id': room_id,
        'nickname': nickname,
        'ip': ip,
        #comentar si es para ip
        # 'sid': sid
    }

    with db_lock:
        user_sessions.insert_one({
            "room_id": room_id,
            "nickname": nickname,
            "ip_address": ip,
            "sid": sid,
            "joined_at": datetime.utcnow()
        })

    # ENVIAR HISTORIAL
    history = get_room_messages(room_id)
    emit('history', history)

    emit('joined', {'nickname': nickname}, room=room_id)
    emit('user_list', get_users_in_room(room_id), room=room_id)
    print(f"{nickname} unido a {room_id}")

@socketio.on('message')
def handle_message(data):
    sid = request.sid
    if sid not in active_sessions:
        return
    room_id = active_sessions[sid]['room_id']
    msg_data = {
        'msg': data['msg'],
        'username': active_sessions[sid]['nickname'],
        'timestamp': data.get('timestamp') or datetime.utcnow().isoformat(),
        'type': 'text'
    }
    with db_lock:
        messages.insert_one({
            **msg_data,
            'room_id': room_id
        })
    emit('message', msg_data, room=room_id, include_self=True)

@socketio.on('file')
def handle_file(data):
    sid = request.sid
    if sid not in active_sessions:
        return
    room_id = active_sessions[sid]['room_id']
    room = get_room(room_id)
    if room['type'] != 'multimedia':
        emit('error', {'msg': 'Sala no permite archivos'})
        return
    file_data = data['file']
    if len(file_data) > 10 * 1024 * 1024:
        emit('error', {'msg': 'Archivo > 10MB'})
        return

    file_msg = {
        'username': active_sessions[sid]['nickname'],
        'filename': data['filename'],
        'filetype': data['filetype'],
        'file': file_data,
        'timestamp': data['timestamp'],
        'type': 'file'
    }
    with db_lock:
        messages.insert_one({
            **file_msg,
            'room_id': room_id
        })
    emit('file', file_msg, room=room_id, include_self=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in active_sessions:
        room_id = active_sessions[sid]['room_id']
        ip = active_sessions[sid]['ip']
        r.delete(f"lock:{ip}:{room_id}")
        # r.delete(f"lock:sid:{sid}")
        leave_room(room_id)
        with db_lock:
            user_sessions.delete_one({"sid": sid})
        del active_sessions[sid]
        emit('user_list', get_users_in_room(room_id), room=room_id)

def get_users_in_room(room_id):
    return [s['nickname'] for s in active_sessions.values() if s['room_id'] == room_id]

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))  # ← AÑADIR
    print(f"Servidor en http://0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)