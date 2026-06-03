"""
main.py — Servidor FastAPI: auth, multi-tienda, colaciones y turnos.
"""
from __future__ import annotations

import io
from datetime import date, time
from typing import Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

import auth
import database as db
from analyzer import RegistroDia, analizar
from parsers import extract_store_info, parse_marcas, parse_turnos

app = FastAPI(title="Marcaciones Walmart Chile")

_jinja = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
)

# Estado en memoria por tienda: store_id -> dict
_state: dict[int, dict] = {}


def _store_state(store_id: int) -> dict:
    if store_id not in _state:
        _state[store_id] = {
            "marcas": [], "turnos": [], "resultados": [],
            "marcas_nombre": "", "turnos_nombre": "",
            "last_analysis_id": None,
        }
    return _state[store_id]


def _render(name: str, ctx: dict) -> HTMLResponse:
    return HTMLResponse(_jinja.get_template(name).render(**ctx))


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Helpers de serialización
# ---------------------------------------------------------------------------

def _fmt_time(t: Optional[time]) -> str:
    return t.strftime("%H:%M") if t else "—"


def _registro_to_dict(r: RegistroDia) -> dict:
    pausas = [
        {
            "inicio": _fmt_time(p.inicio) if p.estado != "FALTA" else "—",
            "fin": _fmt_time(p.fin) if p.estado != "FALTA" else "—",
            "duracion": p.duracion_min,
            "esperado": p.esperado_min,
            "exceso": p.exceso_min,
            "obligatoria": p.es_obligatoria,
            "estado": p.estado,
        }
        for p in r.pausas
    ]
    return {
        "rut": r.rut, "nro": r.nro_personal,
        "nombre": r.nombre, "cargo": r.cargo, "seccion": r.seccion,
        "fecha": r.fecha.strftime("%d/%m/%Y") if r.fecha else "—",
        "fecha_iso": r.fecha.isoformat() if r.fecha else "",
        "turno_raw": r.turno_raw,
        "turno_inicio": _fmt_time(r.turno_inicio),
        "turno_fin": _fmt_time(r.turno_fin),
        "es_nocturno": r.es_nocturno,
        "llegada": _fmt_time(r.llegada),
        "salida": _fmt_time(r.salida),
        "atraso_min": r.atraso_min,
        "extra_min": r.extra_min,
        "estado_entrada": r.estado_entrada,
        "estado_salida": r.estado_salida,
        "pausas": pausas,
        "alertas": r.alertas,
        "estado_colacion": r.estado_colacion,
    }


def _base_ctx(user: dict) -> dict:
    """Contexto base compartido en todos los templates autenticados."""
    store = user.get("stores") or {}
    return {
        "user_name": user.get("username", ""),
        "is_admin": user.get("is_admin", False),
        "store_number": store.get("store_number", ""),
        "store_name": store.get("store_name", ""),
    }


# ---------------------------------------------------------------------------
# Rutas públicas: login
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    # Si ya tiene sesión, redirigir
    user = auth.get_user_from_request(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return _render("login.html", {"error": error})


@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()

    # Setup inicial: si no hay usuarios, crear el primero como admin
    if not db.users_exist():
        return _render("login.html", {
            "error": "",
            "setup_mode": True,
            "username": username,
        })

    user = auth.authenticate(username, password)
    if not user:
        return _render("login.html", {"error": "Usuario o contraseña incorrectos"})

    token = auth.create_session(user["id"])
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 7, samesite="lax")
    return response


@app.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        auth.logout(token)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# ---------------------------------------------------------------------------
# Setup inicial (crear primer usuario admin)
# ---------------------------------------------------------------------------

@app.post("/setup")
async def setup_post(request: Request):
    if db.users_exist():
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()
    store_id_raw = str(form.get("store_id", "")).strip()

    if not username or not password or not store_id_raw:
        stores = db.get_all_stores()
        return _render("login.html", {
            "error": "Completa todos los campos",
            "setup_mode": True,
            "stores": stores,
        })

    pwd_hash = auth.hash_password(password)
    user = db.create_user(username, pwd_hash, int(store_id_raw), is_admin=True)
    token = auth.create_session(user["id"])
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 7, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# Rutas protegidas
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = auth.get_user_from_request(request)
    if not user:
        return _redirect_login()

    store = user.get("stores") or {}
    store_id = store.get("id")
    state = _store_state(store_id) if store_id else {}
    history = db.get_analyses_by_store(store_id, limit=5) if store_id else []

    return _render("index.html", {
        **_base_ctx(user),
        "marcas_nombre": state.get("marcas_nombre", ""),
        "turnos_nombre": state.get("turnos_nombre", ""),
        "n_resultados": len(state.get("resultados", [])),
        "history": history,
    })


@app.post("/upload/marcas")
async def upload_marcas(request: Request, file: UploadFile = File(...)):
    user = auth.get_user_from_request(request)
    if not user:
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    content = await file.read()
    try:
        marcas = parse_marcas(io.BytesIO(content))
        store_info = extract_store_info(io.BytesIO(content))
        store = db.get_or_create_store(
            store_info["store_number"], store_info["store_name"]
        )
        store_id = store["id"]
        state = _store_state(store_id)
        state["marcas"] = marcas
        state["marcas_nombre"] = file.filename
        state["resultados"] = []

        db.save_upload(store_id, user["id"], "marcas",
                       file.filename, date.today(), len(marcas))

        return JSONResponse({
            "ok": True, "registros": len(marcas), "nombre": file.filename,
            "store_number": store_info["store_number"],
            "store_name": store_info["store_name"],
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/upload/turnos")
async def upload_turnos(request: Request, file: UploadFile = File(...)):
    user = auth.get_user_from_request(request)
    if not user:
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    content = await file.read()
    try:
        turnos = parse_turnos(io.BytesIO(content))
        store = user.get("stores") or {}
        store_id = store.get("id")
        if store_id:
            state = _store_state(store_id)
            state["turnos"] = turnos
            state["turnos_nombre"] = file.filename
            state["resultados"] = []
            db.save_upload(store_id, user["id"], "turnos",
                           file.filename, date.today(), len(turnos))

        return JSONResponse({"ok": True, "registros": len(turnos), "nombre": file.filename})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/analizar")
async def run_analizar(request: Request):
    user = auth.get_user_from_request(request)
    if not user:
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    store = user.get("stores") or {}
    store_id = store.get("id")
    state = _store_state(store_id)

    if not state["marcas"]:
        return JSONResponse({"ok": False, "error": "No hay marcas cargadas"}, status_code=400)

    try:
        resultados = analizar(state["marcas"], state["turnos"])
        state["resultados"] = resultados

        # Detectar fecha del reporte
        fechas = [r.fecha for r in resultados if r.fecha]
        result_date = min(fechas) if fechas else date.today()

        # Guardar en Supabase
        rows_json = [_registro_to_dict(r) for r in resultados]
        saved = db.save_analysis(
            store_id, user["id"], result_date,
            state["marcas_nombre"], state["turnos_nombre"],
            len(resultados), rows_json,
        )
        state["last_analysis_id"] = saved["id"]

        return JSONResponse({"ok": True, "total": len(resultados)})
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "error": str(e),
                             "trace": traceback.format_exc()}, status_code=500)


@app.get("/resultados", response_class=HTMLResponse)
async def resultados_page(request: Request, fecha: str = "", nombre: str = "",
                          seccion: str = "", estado: str = "",
                          analysis_id: str = ""):
    user = auth.get_user_from_request(request)
    if not user:
        return _redirect_login()

    store = user.get("stores") or {}
    store_id = store.get("id")
    state = _store_state(store_id)

    # Cargar desde BD si se especifica analysis_id o si no hay en memoria
    if analysis_id:
        row = db.get_analysis_by_id(analysis_id)
        rows = row["result_json"] if row else []
        marcas_nombre = row.get("filename_marcas", "") if row else ""
        turnos_nombre = row.get("filename_turnos", "") if row else ""
    else:
        rows = [_registro_to_dict(r) for r in state["resultados"]]
        marcas_nombre = state.get("marcas_nombre", "")
        turnos_nombre = state.get("turnos_nombre", "")

    total_sin_filtro = len(rows)

    # Filtros
    if fecha:
        rows = [r for r in rows if r["fecha_iso"] == fecha]
    if nombre:
        rows = [r for r in rows if nombre.lower() in r["nombre"].lower()]
    if seccion:
        rows = [r for r in rows if seccion.lower() in r["seccion"].lower()]
    if estado:
        rows = [r for r in rows if
                r["estado_colacion"] == estado or
                r["estado_entrada"] == estado or
                r["estado_salida"] == estado]

    total = len(rows)
    all_rows = [_registro_to_dict(r) for r in state["resultados"]] if not analysis_id else \
               (db.get_analysis_by_id(analysis_id) or {}).get("result_json", [])

    return _render("resultados.html", {
        **_base_ctx(user),
        "rows": rows,
        "total": total,
        "total_sin_filtro": total_sin_filtro,
        "con_exceso":    sum(1 for r in rows if r["estado_colacion"] == "EXCESO"),
        "con_tolerancia":sum(1 for r in rows if r["estado_colacion"] == "TOLERANCIA"),
        "con_atraso":    sum(1 for r in rows if r["estado_entrada"] == "ATRASO"),
        "con_extra":     sum(1 for r in rows if r["estado_salida"] == "EXTRA"),
        "filtro_fecha": fecha, "filtro_nombre": nombre,
        "filtro_seccion": seccion, "filtro_estado": estado,
        "todas_secciones": sorted({r["seccion"] for r in all_rows}),
        "todas_fechas":    sorted({r["fecha_iso"] for r in all_rows}),
        "marcas_nombre": marcas_nombre,
        "turnos_nombre": turnos_nombre,
        "history": db.get_analyses_by_store(store_id, limit=10) if store_id else [],
        "current_analysis_id": analysis_id,
    })


# ---------------------------------------------------------------------------
# Admin: crear usuarios adicionales
# ---------------------------------------------------------------------------

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def admin_usuarios(request: Request):
    user = auth.get_user_from_request(request)
    if not user or not user.get("is_admin"):
        return _redirect_login()
    stores = db.get_all_stores()
    return _render("admin_usuarios.html", {**_base_ctx(user), "stores": stores, "ok": False})


@app.post("/admin/usuarios")
async def admin_crear_usuario(request: Request):
    user = auth.get_user_from_request(request)
    if not user or not user.get("is_admin"):
        return _redirect_login()
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()
    store_id = int(form.get("store_id", 0))
    is_admin = form.get("is_admin") == "on"

    try:
        pwd_hash = auth.hash_password(password)
        db.create_user(username, pwd_hash, store_id, is_admin)
        stores = db.get_all_stores()
        return _render("admin_usuarios.html", {
            **_base_ctx(user), "stores": stores,
            "ok": True, "msg": f"Usuario '{username}' creado correctamente.",
        })
    except Exception as e:
        stores = db.get_all_stores()
        return _render("admin_usuarios.html", {
            **_base_ctx(user), "stores": stores,
            "ok": False, "error": str(e),
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8766, reload=True)
