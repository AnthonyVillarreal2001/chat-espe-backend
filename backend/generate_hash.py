# archivo: generate_hash.py
import bcrypt
print(bcrypt.hashpw("espe2025".encode(), bcrypt.gensalt()))