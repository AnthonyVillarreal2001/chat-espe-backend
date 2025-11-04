import bcrypt

# CREDENCIALES FIJAS DEL ADMIN
ADMIN_USER = "admin"
# Hash de "espe2025" generado con bcrypt
ADMIN_HASH = b'$2b$12$Gaifiz8Ou5bAPtitMtrGce.ko8xE28KZE6MGvhu0UExnwOVF2Aj66'

def verify_admin(username, password):
    if username != ADMIN_USER:
        return False
    # Verifica con el hash correcto
    return bcrypt.checkpw(password.encode('utf-8'), ADMIN_HASH)