import json
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)

def encrypt_config(data: dict) -> bytes:
    return _get_fernet().encrypt(json.dumps(data).encode())

def decrypt_config(data: bytes) -> dict:
    return json.loads(_get_fernet().decrypt(data).decode())
