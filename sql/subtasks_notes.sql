-- HU-09: notas de ejecución en las gestiones. Idempotente: se puede ejecutar varias veces.
-- Ejecutar en Supabase ANTES de desplegar el backend que usa Subtask.notes.

BEGIN;

ALTER TABLE public.subtasks
    ADD COLUMN IF NOT EXISTS notes text;

-- Red de seguridad: el backend ya limita las notas a 500 caracteres.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subtasks_notes_max_length'
    ) THEN
        ALTER TABLE public.subtasks
            ADD CONSTRAINT subtasks_notes_max_length CHECK (char_length(notes) <= 500);
    END IF;
END $$;

COMMIT;
