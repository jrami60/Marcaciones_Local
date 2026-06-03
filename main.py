"""
main.py — Servidor FastAPI para el sistema de marcaciones.
"""
from __future__ import annotations

import io
import json
from datetime import date, time
from typing import Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from analyzer import RegistroDia, analizar
from parsers import parse_marcas, parse_turnos

app = FastAPI(title="Marcaciones La Paloma 929")
templates = Jinja2Templates(directory="templates")

# Estado en memoria (single-user desktop app)
_state: dict = {
    "marcas": [],
    "turnos": [],
    "resultados": [],
    "marcas_nombre": "",
    "turnos_nombre": "",
}


# ---------------------------------------------------------------------------
# Serialización de objetos para templates
# ---------------------------------------------------------------------------

def _fmt_time(t: Optional[time]) -> str:
    if t is None:
        return "—"
    return t.strftime("%H:%M")


def _registro_to_dict(r: RegistroDia) -> dict:
    pausas = []
    for p in r.pausas:
        pausas.append({
            "inicio": _fmt_time(p.inicio) if p.estado != "FALTA" else "—",
            "fin": _fmt_time(p.fin) if p.estado != "FALTA" else "—",
            "duracion": p.duracion_min,
            "esperado": p.esperado_min,
            "tolerancia": p.tolerancia_min,
            "exceso": p.exceso_min,
            "obligatoria": p.es_obligatoria,
            "estado": p.estado,
        })
    return {
        "rut": r.rut,
        "nro": r.nro_personal,
        "nombre": r.nombre,
        "cargo": r.cargo,
        "seccion": r.seccion,
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


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "marcas_nombre": _state["marcas_nombre"],
        "turnos_nombre": _state["turnos_nombre"],
        "n_resultados": len(_state["resultados"]),
    })


@app.post("/upload/marcas")
async def upload_marcas(file: UploadFile = File(...)):
    content = await file.read()
    try:
        marcas = parse_marcas(io.BytesIO(content))
        _state["marcas"] = marcas
        _state["marcas_nombre"] = file.filename
        _state["resultados"] = []  # reset
        return JSONResponse({"ok": True, "registros": len(marcas), "nombre": file.filename})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/upload/turnos")
async def upload_turnos(file: UploadFile = File(...)):
    content = await file.read()
    try:
        turnos = parse_turnos(io.BytesIO(content))
        _state["turnos"] = turnos
        _state["turnos_nombre"] = file.filename
        _state["resultados"] = []  # reset
        return JSONResponse({"ok": True, "registros": len(turnos), "nombre": file.filename})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/analizar")
async def run_analizar(request: Request):
    if not _state["marcas"]:
        return JSONResponse({"ok": False, "error": "No hay marcas cargadas"}, status_code=400)
    try:
        resultados = analizar(_state["marcas"], _state["turnos"])
        _state["resultados"] = resultados
        return JSONResponse({"ok": True, "total": len(resultados)})
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()}, status_code=500)


@app.get("/resultados", response_class=HTMLResponse)
async def resultados_page(
    request: Request,
    fecha: str = "",
    nombre: str = "",
    seccion: str = "",
    estado: str = "",
):
    rows = [_registro_to_dict(r) for r in _state["resultados"]]

    # Filtros
    if fecha:
        rows = [r for r in rows if r["fecha_iso"] == fecha]
    if nombre:
        rows = [r for r in rows if nombre.lower() in r["nombre"].lower()]
    if seccion:
        rows = [r for r in rows if seccion.lower() in r["seccion"].lower()]
    if estado:
        rows = [r for r in rows if r["estado_colacion"] == estado or
                r["estado_entrada"] == estado or r["estado_salida"] == estado]

    # Métricas resumen
    total = len(rows)
    con_exceso = sum(1 for r in rows if r["estado_colacion"] == "EXCESO")
    con_tolerancia = sum(1 for r in rows if r["estado_colacion"] == "TOLERANCIA")
    con_atraso = sum(1 for r in rows if r["estado_entrada"] == "ATRASO")
    con_extra = sum(1 for r in rows if r["estado_salida"] == "EXTRA")

    # Secciones únicas para filtro
    todas_secciones = sorted({r["seccion"] for r in _state.get("resultados", []) and
                               [_registro_to_dict(x) for x in _state["resultados"]]})
    todas_secciones = sorted({_registro_to_dict(r)["seccion"] for r in _state["resultados"]})
    todas_fechas = sorted({_registro_to_dict(r)["fecha_iso"] for r in _state["resultados"]})

    return templates.TemplateResponse("resultados.html", {
        "request": request,
        "rows": rows,
        "total": total,
        "con_exceso": con_exceso,
        "con_tolerancia": con_tolerancia,
        "con_atraso": con_atraso,
        "con_extra": con_extra,
        "filtro_fecha": fecha,
        "filtro_nombre": nombre,
        "filtro_seccion": seccion,
        "filtro_estado": estado,
        "todas_secciones": todas_secciones,
        "todas_fechas": todas_fechas,
        "marcas_nombre": _state["marcas_nombre"],
        "turnos_nombre": _state["turnos_nombre"],
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8765, reload=True)
