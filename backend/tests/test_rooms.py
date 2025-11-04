# tests/test_rooms.py
import pytest
import bcrypt
from rooms import create_room, verify_pin
from models import rooms

def test_create_room():
    room_id = create_room("Sala Test", "1234", "text")
    assert len(room_id) == 8
    room = rooms.find_one({"id": room_id})
    assert room["name"] == "Sala Test"
    assert room["type"] == "text"
    assert bcrypt.checkpw("1234".encode(), room["pin"].encode())

def test_create_multimedia_room():
    room_id = create_room("Multimedia", "9999", "multimedia")
    room = rooms.find_one({"id": room_id})
    assert room["type"] == "multimedia"

def test_verify_pin_correct():
    room_id = create_room("Secreta", "abcd", "text")
    assert verify_pin(room_id, "abcd") is True

def test_verify_pin_incorrect():
    room_id = create_room("Falsa", "xyz", "text")
    assert verify_pin(room_id, "wrong") is False
    assert verify_pin("fake_id", "xyz") is False