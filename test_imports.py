"""test_imports.py - Verifica imports nuevos."""
import sys, traceback
sys.path.insert(0, r"C:\Users\jrami60\OneDrive - Walmart Inc\Escritorio\Proyectos VsCode\Marcaciones")

print("1. exporters...", flush=True)
try:
    import exporters
    print("   OK", flush=True)
except Exception:
    traceback.print_exc()

print("2. main + rutas...", flush=True)
try:
    import main
    routes = [r.path for r in main.app.routes]
    print("   OK rutas:", routes, flush=True)
except Exception:
    traceback.print_exc()

print("DONE", flush=True)
