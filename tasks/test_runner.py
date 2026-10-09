from django.db import connection
from django.test.runner import DiscoverRunner
from .models import Profile, Event, Subtask


class LocalDatabaseRunner(DiscoverRunner):
    """Tablas unmanaged en una BD efímera; nunca toca Supabase."""
    def setup_databases(self, **kwargs):
        config = super().setup_databases(**kwargs)
        with connection.schema_editor() as editor:
            for model in (Profile, Event, Subtask):
                editor.create_model(model)
        return config
