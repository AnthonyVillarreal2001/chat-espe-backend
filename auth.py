import bcrypt

# CREDENCIALES FIJAS DEL ADMIN
ADMIN_USER = "admin"
# Hash de "espe2025" generado con bcrypt
ADMIN_HASH = b'$2a$12$8dgp4N3xGN3xPzVXFrEmxeZN3nS2o3qXTqaObQsoTvjeiaCY3llei'

def verify_admin(username, password):
    if username != ADMIN_USER:
        return False
    # Verifica con el hash correcto
    return bcrypt.checkpw(password.encode('utf-8'), ADMIN_HASH)