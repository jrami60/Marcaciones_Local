"""
database.py — Cliente Supabase y operaciones CRUD.
En DEV_MODE=true opera sin Supabase (datos mock).
"""
from __future__ import annotations

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"

# Usuario ficticio para desarrollo local
_DEV_USER = {
    "id": "dev-user-0000",
    "username": "dev",
    "password_hash": "",
    "store_id": 1,
    "is_admin": True,
    "stores": {"id": 1, "store_number": "929", "store_name": "La Paloma"},
}

# ---- Si NO es DEV_MODE cargamos Supabase --------------------------------
if not DEV_MODE:
    from supabase import Client, create_client
    _client: Client | None = None

    def get_db() -> Client:
        global _client
        if _client is None:
            _client = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_KEY"],
            )
        return _client


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

def get_store_by_number(store_number: str) -> dict | None:
    if DEV_MODE:
        mapping = {"929": {"id": 1, "store_number": "929", "store_name": "La Paloma"},
                   "670": {"id": 2, "store_number": "670", "store_name": "Local 670"}}
        return mapping.get(store_number)
    r = get_db().table("stores").select("*").eq("store_number", store_number).execute()
    return r.data[0] if r.data else None


def get_or_create_store(store_number: str, store_name: str) -> dict:
    if DEV_MODE:
        return get_store_by_number(store_number) or {"id": 0, "store_number": store_number, "store_name": store_name}
    existing = get_store_by_number(store_number)
    if existing:
        return existing
    r = get_db().table("stores").insert(
        {"store_number": store_number, "store_name": store_name}
    ).execute()
    return r.data[0]


def get_all_stores() -> list[dict]:
    if DEV_MODE:
        return [{"id": 1, "store_number": "929", "store_name": "La Paloma"},
                {"id": 2, "store_number": "670", "store_name": "Local 670"}]
    r = get_db().table("stores").select("*").order("store_number").execute()
    return r.data


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_username(username: str) -> dict | None:
    if DEV_MODE:
        return _DEV_USER if username == "dev" else None
    r = (
        get_db()
        .table("app_users")
        .select("*, stores(*)")
        .eq("username", username)
        .execute()
    )
    return r.data[0] if r.data else None


def create_user(username: str, password_hash: str,
                store_id: int, is_admin: bool = False) -> dict:
    if DEV_MODE:
        return {"id": "dev-new", "username": username, "store_id": store_id}
    r = get_db().table("app_users").insert({
        "username": username, "password_hash": password_hash,
        "store_id": store_id, "is_admin": is_admin,
    }).execute()
    return r.data[0]


def upsert_user(username: str, password_hash: str,
                store_id: int, is_admin: bool = False) -> dict:
    """Inserta o actualiza un usuario por username (idempotente).
    Garantiza que las credenciales siempre sean las correctas.
    """
    if DEV_MODE:
        return {"id": "dev-upsert", "username": username, "store_id": store_id}
    r = get_db().table("app_users").upsert(
        {
            "username": username,
            "password_hash": password_hash,
            "store_id": store_id,
            "is_admin": is_admin,
        },
        on_conflict="username",
    ).execute()
    return r.data[0]


def users_exist() -> bool:
    if DEV_MODE:
        return True
    r = get_db().table("app_users").select("id").limit(1).execute()
    return len(r.data) > 0


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def save_session(user_id: str, token: str, expires_at: str) -> None:
    if DEV_MODE:
        return
    get_db().table("sessions").insert({
        "user_id": user_id, "token": token, "expires_at": expires_at,
    }).execute()


def get_session_user(token: str) -> dict | None:
    if DEV_MODE:
        return _DEV_USER if token == "dev-token" else None
    now = date.today().isoformat()
    r = (
        get_db()
        .table("sessions")
        .select("*, app_users(*, stores(*))")
        .eq("token", token)
        .gte("expires_at", now)
        .execute()
    )
    if not r.data:
        return None
    return r.data[0].get("app_users")


def delete_session(token: str) -> None:
    if DEV_MODE:
        return
    get_db().table("sessions").delete().eq("token", token).execute()


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def save_upload(store_id: int, user_id: str, upload_type: str,
                filename: str, upload_date: date, record_count: int) -> dict:
    if DEV_MODE:
        return {"id": "dev-upload"}
    r = get_db().table("uploads").insert({
        "store_id": store_id, "user_id": user_id, "upload_type": upload_type,
        "filename": filename, "upload_date": upload_date.isoformat(),
        "record_count": record_count,
    }).execute()
    return r.data[0]


def get_uploads_by_store(store_id: int, limit: int = 10) -> list[dict]:
    if DEV_MODE:
        return []
    r = (
        get_db().table("uploads").select("*")
        .eq("store_id", store_id)
        .order("created_at", desc=True)
        .limit(limit).execute()
    )
    return r.data


# ---------------------------------------------------------------------------
# Analysis results
# ---------------------------------------------------------------------------

def save_analysis(store_id: int, user_id: str, result_date: date,
                  filename_marcas: str, filename_turnos: str,
                  total_records: int, result_json: list[dict]) -> dict:
    if DEV_MODE:
        return {"id": "dev-analysis"}
    r = get_db().table("analysis_results").insert({
        "store_id": store_id, "user_id": user_id,
        "result_date": result_date.isoformat(),
        "filename_marcas": filename_marcas, "filename_turnos": filename_turnos,
        "total_records": total_records, "result_json": result_json,
    }).execute()
    return r.data[0]


def get_analyses_by_store(store_id: int, limit: int = 20) -> list[dict]:
    if DEV_MODE:
        return []
    r = (
        get_db().table("analysis_results")
        .select("id, result_date, filename_marcas, filename_turnos, total_records, created_at")
        .eq("store_id", store_id)
        .order("created_at", desc=True)
        .limit(limit).execute()
    )
    return r.data


def get_analysis_by_id(analysis_id: str) -> dict | None:
    if DEV_MODE:
        return None
    r = (
        get_db().table("analysis_results")
        .select("*").eq("id", analysis_id).execute()
    )
    return r.data[0] if r.data else None


# ---------------------------------------------------------------------------
# Limpieza de datos anteriores (nuevo reporte borra el anterior)
# ---------------------------------------------------------------------------

def delete_analyses_for_store(store_id: int) -> None:
    """Elimina todos los análisis guardados de una tienda."""
    if DEV_MODE:
        return
    get_db().table("analysis_results").delete().eq("store_id", store_id).execute()


def delete_uploads_for_store(store_id: int) -> None:
    """Elimina todos los registros de uploads de una tienda."""
    if DEV_MODE:
        return
    get_db().table("uploads").delete().eq("store_id", store_id).execute()
