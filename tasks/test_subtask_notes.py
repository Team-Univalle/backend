from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .authentication import create_access_token
from .models import Event, Profile, Subtask


@override_settings(JWT_SECRET='isolated-subtask-notes-tests-secret-not-for-production')
class SubtaskNotesTests(TestCase):
    """HU-09: PATCH /subtasks/<id> guarda estado y nota opcional."""

    def setUp(self):
        today = timezone.localdate()
        self.user = Profile.objects.create(
            id='qa-notes', name='QA', email='qa-notes@example.invalid', password_hash=make_password('testing-only')
        )
        event = Event.objects.create(user=self.user, name='Evento QA', type='social', event_date=today + timedelta(days=30))
        self.item = Subtask.objects.create(event=event, name='Pagar salón', estimated_hours=1, target_date=today + timedelta(days=2))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.user.id))

    def patch(self, data):
        return self.client.patch('/subtasks/' + self.item.id, data, format='json')

    def test_sin_nota_por_defecto(self):
        self.assertIsNone(self.client.get('/subtasks/' + self.item.id).json()['notes'])

    def test_ejecutar_con_nota_persiste(self):
        response = self.patch({'status': 'Ejecutada', 'notes': 'Se pagó el 50% del depósito del salón'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['notes'], 'Se pagó el 50% del depósito del salón')
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.notes), ('Ejecutada', 'Se pagó el 50% del depósito del salón'))

    def test_posponer_con_nota_y_nueva_fecha(self):
        new_date = timezone.localdate() + timedelta(days=5)
        response = self.patch({'status': 'Pospuesta', 'notes': 'Proveedor sin respuesta', 'target_date': str(new_date)})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.notes, self.item.target_date), ('Pospuesta', 'Proveedor sin respuesta', new_date))

    def test_nota_se_sanitiza(self):
        response = self.patch({'notes': '  <b>Entregado</b>​ '})
        self.assertEqual(response.json()['notes'], 'Entregado')

    def test_nota_vacia_se_guarda_como_null(self):
        self.patch({'notes': 'algo'})
        self.assertIsNone(self.patch({'notes': '   '}).json()['notes'])

    def test_nota_de_mas_de_500_caracteres_da_400(self):
        response = self.patch({'notes': 'a' * 501})
        self.assertEqual(response.status_code, 400)
        self.assertIn('notes', response.json()['fields'])
        self.assertEqual(self.patch({'notes': 'a' * 500}).status_code, 200)
