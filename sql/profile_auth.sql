-- Ejecutar una sola vez en Supabase SQL Editor antes de desplegar el login.
-- Es idempotente: puede ejecutarse nuevamente sin duplicar columnas o índices.

BEGIN;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS password_hash varchar(128);

-- La tabla ya puede tener profiles_email_key. Este índice agrega además
-- unicidad sin distinguir mayúsculas y minúsculas.
CREATE UNIQUE INDEX IF NOT EXISTS profiles_email_ci_unique
    ON public.profiles (LOWER(email));

COMMIT;

-- Si la instalación tenía la columna heredada password con texto plano, ejecutar:
-- python manage.py migrar_passwords_profiles
-- Ese comando genera hashes con make_password, marca password_hash como NOT NULL
-- y elimina la columna password únicamente después de verificar la migración.
