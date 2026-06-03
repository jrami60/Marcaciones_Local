import sys
sys.path.insert(0, '.')
from parsers import parse_marcas, parse_turnos

with open(r'C:/Users/jrami60/Downloads/Reporte Marcas 01.06.2026.XLSX', 'rb') as f:
    marcas = parse_marcas(f)
print(f'Marcas: {len(marcas)} registros')
print('Muestra:', marcas[0])

with open(r'C:/Users/jrami60/Downloads/ReporteTurnoResumen_929-La_Paloma(01_06_2026_a_05_07_2026) (4).xlsx', 'rb') as f:
    turnos = parse_turnos(f)
print(f'Turnos: {len(turnos)} registros')
t_validos = [t for t in turnos if t.hora_inicio]
print(f'Turnos con horario: {len(t_validos)}')
if t_validos:
    print('Muestra turno:', t_validos[0])

from analyzer import analizar
resultados = analizar(marcas, turnos)
print(f'Resultados: {len(resultados)} registros dia-colaborador')
if resultados:
    r = resultados[0]
    print(f'Primer: {r.nombre} | {r.fecha} | llegada={r.llegada} | pausas={len(r.pausas)} | col={r.estado_colacion} | entrada={r.estado_entrada}')
    for p in r.pausas:
        print(f'  Pausa: {p.inicio}->{p.fin} dur={p.duracion_min} esperado={p.esperado_min} exceso={p.exceso_min} estado={p.estado}')
