"""Usuario demo y datos de ejemplo para producción (historia de despliegue, subtarea 4).

Uso:
    DEMO_PASSWORD='...' python manage.py seed_demo            # crea lo que falte (idempotente)
    python manage.py seed_demo --refrescar                     # vuelve las fechas/estados al día de hoy
    DEMO_PASSWORD='...' python manage.py seed_demo --actualizar-password

Variables de entorno:
    DEMO_EMAIL     correo del usuario demo (por defecto demo@organiza-eventos.app)
    DEMO_PASSWORD  contraseña del demo; solo se pide al crearlo o con --actualizar-password.
                   Nunca se escribe en el código: se guarda con hash (make_password).

Idempotente: los IDs se generan en la aplicación de forma determinista a partir del correo demo
(uuid5), así que ejecutar el comando dos veces no duplica nada. Solo toca datos del usuario demo.

Las fechas son relativas al día en que se ejecuta (H = hoy). Con --refrescar se recalculan, útil
antes de una demostración en otro día.

CASO DE SOBRECARGA (límite del demo: 6 h por día):
    El día H+3 ya tiene 5 h pendientes:
        "Confirmar catering" (3 h, Boda Laura & Andrés)
        "Coordinar sonido y proyector" (2 h, Lanzamiento App Univalle)
    Reprograma "Confirmar fotógrafo" (2 h, hoy en H+5, evento Boda Laura & Andrés) al día H+3:
        5 h + 2 h = 7 h > 6 h  ->  conflicto de sobrecarga (exceso 1 h), PATCH /subtasks/<id> responde 409.
    Para resolverlo: moverla a otro día con espacio, reducirla a 1 h o posponerla.
"""
import os
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tasks.models import Event, Profile, Subtask

DEMO_EMAIL_POR_DEFECTO = 'demo@organiza-eventos.app'
DEMO_NAMESPACE = uuid.UUID('6f1c2a4e-9b7d-4f3a-8c21-5d0e9a7b3c11')
LIMITE_DEMO = 6

# (clave, nombre, tipo, cliente, lugar, días hasta el evento, gestiones)
# gestión: (clave, nombre, días desde hoy, horas, estado, nota)
EVENTOS = [
    ('boda', 'Boda Laura & Andrés', 'boda', 'Laura Gómez', 'Hacienda El Bosque', 20, [
        ('menu', 'Prueba de menú', -3, '2', 'Ejecutada', 'Se eligió el menú de tres tiempos.'),
        ('salon', 'Reservar salón', -2, '1', 'Pendiente', None),
        ('invitaciones', 'Enviar invitaciones', 0, '2', 'Pendiente', None),
        ('catering', 'Confirmar catering', 3, '3', 'Pendiente', None),
        ('fotografo', 'Confirmar fotógrafo', 5, '2', 'Pendiente', None),
    ]),
    ('cumple', 'Cumpleaños 15 de Sofía', 'cumpleanos', 'Marta Ruiz', 'Salón Los Robles', 30, [
        ('decoracion', 'Cotizar decoración', -1, '1', 'Pospuesta', 'El proveedor no ha enviado la cotización.'),
        ('dj', 'Contratar DJ', 0, '1.5', 'Pendiente', None),
        ('invitaciones', 'Enviar invitaciones digitales', 7, '0.5', 'Pendiente', None),
        ('pastel', 'Pedir el pastel', 10, '1', 'Ejecutada', 'Se pagó el 50% del pastel.'),
    ]),
    ('lanzamiento', 'Lanzamiento App Univalle', 'corporativo', 'Univalle', 'Edificio 331, Univalle Meléndez', 14, [
        ('auditorio', 'Reservar auditorio', -4, '1', 'Ejecutada', 'Auditorio confirmado por correo.'),
        ('sonido', 'Coordinar sonido y proyector', 3, '2', 'Pendiente', None),
        ('material', 'Imprimir material promocional', 8, '1.5', 'Pendiente', None),
        ('asistentes', 'Confirmar lista de asistentes', 12, '1', 'Ejecutada', None),
    ]),
    # Evento sin gestiones: muestra el estado vacío de la barra de progreso.
    ('taller', 'Taller de fotografía', 'social', 'Club de Fotografía', 'Biblioteca Mario Carvajal', 25, []),
]


def demo_id(email, *partes):
    """ID generado por la aplicación, estable para el mismo correo (permite re-ejecutar sin duplicar)."""
    return str(uuid.uuid5(DEMO_NAMESPACE, ':'.join([email, *partes])))


class Command(BaseCommand):
    help = 'Crea (o completa) el usuario demo y datos de ejemplo, incluido un caso de sobrecarga. Idempotente.'

    def add_arguments(self, parser):
        parser.add_argument('--refrescar', action='store_true',
                            help='Recalcula fechas, estados y notas de los datos demo según el día de hoy.')
        parser.add_argument('--actualizar-password', action='store_true',
                            help='Cambia la contraseña del demo por la de DEMO_PASSWORD.')

    def handle(self, *args, **options):
        email = os.getenv('DEMO_EMAIL', DEMO_EMAIL_POR_DEFECTO).strip().lower()
        password = os.getenv('DEMO_PASSWORD', '')
        refrescar = options['refrescar']
        today = timezone.localdate()
        creados = {'perfil': 0, 'eventos': 0, 'gestiones': 0}

        with transaction.atomic():
            profile = self._perfil(email, password, options['actualizar_password'], creados)

            for clave, nombre, tipo, cliente, lugar, dias_evento, gestiones in EVENTOS:
                datos_evento = {
                    'user': profile, 'name': nombre, 'type': tipo, 'client': cliente,
                    'location': lugar, 'event_date': today + timedelta(days=dias_evento),
                }
                event, creado = Event.objects.get_or_create(id=demo_id(email, clave), defaults=datos_evento)
                creados['eventos'] += creado
                if refrescar and not creado:
                    Event.objects.filter(pk=event.pk).update(event_date=datos_evento['event_date'])

                for g_clave, g_nombre, dias, horas, estado, nota in gestiones:
                    datos = {
                        'event': event, 'name': g_nombre, 'target_date': today + timedelta(days=dias),
                        'estimated_hours': Decimal(horas), 'status': estado, 'notes': nota,
                    }
                    subtask, creada = Subtask.objects.get_or_create(
                        id=demo_id(email, clave, g_clave), defaults=datos
                    )
                    creados['gestiones'] += creada
                    if refrescar and not creada:
                        Subtask.objects.filter(pk=subtask.pk).update(
                            **{k: v for k, v in datos.items() if k != 'event'}
                        )

        conflicto = Subtask.objects.get(id=demo_id(email, 'boda', 'fotografo'))
        dia_cargado = today + timedelta(days=3)
        self.stdout.write(self.style.SUCCESS(
            f"Usuario demo listo: {email} (límite {profile.daily_limit_hours} h/día). "
            f"Nuevos: {creados['perfil']} perfil, {creados['eventos']} eventos, {creados['gestiones']} gestiones."
            + (' Fechas refrescadas al día de hoy.' if refrescar else '')
        ))
        self.stdout.write(
            f'Caso de sobrecarga: reprograma "Confirmar fotógrafo" (id {conflicto.id}) al {dia_cargado:%Y-%m-%d}; '
            'ese día ya tiene 5 h pendientes y quedaría en 7 h (límite 6 h).'
        )

    def _perfil(self, email, password, actualizar_password, creados):
        profile_id = demo_id(email, 'perfil')
        existente = Profile.objects.filter(email__iexact=email).first()
        if existente and existente.id != profile_id:
            raise CommandError(
                f'{email} ya pertenece a un perfil que no es el demo. Usa otro DEMO_EMAIL; no se modificó nada.'
            )

        if existente is None or actualizar_password:
            if not password:
                raise CommandError('Define DEMO_PASSWORD en el entorno (no se guarda en el código).')
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError('DEMO_PASSWORD no es segura: ' + ' '.join(exc.messages)) from None

        if existente is None:
            creados['perfil'] = 1
            return Profile.objects.create(
                id=profile_id, name='Usuario Demo', email=email,
                password_hash=make_password(password), daily_limit_hours=LIMITE_DEMO,
            )
        if actualizar_password:
            existente.password_hash = make_password(password)
            existente.save(update_fields=['password_hash'])
        return existente
