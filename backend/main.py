# === FIX DNS + EVENTLET ===
import socket
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
from models import init_db, rooms, user_sessions, db_lock
from rooms import create_room, verify_pin, get_room
from auth import verify_admin
import redis
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecreto2025'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

r = redis.Redis(host='127.0.0.1', port=6379, db=0, socket_connect_timeout=2)

# Inicializar DB
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
    print("Servidor en http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    
# Al final de app.py
@app.route('/test')
def test_route():
    return {"status": "ok"}