from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .authentication import create_access_token
from .models import Profile, Event, Subtask


@override_settings(JWT_SECRET='isolated-capacity-tests-secret-not-for-production')
class CapacityPersistenceTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.day = self.today + timedelta(days=2)
        self.a = Profile.objects.create(id='qa-a', name='QA A', email='qa-a@example.invalid', password_hash=make_password('testing-only'))
        self.b = Profile.objects.create(id='qa-b', name='QA B', email='qa-b@example.invalid', password_hash=make_password('testing-only'), daily_limit_hours=4)
        self.event = Event.objects.create(user=self.a, name='Evento QA', type='Social', event_date=self.today + timedelta(days=30))
        self.other_event = Event.objects.create(user=self.a, name='Otro evento QA', type='Social', event_date=self.event.event_date)
        self.foreign = Event.objects.create(user=self.b, name='Evento B', type='Social', event_date=self.event.event_date)
        self.load = self.task(self.other_event, 5, self.day)
        self.item = self.task(self.event, 2, self.today)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.a.id))

    def task(self, event, hours, day, status='Pendiente'):
        return Subtask.objects.create(event=event, name='Gestión QA', estimated_hours=hours, target_date=day, status=status)

    def patch(self, data):
        return self.client.patch('/subtasks/' + self.item.id, data, format='json')

    def check(self, day=None, hours=2):
        return self.client.get('/conflicts', {'date': day or self.day, 'subtask_id': self.item.id, 'estimated_hours': hours})

    def test_conflict_5_plus_2_rejects_without_partial_changes(self):
        result = self.check().json()
        self.assertEqual((result['planned_hours'], result['task_hours'], result['total_hours'], result['excess']), (5, 2, 7, 1))
        response = self.patch({'target_date': str(self.day), 'name': 'No guardar', 'status': 'Pospuesta'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'overload_conflict')
        self.item.refresh_from_db()
        self.assertEqual((self.item.target_date, self.item.name, self.item.status), (self.today, 'Gestión QA', 'Pendiente'))

    def test_equality_4_plus_2_persists_and_regroups(self):
        self.load.estimated_hours = 4
        self.load.save()
        self.assertFalse(self.check().json()['conflict'])
        self.assertEqual(self.patch({'target_date': str(self.day)}).status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.target_date, self.day)
        self.assertEqual(self.client.get('/subtasks/' + self.item.id).json()['target_date'], str(self.day))
        data = self.client.get('/today', {'event_id': self.event.id, 'status': 'Pendiente'}).json()
        self.assertEqual([t['id'] for t in data['proximas']], [self.item.id])
        self.assertEqual(data['hoy'], [])

    def test_reduce_2_to_1_excludes_self_and_persists(self):
        self.item.target_date = self.day
        self.item.save()
        self.assertEqual(self.check(hours=1).json()['total_hours'], 6)
        self.assertEqual(self.patch({'estimated_hours': 1}).status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estimated_hours, Decimal('1'))
        self.assertEqual(self.item.name, 'Gestión QA')
        self.assertEqual(self.item.status, 'Pendiente')

    def test_insufficient_reduction_and_invalid_hours(self):
        self.item.target_date = self.day
        self.item.save()
        for hours, expected in [(1.5, 409), (0, 400), (-1, 400), ('text', 400), ('1.001', 400)]:
            with self.subTest(hours=hours):
                self.assertEqual(self.patch({'estimated_hours': hours}).status_code, expected)
                self.item.refresh_from_db()
                self.assertEqual(self.item.estimated_hours, Decimal('2'))

    def test_executed_and_foreign_excluded_custom_limit_no_double_count(self):
        self.a.daily_limit_hours = 8
        self.a.save()
        self.task(self.event, 15, self.day, 'Ejecutada')
        self.task(self.foreign, 15, self.day)
        self.assertEqual(self.check().json()['total_hours'], 7)
        self.assertEqual(self.patch({'target_date': str(self.day)}).status_code, 200)
        self.assertEqual(self.check().json()['total_hours'], 7)

    def test_concurrent_change_after_check_is_revalidated(self):
        self.load.estimated_hours = 4
        self.load.save()
        self.assertFalse(self.check().json()['conflict'])
        self.task(self.event, 1, self.day)
        self.assertEqual(self.patch({'target_date': str(self.day)}).status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.target_date, self.today)

    def test_daily_limit_boundaries_isolation_reload(self):
        self.assertEqual(self.client.get('/daily-limit').json()['daily_limit_hours'], 6)
        for value in [1, 16, 6]:
            self.assertEqual(self.client.put('/daily-limit', {'daily_limit_hours': value}, format='json').status_code, 200)
            self.a.refresh_from_db()
            self.assertEqual(self.a.daily_limit_hours, value)
        for value in [0, 17, '', 'text', 1.5]:
            response = self.client.put('/daily-limit', {'daily_limit_hours': value}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('daily_limit_hours', response.json()['fields'])
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.b.id))
        self.assertEqual(self.client.get('/daily-limit').json()['daily_limit_hours'], 4)
        self.b.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual((self.a.daily_limit_hours, self.b.daily_limit_hours), (6, 4))

    def test_foreign_resources_are_404_and_absent_from_today(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.b.id))
        for endpoint in ['/events/' + self.event.id, '/subtasks/' + self.item.id, '/events/' + self.event.id + '/subtasks']:
            self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.patch({'estimated_hours': 1}).status_code, 404)
        self.assertEqual(self.client.get('/today', {'event_id': self.event.id}).status_code, 404)
        self.assertEqual(self.client.get('/conflicts', {'date': self.day, 'subtask_id': self.item.id}).status_code, 404)
        self.assertNotIn(self.item.id, str(self.client.get('/today').json()))

    def test_invalid_dates_and_no_token(self):
        for value in ['', 'not-date', '2026-02-30', str(self.today - timedelta(days=1))]:
            self.assertEqual(self.patch({'target_date': value}).status_code, 400)
        self.assertEqual(self.client.get('/conflicts', {'date': 'invalid'}).status_code, 400)
        self.client.credentials()
        for endpoint in ['/daily-limit', '/today', '/conflicts?date=' + str(self.day)]:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()['error'], 'Tu sesión expiró o no has iniciado sesión.')

    def test_today_order_and_groups_remain_correct(self):
        past = self.task(self.event, 1, self.today - timedelta(days=1))
        short = self.task(self.event, 1, self.today)
        data = self.client.get('/today', {'event_id': self.event.id}).json()
        self.assertEqual(data['vencidas'][0]['id'], past.id)
        self.assertEqual([t['id'] for t in data['hoy']], [short.id, self.item.id])
        self.assertTrue(all(t['event_name'] == 'Evento QA' for t in data['hoy']))

    def test_postponing_does_not_move_or_drop_existing_load(self):
        self.task(self.other_event, 5, self.today)
        response = self.patch({'status': 'Pospuesta'})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.target_date, self.today)
        self.assertEqual(self.item.estimated_hours, 2)
        self.assertEqual(self.item.status, 'Pospuesta')
        result = self.client.get('/conflicts', {'date': self.today}).json()
        self.assertEqual(result['total_hours'], 7)
        self.assertTrue(result['conflict'])
