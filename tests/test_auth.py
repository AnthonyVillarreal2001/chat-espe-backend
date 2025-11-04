# tests/test_auth.py
from auth import verify_admin

def test_admin_login():
    assert verify_admin("admin", "espe2025") is True
    assert verify_admin("admin", "wrong") is False
    assert verify_admin("hacker", "espe2025") is False