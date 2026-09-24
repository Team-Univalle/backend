import uuid

from django.db import models


def generar_id():
    return str(uuid.uuid4())


class Profile(models.Model):
    """Usuario de la app (tabla profiles de Supabase)."""

    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(max_length=150)
    email = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        managed = False  # la tabla ya existe en Supabase, Django no la modifica
        db_table = 'profiles'

    def __str__(self):
        return self.name


class Event(models.Model):
    """Evento que crea un organizador (tabla events de Supabase)."""

    id = models.CharField(primary_key=True, max_length=50, default=generar_id)
    user = models.ForeignKey(Profile, on_delete=models.CASCADE, db_column='user_id', related_name='events')
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=100)
    client = models.CharField(max_length=150, blank=True, null=True)
    event_date = models.DateField()
    event_time = models.TimeField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    deadline = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        managed = False  # la tabla ya existe en Supabase, Django no la modifica
        db_table = 'events'

    def __str__(self):
        return self.name


class Subtask(models.Model):
    """Subtarea logística de un evento (tabla subtasks de Supabase)."""

    ESTADOS = [('Pendiente', 'Pendiente'), ('Ejecutada', 'Ejecutada'), ('Pospuesta', 'Pospuesta')]

    id = models.CharField(primary_key=True, max_length=50, default=generar_id)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, db_column='event_id', related_name='subtasks')
    name = models.CharField(max_length=200)
    target_date = models.DateField()
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=20, choices=ESTADOS, default='Pendiente')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        managed = False  # la tabla ya existe en Supabase, Django no la modifica
        db_table = 'subtasks'

    def __str__(self):
        return self.name
