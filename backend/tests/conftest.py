# backend/tests/conftest.py
import os
import sys
import pytest

# Añade backend al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa TODO para coverage
import main
import rooms
import auth
import models

@pytest.fixture(autouse=True)
def clean_db():
    """Limpia DB antes de CADA prueba"""
    models.init_db()