from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from config import SECRET_KEY

def generar_token(usuario_id):
    s = URLSafeTimedSerializer(SECRET_KEY)
    return s.dumps(usuario_id)

def decodificar_token(token, max_age=3600):
    s = URLSafeTimedSerializer(SECRET_KEY)
    try:
        return s.loads(token, max_age=max_age)
    except SignatureExpired:
        print("⚠️ Token expirado")
        return None
    except BadSignature:
        print("❌ Token inválido")
        return None
