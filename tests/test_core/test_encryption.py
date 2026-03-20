from app.core.encryption import encrypt_config, decrypt_config

def test_encrypt_decrypt_roundtrip():
    data = {"api_url": "https://pms.example.com", "api_key": "secret123"}
    encrypted = encrypt_config(data)
    assert isinstance(encrypted, bytes)
    assert encrypted != str(data).encode()
    decrypted = decrypt_config(encrypted)
    assert decrypted == data

def test_encrypted_values_differ_each_call():
    data = {"key": "value"}
    assert encrypt_config(data) != encrypt_config(data)  # Fernet uses random IV
