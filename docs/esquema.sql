-- Esquema de la base de datos (Supabase / PostgreSQL) — Organizador de Eventos Independientes.
--
-- Los modelos de Django usan managed = False: Django NO crea ni modifica estas tablas.
-- Este script las crea en una base vacía. Ejecútalo a mano en Supabase > SQL Editor.
--
-- Es seguro en la base actual: solo crea lo que falta (IF NOT EXISTS) y no borra ni cambia datos.
-- Si una tabla ya existe con otra forma, NO se modifica; para eso están los parches de sql/:
--   sql/profile_auth.sql    (password_hash en profiles)
--   sql/subtasks_notes.sql  (notes en subtasks)
--
-- Fuente: tasks/models.py y la "Base técnica operativa" del proyecto.
-- daily_capacity y subtask_execution existen en el diseño, pero la API actual NO las usa:
--   el límite diario está en profiles.daily_limit_hours y la nota de ejecución en subtasks.notes.

BEGIN;

-- Usuarios. El id lo genera la aplicación (uuid como texto), no Supabase.
CREATE TABLE IF NOT EXISTS public.profiles (
    id                varchar(50)  PRIMARY KEY,
    name              varchar(150) NOT NULL,
    email             varchar(150) NOT NULL UNIQUE,
    password_hash     varchar(128) NOT NULL,
    daily_limit_hours integer      NOT NULL DEFAULT 6
                      CONSTRAINT profiles_daily_limit_range CHECK (daily_limit_hours BETWEEN 1 AND 16),
    created_at        timestamptz  DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS profiles_email_ci_unique ON public.profiles (LOWER(email));

-- Eventos de cada usuario. Al borrar el usuario se borran sus eventos.
CREATE TABLE IF NOT EXISTS public.events (
    id          varchar(50)  PRIMARY KEY,
    user_id     varchar(50)  NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
    name        varchar(150) NOT NULL,
    type        varchar(100) NOT NULL,
    client      varchar(150),
    event_date  date         NOT NULL,
    event_time  time,
    location    varchar(200),
    deadline    date,
    created_at  timestamptz  DEFAULT now(),
    updated_at  timestamptz  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_user_date_idx ON public.events (user_id, event_date);

-- Gestiones logísticas (subtareas). Al borrar el evento se borran sus gestiones.
CREATE TABLE IF NOT EXISTS public.subtasks (
    id               varchar(50)   PRIMARY KEY,
    event_id         varchar(50)   NOT NULL REFERENCES public.events (id) ON DELETE CASCADE,
    name             varchar(200)  NOT NULL,
    target_date      date          NOT NULL,
    estimated_hours  numeric(5, 2) NOT NULL CONSTRAINT subtasks_estimated_hours_positive CHECK (estimated_hours > 0),
    status           varchar(20)   NOT NULL DEFAULT 'Pendiente'
                     CONSTRAINT subtasks_status_valid CHECK (status IN ('Pendiente', 'Ejecutada', 'Pospuesta')),
    notes            text          CONSTRAINT subtasks_notes_max_length CHECK (char_length(notes) <= 500),
    created_at       timestamptz   DEFAULT now(),
    updated_at       timestamptz   DEFAULT now()
);
CREATE INDEX IF NOT EXISTS subtasks_event_idx ON public.subtasks (event_id);
CREATE INDEX IF NOT EXISTS subtasks_target_date_idx ON public.subtasks (target_date);

-- Capacidad por día (diseño original; la API usa profiles.daily_limit_hours). Estructura verificada en Supabase.
CREATE TABLE IF NOT EXISTS public.daily_capacity (
    id          varchar(50)  PRIMARY KEY,
    user_id     varchar(50)  NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
    date        date         NOT NULL,
    max_hours   numeric      NOT NULL DEFAULT 6 CONSTRAINT daily_capacity_max_hours_check CHECK (max_hours > 0),
    created_at  timestamptz  DEFAULT now(),
    CONSTRAINT daily_capacity_user_id_date_key UNIQUE (user_id, date)
);

-- Historial de ejecución (diseño original; la API guarda la última nota en subtasks.notes).
-- Estructura según la Base técnica: estado, fecha y nota. Verifica la tabla real antes de usarla.
CREATE TABLE IF NOT EXISTS public.subtask_execution (
    id           varchar(50)  PRIMARY KEY,
    subtask_id   varchar(50)  NOT NULL REFERENCES public.subtasks (id) ON DELETE CASCADE,
    status       varchar(20)  NOT NULL CONSTRAINT subtask_execution_status_valid CHECK (status IN ('Ejecutada', 'Pospuesta')),
    executed_at  date         NOT NULL DEFAULT CURRENT_DATE,
    note         text,
    created_at   timestamptz  DEFAULT now()
);

COMMIT;
