"""
test_startup.py — Simula el arranque en produccion (sin DEV_MODE).
Verifica imports y creacion de la app FastAPI.
"""
import sys
import os

# Simular ambiente de produccion
os.environ.pop("DEV_MODE", None)
os.environ["SUPABASE_URL"] = "https://laipzggyiqxttnqrrfwf.supabase.co"
os.environ["SUPABASE_KEY"] = "sb_publishable_jdtV_11xjewTlGBqapziPg_dq-r9Mz_"
os.environ["SECRET_KEY"]   = "test-secret"

print("1. Importando database...", flush=True)
try:
    import database
    print("   OK - DEV_MODE:", database.DEV_MODE, flush=True)
except Exception as e:
    print("   ERROR:", e, flush=True); sys.exit(1)

print("2. Importando auth...", flush=True)
try:
    import auth
    print("   OK", flush=True)
except Exception as e:
    print("   ERROR:", e, flush=True); sys.exit(1)

print("3. Importando parsers...", flush=True)
try:
    import parsers
    print("   OK", flush=True)
except Exception as e:
    print("   ERROR:", e, flush=True); sys.exit(1)

print("4. Importando analyzer...", flush=True)
try:
    import analyzer
    print("   OK", flush=True)
except Exception as e:
    print("   ERROR:", e, flush=True); sys.exit(1)

print("5. Importando main (crea app FastAPI)...", flush=True)
try:
    import main
    rutas = [r.path for r in main.app.routes]
    print("   OK - Rutas registradas:", rutas, flush=True)
except Exception as e:
    import traceback
    print("   ERROR:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

print("\n✅ Todo OK - la app arranca correctamente en modo produccion", flush=True)
