"""Datos ficticios exclusivamente en django_crud_api.qa_settings."""
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from tasks.models import Profile, Event, Subtask


class Command(BaseCommand):
    def handle(self, *args, **options):
        if connection.vendor != 'sqlite' or str(settings.DATABASES['default']['NAME']).split('\\')[-1].split('/')[-1] != 'qa.sqlite3':
            raise CommandError('Solo se permite en la base qa.sqlite3 local aislada.')
        existing = connection.introspection.table_names()
        with connection.schema_editor() as editor:
            for model in (Profile, Event, Subtask):
                if model._meta.db_table not in existing:
                    editor.create_model(model)
        today = timezone.localdate()
        for identifier, limit in [('qa-a', 6), ('qa-b', 4)]:
            profile, _ = Profile.objects.get_or_create(id=identifier, defaults={'name': 'Organizador QA ' + identifier[-1].upper(), 'email': identifier + '@example.invalid', 'password_hash': make_password('Qa-Testing-Only!2026'), 'daily_limit_hours': limit})
            event, _ = Event.objects.get_or_create(id='evento-' + identifier, defaults={'user': profile, 'name': 'Boda Laura & Andrés' if identifier == 'qa-a' else 'Evento QA B', 'type': 'Social', 'event_date': today + timedelta(days=30)})
            for key, name, hours, offset in [('gestion', 'Buscar proveedor de catering', 2, 0), ('carga', 'Reservar salón', 5, 2), ('vencida', 'Confirmar fotógrafo', 1, -1)]:
                Subtask.objects.get_or_create(id=identifier + '-' + key, defaults={'event': event, 'name': name, 'estimated_hours': hours, 'target_date': today + timedelta(days=offset)})
        Profile.objects.get_or_create(id='qa-empty', defaults={'name': 'Organizador QA sin gestiones', 'email': 'qa-empty@example.invalid', 'password_hash': make_password('Qa-Testing-Only!2026')})
        self.stdout.write('Datos QA locales preparados. Nunca se conectó a Supabase.')
        self.stdout.write('Cuentas ficticias: qa-a@example.invalid, qa-b@example.invalid, qa-empty@example.invalid. Clave de QA: Qa-Testing-Only!2026')
