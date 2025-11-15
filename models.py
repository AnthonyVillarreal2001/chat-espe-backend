from pymongo import MongoClient
from datetime import datetime
import threading

client = MongoClient(
    host='127.0.0.1',
    port=27017,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=3000
)
db = client['chat_espe']
rooms = db['rooms']
user_sessions = db['user_sessions']
messages = db['messages']  # ← NUEVA COLECCIÓN
db_lock = threading.Lock()

def init_db():
    with db_lock:
        print("Limpieza de DB para pruebas...")
        rooms.delete_many({})
        user_sessions.delete_many({})
        messages.delete_many({})
        print("DB limpia")
    try:
        client.admin.command('ping')
        rooms.create_index("id", unique=True)
        user_sessions.create_index([("room_id", 1), ("sid", 1)])
        messages.create_index([("room_id", 1), ("timestamp", 1)])
        print("MongoDB conectado correctamente (Compass activo)")
    except Exception as e:
        print(f"ERROR: No se pudo conectar a MongoDB: {e}")
        print("Asegúrate de tener MongoDB Compass abierto y conectado a 127.0.0.1:27017")
        exit(1)