import os
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request
from fastapi.responses import RedirectResponse

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return _pwd_ctx.verify(password, hashed)

def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    return URLSafeTimedSerializer(secret)

def create_session_token(user_id: int) -> str:
    return _serializer().dumps(user_id, salt="session")

def decode_session_token(token: str) -> int | None:
    try:
        # Token valid for 30 days
        return _serializer().loads(token, salt="session", max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        return None

def get_user_from_request(request: Request, db):
    """Returns (user, None) or (None, RedirectResponse to /login)."""
    from app.database import User
    token = request.cookies.get("session")
    if token:
        user_id = decode_session_token(token)
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user, None
    return None, RedirectResponse(url="/login", status_code=303)
