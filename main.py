# === IMPORTS ===
import os
import socket
import eventlet
eventlet.monkey_patch()

# === PATCH DNS (Render) ===
original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(*args, **kwargs):
    if args[0] in ['localhost', '127.0.0.1']:
        args = list(args)
        args[0] = '127.0.0.1'
    return original_getaddrinfo(*args, **kwargs)
socket.getaddrinfo = patched_getaddrinfo

from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import init_db, rooms, user_sessions, db_lock
from rooms import create_room, verify_pin, get_room
from auth import verify_admin
import redis
from datetime import datetime
from pymongo import MongoClient
import threading

# === CONFIG ===
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'supersecreto2025')

# MongoDB ya se conecta en models.py
from models import init_db, rooms, user_sessions, db_lock

# === Redis (Upstash REST o Redis Protocol) ===
REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

if REDIS_URL and REDIS_TOKEN:
    import requests
    class UpstashRedis:
        def __init__(self, url, token):
            self.url = url
            self.token = token
        def get(self, key):
            try:
                r = requests.get(f"{self.url}/{key}", headers={"Authorization": f"Bearer {self.token}"})
                return r.json().get('result')
            except:
                return None
        def setex(self, key, seconds, value):
            try:
                requests.post(self.url, json=["SET", key, value, "EX", seconds], headers={"Authorization": f"Bearer {self.token}"})
            except:
                pass
        def delete(self, key):
            try:
                requests.post(self.url, json=["DEL", key], headers={"Authorization": f"Bearer {self.token}"})
            except:
                pass
    r = UpstashRedis(REDIS_URL, REDIS_TOKEN)
else:
    import redis
    r = redis.Redis(host='127.0.0.1', port=6379, db=0, socket_connect_timeout=2)

# === SocketIO ===
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# === INIT DB ===
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

# === SOCKET EVENTS ===
@socketio.on('join_room')
def handle_join(data):
    room_id = data['room_id']
    pin = data['pin']
    nickname = data['nickname']
    ip = request.remote_addr
    sid = request.sid
    
    print(f"👤 Intentando unir: {nickname} a sala {room_id} con PIN '{pin}' desde IP {ip}")

    # Verificar PIN con logging
    if not verify_pin(room_id, pin):
        print(f"❌ PIN INCORRECTO para sala {room_id}")
        emit('error', {'msg': 'PIN incorrecto'})
        return

    # Sesión única por IP
    lock_key = f"lock:{ip}:{room_id}"
    if r.get(lock_key):
        emit('error', {'msg': 'Ya estás en esta sala desde otro dispositivo'})
        return

    r.setex(lock_key, 3600, sid)  # 1 hora

    join_room(room_id)
    active_sessions[sid] = {
        'room_id': room_id,
        'nickname': nickname,
        'ip': ip
    }

    # Guardar sesión en MongoDB
    with db_lock:
        user_sessions.insert_one({
            "room_id": room_id,
            "nickname": nickname,
            "ip_address": ip,
            "sid": sid,
            "joined_at": datetime.utcnow()
        })

    emit('joined', {'nickname': nickname}, room=room_id)
    emit('user_list', get_users_in_room(room_id), room=room_id)
    print(f"✅ {nickname} unido a {room_id}")

@socketio.on('message')
def handle_message(data):
    sid = request.sid
    if sid not in active_sessions:
        return
    room_id = active_sessions[sid]['room_id']
    msg = {
        'msg': data['msg'],
        'username': active_sessions[sid]['nickname'],
        'timestamp': data.get('timestamp')
    }
    emit('message', msg, room=room_id, include_self=True)

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

    emit('file', {
        'username': active_sessions[sid]['nickname'],
        'filename': data['filename'],
        'filetype': data['filetype'],
        'file': file_data,
        'timestamp': data['timestamp']
    }, room=room_id, include_self=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in active_sessions:
        room_id = active_sessions[sid]['room_id']
        ip = active_sessions[sid]['ip']
        r.delete(f"lock:{ip}:{room_id}")
        leave_room(room_id)

        # Borrar de MongoDB
        with db_lock:
            user_sessions.delete_one({"sid": sid})

        del active_sessions[sid]
        emit('user_list', get_users_in_room(room_id), room=room_id)

def get_users_in_room(room_id):
    return [s['nickname'] for s in active_sessions.values() if s['room_id'] == room_id]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Servidor en http://0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
    
# Al final de app.py
@app.route('/test')
def test_route():
    return {"status": "ok"}