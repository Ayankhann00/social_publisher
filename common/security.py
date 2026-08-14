import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt_token(raw_token: str) -> str:
    f = _get_fernet()
    return f.encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted_token.encode()).decode()


def sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)
