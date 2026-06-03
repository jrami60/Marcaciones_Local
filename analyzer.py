"""
analyzer.py — Lógica de negocio: colaciones, tolerancias, atrasos y extras.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from parsers import Marca, TurnoDay


# ---------------------------------------------------------------------------
# Constantes de tolerancias
# ---------------------------------------------------------------------------

PAUSE_30_MIN = 30
PAUSE_15_MIN = 15
TOL_30 = 2        # minutos de tolerancia para pausa de 30 min
TOL_15 = 1        # minutos de tolerancia para pausa de 15 min
TURNO_TOL = 10    # minutos de tolerancia entrada/salida de turno

# Hora de inicio que separa turno AM/PM de nocturno (22:00+)
NIGHT_START = time(21, 0)


# ---------------------------------------------------------------------------
# Data classes de resultado
# ---------------------------------------------------------------------------

@dataclass
class PausaResultado:
    inicio: time
    fin: time
    duracion_min: float
    esperado_min: int
    tolerancia_min: int
    exceso_min: float      # positivo = tomó de más; negativo = tomó de menos
    es_obligatoria: bool
    estado: str            # "OK" | "TOLERANCIA" | "EXCESO" | "FALTA" | "SIN_PAR"


@dataclass
class RegistroDia:
    rut: str
    nro_personal: str
    nombre: str
    cargo: str
    seccion: str
    fecha: date
    # Turno planificado
    turno_raw: str
    turno_inicio: Optional[time]
    turno_fin: Optional[time]
    es_nocturno: bool
    # Marcas reales
    llegada: Optional[time]
    salida: Optional[time]
    # Comparaciones turno
    atraso_min: float           # positivo = llegó tarde
    extra_min: float            # positivo = salió tarde
    estado_entrada: str         # "OK" | "ATRASO" | "ANTICIPADO" | "SIN_MARCA"
    estado_salida: str
    # Colaciones
    pausas: list[PausaResultado] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    # Estado general colaciones
    estado_colacion: str = "OK"  # "OK" | "TOLERANCIA" | "EXCESO" | "SIN_COLACION"


# ---------------------------------------------------------------------------
# Helpers de tiempo
# ---------------------------------------------------------------------------

def _to_minutes(t: time) -> float:
    return t.hour * 60 + t.minute + t.second / 60


def _diff_minutes(t_real: time, t_plan: time, nocturno: bool = False) -> float:
    """
    Diferencia real - plan en minutos.
    Positivo = real es posterior a plan.
    Nocturno: si plan < 12 (madrugada) y real > 12 → real es "del día anterior".
    """
    r = _to_minutes(t_real)
    p = _to_minutes(t_plan)
    diff = r - p
    # Corrección cruce medianoche (para entradas/salidas nocturnas)
    if nocturno and abs(diff) > 720:
        diff = diff - 1440 if diff > 0 else diff + 1440
    return diff


def _duration_minutes(inicio: time, fin: time) -> float:
    """Duración en minutos entre dos horas; puede cruzar medianoche."""
    d = _to_minutes(fin) - _to_minutes(inicio)
    if d < 0:
        d += 1440
    return d


# ---------------------------------------------------------------------------
# Lógica de colaciones
# ---------------------------------------------------------------------------

def _determinar_tipo_turno(llegada: Optional[time], turno_inicio: Optional[time],
                            es_nocturno: bool) -> str:
    """Clasifica el turno como 'AM', 'PM' o 'NOCHE'."""
    if es_nocturno:
        return "NOCHE"
    ref = llegada or turno_inicio
    if ref is None:
        return "AM"
    h = ref.hour
    if h < 14:
        return "AM"
    if h < 21:
        return "PM"
    return "NOCHE"


def _reglas_pausas(tipo_turno: str, n_pausas: int) -> list[dict]:
    """
    Retorna reglas esperadas según tipo de turno y cantidad de pausas.
    Cada regla: {"duracion": int, "tolerancia": int, "obligatoria": bool}
    """
    if tipo_turno == "NOCHE":
        # Una sola pausa de 30 min obligatoria
        return [{"duracion": 30, "tolerancia": TOL_30, "obligatoria": True}]
    # AM o PM
    if n_pausas == 1:
        return [{"duracion": 30, "tolerancia": TOL_30, "obligatoria": True}]
    if n_pausas >= 2:
        return [
            {"duracion": 15, "tolerancia": TOL_15, "obligatoria": False},
            {"duracion": 30, "tolerancia": TOL_30, "obligatoria": True},
        ]
    return []


def _emparejar_pausas(marcas_dia: list[Marca]) -> list[tuple[time, time]]:
    """
    Empareja P15 (inicio) con el P25 (fin) más cercano posterior.
    Retorna lista de (inicio, fin).
    """
    inicios = sorted(
        [m.hora for m in marcas_dia if m.cod == "P15"],
    )
    fines_raw = sorted(
        [m.hora for m in marcas_dia if m.cod == "P25"],
    )
    fines_usados: set[int] = set()
    pares: list[tuple[time, time]] = []

    for ini in inicios:
        ini_min = _to_minutes(ini)
        mejor: Optional[time] = None
        mejor_diff = float("inf")
        for j, fin in enumerate(fines_raw):
            if j in fines_usados:
                continue
            fin_min = _to_minutes(fin)
            diff = fin_min - ini_min
            if diff < 0:
                diff += 1440  # cruce medianoche
            if diff < mejor_diff:
                mejor_diff = diff
                mejor = fin
                mejor_idx = j
        if mejor is not None and mejor_diff < 240:  # max 4 horas
            pares.append((ini, mejor))
            fines_usados.add(mejor_idx)

    return pares


def _analizar_pausas(
    marcas_dia: list[Marca],
    llegada: Optional[time],
    turno_inicio: Optional[time],
    es_nocturno: bool,
) -> tuple[list[PausaResultado], str]:
    """Analiza todas las pausas del día y retorna resultados + estado general."""
    pares = _emparejar_pausas(marcas_dia)
    tipo = _determinar_tipo_turno(llegada, turno_inicio, es_nocturno)
    reglas = _reglas_pausas(tipo, len(pares))

    resultados: list[PausaResultado] = []
    estado_general = "OK"

    if not pares and not reglas:
        return [], "OK"

    # Verificar pausa de 30 min obligatoria
    tiene_30_obligatoria = any(r["obligatoria"] for r in reglas)
    if not pares and tiene_30_obligatoria:
        resultados.append(PausaResultado(
            inicio=time(0, 0), fin=time(0, 0),
            duracion_min=0, esperado_min=30, tolerancia_min=TOL_30,
            exceso_min=-30, es_obligatoria=True, estado="FALTA",
        ))
        return resultados, "EXCESO"

    # Asignar reglas a pausas ordenadas por duración
    pares_con_dur = [(ini, fin, _duration_minutes(ini, fin)) for ini, fin in pares]
    # Asignar la regla de 30 min a la pausa más larga, 15 min a la más corta
    pares_con_dur_sorted = sorted(pares_con_dur, key=lambda x: x[2])

    for idx, (ini, fin, dur) in enumerate(pares_con_dur_sorted):
        if idx < len(reglas):
            regla = reglas[idx]
        else:
            # Pausa extra sin regla específica → comparar con 30 min
            regla = {"duracion": 30, "tolerancia": TOL_30, "obligatoria": False}

        exceso = dur - regla["duracion"]

        if exceso > regla["tolerancia"]:
            estado = "EXCESO"
            if estado_general != "EXCESO":
                estado_general = "EXCESO"
        elif exceso > 0:
            estado = "TOLERANCIA"
            if estado_general == "OK":
                estado_general = "TOLERANCIA"
        elif exceso < -regla["tolerancia"] and regla["obligatoria"]:
            estado = "FALTA"
            estado_general = "EXCESO"
        else:
            estado = "OK"

        resultados.append(PausaResultado(
            inicio=ini, fin=fin, duracion_min=round(dur, 1),
            esperado_min=regla["duracion"], tolerancia_min=regla["tolerancia"],
            exceso_min=round(exceso, 1), es_obligatoria=regla["obligatoria"],
            estado=estado,
        ))

    # Pausas sin par (P15 sin P25)
    n_inicios = sum(1 for m in marcas_dia if m.cod == "P15")
    if n_inicios > len(pares):
        for _ in range(n_inicios - len(pares)):
            resultados.append(PausaResultado(
                inicio=time(0, 0), fin=time(0, 0),
                duracion_min=0, esperado_min=0, tolerancia_min=0,
                exceso_min=0, es_obligatoria=False, estado="SIN_PAR",
            ))
        if estado_general == "OK":
            estado_general = "TOLERANCIA"

    return resultados, estado_general


# ---------------------------------------------------------------------------
# Lógica de turno (entrada / salida)
# ---------------------------------------------------------------------------

def _analizar_turno(
    llegada: Optional[time],
    salida: Optional[time],
    turno: Optional[TurnoDay],
) -> tuple[float, float, str, str]:
    """
    Retorna (atraso_min, extra_min, estado_entrada, estado_salida).
    atraso_min > 0 = llegó tarde
    extra_min > 0 = salió tarde (hizo extra)
    """
    if turno is None or turno.hora_inicio is None:
        return 0.0, 0.0, "SIN_TURNO", "SIN_TURNO"

    es_noct = turno.es_nocturno

    # Entrada
    if llegada is None:
        atraso = 0.0
        est_entrada = "SIN_MARCA"
    else:
        diff = _diff_minutes(llegada, turno.hora_inicio, es_noct)
        if diff > TURNO_TOL:
            atraso = round(diff - TURNO_TOL, 1)
            est_entrada = "ATRASO"
        elif diff < -TURNO_TOL:
            atraso = round(diff + TURNO_TOL, 1)
            est_entrada = "ANTICIPADO"
        else:
            atraso = 0.0
            est_entrada = "OK"

    # Salida
    if salida is None or turno.hora_fin is None:
        extra = 0.0
        est_salida = "SIN_MARCA"
    else:
        diff = _diff_minutes(salida, turno.hora_fin, es_noct)
        if diff > TURNO_TOL:
            extra = round(diff - TURNO_TOL, 1)
            est_salida = "EXTRA"
        elif diff < -TURNO_TOL:
            extra = round(diff + TURNO_TOL, 1)
            est_salida = "ANTICIPADO"
        else:
            extra = 0.0
            est_salida = "OK"

    return atraso, extra, est_entrada, est_salida


# ---------------------------------------------------------------------------
# Función principal de análisis
# ---------------------------------------------------------------------------

def analizar(
    marcas: list[Marca],
    turnos: list[TurnoDay],
) -> list[RegistroDia]:
    """
    Cruza marcas reales con turnos planificados y retorna resultados por
    colaborador × día.
    """
    # Índice turnos por (codigo, fecha)
    turno_idx: dict[tuple[int, date], TurnoDay] = {}
    for t in turnos:
        turno_idx[(t.codigo, t.fecha)] = t

    # Agrupar marcas por (nro_personal, fecha)
    from collections import defaultdict
    grupos: dict[tuple[str, date], list[Marca]] = defaultdict(list)
    for m in marcas:
        grupos[(m.nro_personal, m.fecha)].append(m)

    resultados: list[RegistroDia] = []

    for (nro, fecha), marcas_dia in sorted(grupos.items()):
        marcas_dia.sort(key=lambda m: m.hora)
        primera = marcas_dia[0]

        # Llegada y salida reales
        llegadas = [m.hora for m in marcas_dia if m.cod == "P10"]
        salidas = [m.hora for m in marcas_dia if m.cod == "P20"]
        llegada = min(llegadas) if llegadas else None
        salida = max(salidas) if salidas else None

        # Buscar turno: primero por nro_personal exacto, luego por código
        turno: Optional[TurnoDay] = turno_idx.get((int(nro) if nro.isdigit() else 0, fecha))

        turno_raw = turno.raw_turno if turno else "—"
        turno_inicio = turno.hora_inicio if turno else None
        turno_fin = turno.hora_fin if turno else None
        es_nocturno = turno.es_nocturno if turno else False

        # Pausas
        pausas, est_col = _analizar_pausas(marcas_dia, llegada, turno_inicio, es_nocturno)

        # Turno
        atraso, extra, est_ent, est_sal = _analizar_turno(llegada, salida, turno)

        # Alertas
        alertas: list[str] = []
        for p in pausas:
            if p.estado == "FALTA":
                alertas.append("⚠ Falta colación obligatoria de 30 min")
            elif p.estado == "EXCESO":
                alertas.append(f"🔴 Exceso en colación: +{p.exceso_min} min (esperado {p.esperado_min} min)")
            elif p.estado == "SIN_PAR":
                alertas.append("⚠ Marca de inicio pausa sin fin registrado")
        if est_ent == "ATRASO":
            alertas.append(f"🕐 Atraso en entrada: {atraso} min")
        if est_sal == "ANTICIPADO":
            alertas.append(f"🏃 Salida anticipada: {abs(extra)} min")

        resultados.append(RegistroDia(
            rut=primera.rut, nro_personal=nro,
            nombre=primera.nombre, cargo=primera.cargo, seccion=primera.seccion,
            fecha=fecha,
            turno_raw=turno_raw, turno_inicio=turno_inicio,
            turno_fin=turno_fin, es_nocturno=es_nocturno,
            llegada=llegada, salida=salida,
            atraso_min=atraso, extra_min=extra,
            estado_entrada=est_ent, estado_salida=est_sal,
            pausas=pausas, alertas=alertas,
            estado_colacion=est_col,
        ))

    return resultados
