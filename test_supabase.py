"""test_supabase.py — Prueba de conectividad con Supabase desde red Walmart."""
import httpx

URL  = "https://laipzggyiqxttnqrrfwf.supabase.co/rest/v1/stores?select=*"
KEY  = "sb_publishable_jdtV_11xjewTlGBqapziPg_dq-r9Mz_"
HDR  = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
PROXY = "http://sysproxy.wal-mart.com:8080"

print("=" * 50)

# 1) Sin proxy
print("[1] Probando SIN proxy (trust_env=False)...")
try:
    r = httpx.get(URL, headers=HDR, trust_env=False, timeout=10)
    print("    STATUS:", r.status_code)
    print("    BODY  :", r.text[:150])
except Exception as e:
    print("    ERROR :", repr(e))

print()

# 2) Con proxy explícito
print("[2] Probando CON proxy sysproxy:8080...")
try:
    r = httpx.get(URL, headers=HDR, proxy=PROXY, timeout=15)
    print("    STATUS:", r.status_code)
    print("    BODY  :", r.text[:150])
except Exception as e:
    print("    ERROR :", repr(e))

print()

# 3) Con proxy + verify=False (por si hay SSL inspection)
print("[3] Probando CON proxy + verify=False...")
try:
    r = httpx.get(URL, headers=HDR, proxy=PROXY, verify=False, timeout=15)
    print("    STATUS:", r.status_code)
    print("    BODY  :", r.text[:150])
except Exception as e:
    print("    ERROR :", repr(e))

print("=" * 50)
print("DONE")
