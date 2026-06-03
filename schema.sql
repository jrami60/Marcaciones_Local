-- ============================================================
-- Schema: Marcaciones La Paloma / Walmart Chile
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Tiendas
CREATE TABLE IF NOT EXISTS stores (
  id          SERIAL PRIMARY KEY,
  store_number TEXT NOT NULL UNIQUE,   -- '929', '670'
  store_name   TEXT NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Usuarios de la app (NO usa Supabase Auth)
CREATE TABLE IF NOT EXISTS app_users (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  store_id      INTEGER REFERENCES stores(id),
  is_admin      BOOLEAN DEFAULT FALSE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Sesiones activas
CREATE TABLE IF NOT EXISTS sessions (
  id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id    UUID REFERENCES app_users(id) ON DELETE CASCADE,
  token      TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de archivos cargados
CREATE TABLE IF NOT EXISTS uploads (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  store_id     INTEGER REFERENCES stores(id),
  user_id      UUID REFERENCES app_users(id),
  upload_type  TEXT NOT NULL,   -- 'marcas' | 'turnos'
  filename     TEXT NOT NULL,
  upload_date  DATE NOT NULL,
  record_count INTEGER,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Resultados de análisis (historial completo)
CREATE TABLE IF NOT EXISTS analysis_results (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  store_id         INTEGER REFERENCES stores(id),
  user_id          UUID REFERENCES app_users(id),
  result_date      DATE NOT NULL,
  filename_marcas  TEXT,
  filename_turnos  TEXT,
  total_records    INTEGER,
  result_json      JSONB NOT NULL,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Deshabilitar RLS (auth la maneja la app)
ALTER TABLE stores           DISABLE ROW LEVEL SECURITY;
ALTER TABLE app_users        DISABLE ROW LEVEL SECURITY;
ALTER TABLE sessions         DISABLE ROW LEVEL SECURITY;
ALTER TABLE uploads          DISABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_results DISABLE ROW LEVEL SECURITY;

-- Tiendas iniciales
INSERT INTO stores (store_number, store_name) VALUES
  ('929', 'La Paloma'),
  ('670', 'Local 670')
ON CONFLICT (store_number) DO NOTHING;
