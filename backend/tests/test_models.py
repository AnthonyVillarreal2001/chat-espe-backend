# tests/test_models.py
from models import rooms
from rooms import create_room

def test_insert_and_find():
    # init_db() ya se ejecuta automáticamente
    room_id = create_room("Test", "1234", "text")
    assert rooms.count_documents({}) == 1
    assert rooms.find_one({"id": room_id}) is not None