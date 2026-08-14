import secrets

from app.database import SessionLocal
from app.models import SocialToken
from common.security import encrypt_token, decrypt_token


def get_or_create_token(platform: str) -> str:
    db = SessionLocal()
    try:
        existing = db.query(SocialToken).filter_by(platform=platform).first()
        if existing:
            return decrypt_token(existing.encrypted_token)

        fake_token = f"fake-{platform}-{secrets.token_hex(16)}"
        record = SocialToken(platform=platform, encrypted_token=encrypt_token(fake_token))
        db.add(record)
        db.commit()
        return fake_token
    finally:
        db.close()
