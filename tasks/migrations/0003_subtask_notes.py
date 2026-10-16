from django.db import migrations, models


class Migration(migrations.Migration):
    """Solo actualiza el estado de Django: la tabla subtasks es unmanaged.

    La columna real se crea en Supabase con sql/subtasks_notes.sql.
    """

    dependencies = [
        ("tasks", "0002_subtask"),
    ]

    operations = [
        migrations.AddField(
            model_name="subtask",
            name="notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
