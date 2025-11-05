# main.py
from dotenv import load_dotenv
load_dotenv()

import os
import gevent
from gevent import monkey
monkey.patch_all()

from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS  # ← CORS
from models import init_db, rooms, user_sessions, db_lock
from rooms import create_room, verify_pin, get_room
from auth import verify_admin
import redis
from datetime import datetime
from pymongo import MongoClient
import threading
import requests
import shortuuid

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')
CORS(app, supports_credentials=True)  # ← CORS + COOKIES

# === Redis Upstash ===
REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

if REDIS_URL and REDIS_TOKEN:
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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', cookie='session_id')

# === INIT DB ===
init_db()
active_sessions = {}

# === RUTAS ===
@app.route('/test')
def test():
    return jsonify({"status": "ok"})

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if verify_admin(data.get('username'), data.get('password')):
        session['admin'] = True
        return jsonify({"success": True})
    return jsonify({"error": "Credenciales inválidas"}), 401

@app.route('/api/admin/rooms', methods=['POST'])
def api_create_room():
    if not session.get('admin'):
        return jsonify({"error": "No autorizado"}), 401
    data = request.get_json()
    room = create_room(data['name'], data['pin'], data['type'])
    return jsonify({"room_id": room['room_id']})

# === SOCKET EVENTS ===
@socketio.on('join_room')
def handle_join(data):
    room_id = data['room_id']
    pin = data['pin']
    nickname = data['nickname']
    ip = request.remote_addr

    if not verify_pin(room_id, pin):
        emit('error', {'msg': 'PIN incorrecto'})
        return

    room = get_room(room_id)
    if not room:
        emit('error', {'msg': 'Sala no existe'})
        return

    with db_lock:
        if ip in user_sessions and user_sessions[ip] != room_id:
            emit('error', {'msg': 'Ya estás en otra sala'})
            return
        user_sessions[ip] = room_id

    join_room(room_id)
    emit('joined', room=room_id, to=room_id)
    emit('user_list', list(room.get('users', {}).keys()), to=room_id)
    print(f"{nickname} se unió a {room_id}")

@socketio.on('message')
def handle_message(data):
    room_id = user_sessions.get(request.remote_addr)
    if not room_id:
        return
    msg = {
        'msg': data['msg'],
        'username': data.get('username', 'Anónimo'),
        'timestamp': data['timestamp']
    }
    emit('message', msg, to=room_id)

@socketio.on('file')
def handle_file(data):
    room_id = user_sessions.get(request.remote_addr)
    if not room_id:
        return
    file_msg = {
        'file': data['file'],
        'filename': data['filename'],
        'filetype': data['filetype'],
        'username': data.get('username', 'Anónimo'),
        'timestamp': data['timestamp']
    }
    emit('file', file_msg, to=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in active_sessions:
        room_id = active_sessions[sid]['room_id']
        ip = active_sessions[sid]['ip']
        r.delete(f"lock:{ip}:{room_id}")
        leave_room(room_id)

        with db_lock:
            user_sessions.delete_one({"sid": sid})

        del active_sessions[sid]
        emit('user_list', get_users_in_room(room_id), room=room_id)

def get_users_in_room(room_id):
    return [s['nickname'] for s in active_sessions.values() if s['room_id'] == room_id]

@app.route('/test')
def test_route():
    return {"status": "ok"}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)