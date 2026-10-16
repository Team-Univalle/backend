from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .authentication import create_access_token
from .models import Event, Profile, Subtask
from .progress import calculate_progress


class CalculateProgressTests(SimpleTestCase):
    """HU-10: misma regla de porcentaje que el frontend (calcularProgreso)."""

    def test_sin_subtareas_es_0(self):
        self.assertEqual(calculate_progress(0, 0), 0)

    def test_parcial_redondea_al_entero(self):
        self.assertEqual(calculate_progress(7, 4), 57)
        self.assertEqual(calculate_progress(3, 2), 67)

    def test_completo_es_100(self):
        self.assertEqual(calculate_progress(3, 3), 100)

    def test_extremos(self):
        self.assertEqual(calculate_progress(200, 199), 99)
        self.assertEqual(calculate_progress(300, 1), 1)


@override_settings(JWT_SECRET='isolated-progress-tests-secret-not-for-production')
class EventProgressApiTests(TestCase):
    """GET /events y /events/<id> devuelven el progreso sin romper la serialización."""

    def setUp(self):
        today = timezone.localdate()
        self.user = Profile.objects.create(
            id='qa-progress', name='QA', email='qa-progress@example.invalid', password_hash=make_password('testing-only')
        )
        self.event = Event.objects.create(user=self.user, name='Boda QA', type='boda', event_date=today + timedelta(days=30))
        self.empty = Event.objects.create(user=self.user, name='Vacío QA', type='social', event_date=today + timedelta(days=40))
        for status, day in [
            ('Ejecutada', today - timedelta(days=3)),
            ('Ejecutada', today + timedelta(days=1)),
            ('Pendiente', today - timedelta(days=1)),
            ('Pospuesta', today + timedelta(days=2)),
        ]:
            Subtask.objects.create(event=self.event, name='Gestión QA', estimated_hours=1, target_date=day, status=status)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.user.id))

    def test_lista_de_eventos_incluye_progreso(self):
        response = self.client.get('/events')
        self.assertEqual(response.status_code, 200)
        by_id = {event['id']: event for event in response.json()}
        boda = by_id[self.event.id]
        self.assertEqual(
            (boda['total_subtasks'], boda['completed_subtasks'], boda['overdue_subtasks'], boda['progress_percentage']),
            (4, 2, 1, 50),
        )
        vacio = by_id[self.empty.id]
        self.assertEqual((vacio['total_subtasks'], vacio['progress_percentage']), (0, 0))

    def test_detalle_crear_y_editar_no_fallan(self):
        detail = self.client.get('/events/' + self.event.id)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['progress_percentage'], 50)

        created = self.client.post(
            '/events',
            {'name': 'Nuevo QA', 'type': 'social', 'event_date': str(timezone.localdate() + timedelta(days=10))},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['total_subtasks'], 0)

        patched = self.client.patch('/events/' + self.event.id, {'name': 'Boda QA editada'}, format='json')
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()['completed_subtasks'], 2)

    def test_progreso_no_es_editable(self):
        self.client.patch('/events/' + self.event.id, {'progress_percentage': 100}, format='json')
        self.assertEqual(self.client.get('/events/' + self.event.id).json()['progress_percentage'], 50)
