"""
auth.py — Hash de contrasenas, sesiones y validacion de usuario.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

import database as db

SESSION_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def authenticate(username: str, password: str) -> dict | None:
    """Retorna el usuario si las credenciales son correctas, None si no."""
    user = db.get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def create_session(user_id: str) -> str:
    """Crea sesion en BD y retorna el token."""
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    ).isoformat()
    db.save_session(user_id, token, expires_at)
    return token


def validate_session(token: str) -> dict | None:
    """Retorna usuario si la sesion es valida, None si no."""
    if not token:
        return None
    return db.get_session_user(token)


def logout(token: str) -> None:
    db.delete_session(token)


def get_user_from_request(request) -> dict | None:
    token = request.cookies.get("session_token")
    if not token:
        return None
    return validate_session(token)
