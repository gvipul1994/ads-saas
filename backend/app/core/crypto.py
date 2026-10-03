"""
Encrypts Google Ads OAuth refresh tokens before they touch the database.
A refresh token is a long-lived secret equivalent to a password for that
client's entire Google Ads account — it must never be stored in plaintext.

FERNET_KEY must be a stable, securely-generated key (see README for how to
generate one). Losing it means every stored refresh token becomes
undecryptable and every client must reconnect.
"""
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.fernet_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
