from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Migra la columna heredada password a password_hash y elimina el texto plano.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'profiles'
            """)
            columns = {row[0] for row in cursor.fetchall()}

        if 'password_hash' not in columns:
            raise CommandError('Primero ejecuta sql/profile_auth.sql en Supabase.')

        if 'password' not in columns:
            self.stdout.write(self.style.SUCCESS('La contraseña heredada ya fue eliminada.'))
            return

        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SELECT id, password, password_hash FROM profiles')
            profiles = cursor.fetchall()

            for profile_id, legacy_password, password_hash in profiles:
                if not password_hash:
                    if not legacy_password:
                        raise CommandError(f'El perfil {profile_id} no tiene contraseña para migrar.')
                    cursor.execute(
                        'UPDATE profiles SET password_hash = %s WHERE id = %s',
                        [make_password(legacy_password), profile_id],
                    )

            cursor.execute("""
                SELECT COUNT(*) FROM profiles
                WHERE password_hash IS NULL OR password_hash = ''
            """)
            if cursor.fetchone()[0]:
                raise CommandError('Quedaron perfiles sin password_hash; no se eliminó password.')

            cursor.execute('ALTER TABLE profiles ALTER COLUMN password_hash SET NOT NULL')
            cursor.execute('ALTER TABLE profiles DROP COLUMN password')

        self.stdout.write(self.style.SUCCESS(
            f'Migración completada para {len(profiles)} perfiles; se eliminó la columna password.'
        ))
