import threading
import shortuuid
import bcrypt
from models import rooms, messages, db_lock
from datetime import datetime

def create_room(name, pin, room_type):
    with db_lock:
        room_id = shortuuid.uuid()[:8]
        pin_bytes = pin.encode('utf-8')
        pin_hash = bcrypt.hashpw(pin_bytes, bcrypt.gensalt()).decode('utf-8')
        room_data = {
            "id": room_id,
            "name": name,
            "pin": pin_hash,
            "type": room_type,
            "created_at": datetime.utcnow()
        }
        rooms.insert_one(room_data)
        print(f"Sala creada: {room_id} | PIN hasheado: {pin_hash[:20]}...")
        return room_id

def verify_pin(room_id, pin):
    try:
        room = rooms.find_one({"id": room_id})
        if not room:
            print(f"Sala no encontrada: {room_id}")
            return False
        pin_bytes = pin.encode('utf-8')
        result = bcrypt.checkpw(pin_bytes, room["pin"].encode('utf-8'))
        print(f"Verificando PIN para {room_id}: {pin} -> {result}")
        return result
    except Exception as e:
        print(f"Error verificando PIN: {e}")
        return False

def get_room(room_id):
    return rooms.find_one({"id": room_id})

def get_room_messages(room_id, limit=100):
    cursor = messages.find({"room_id": room_id}).sort("timestamp", -1).limit(limit)
    msgs = list(cursor)[::-1]
    for msg in msgs:
        msg['_id'] = str(msg['_id'])
    return msgs