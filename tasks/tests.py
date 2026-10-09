import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import jwt
from django.contrib.auth.hashers import check_password, make_password
from django.core.management import call_command
from django.http import Http404
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from .authentication import create_access_token
from .models import Event
from .serializers import SubtaskSerializer
from .views import EventDetailView, EventListCreateView, SubtaskDetailView


TEST_JWT_SECRET = 'test-secret-that-is-not-used-outside-the-test-suite'


def profile_stub(
    identifier='user-b',
    email='user-b@example.com',
    password='StrongPassword!2026',
):
    return SimpleNamespace(
        id=identifier,
        name='Usuario de prueba',
        email=email,
        password_hash=make_password(password),
        is_authenticated=True,
        daily_limit_hours=6,
    )


class EstimatedHoursTest(SimpleTestCase):
    """HU-02: estimated_hours debe ser un número mayor que 0."""

    def validar(self, horas):
        datos = {'name': 'Reservar salón', 'target_date': '2026-12-01', 'estimated_hours': horas}
        return SubtaskSerializer(data=datos)

    def test_horas_validas(self):
        self.assertTrue(self.validar(2).is_valid())
        self.assertTrue(self.validar('1.5').is_valid())

    def test_horas_en_cero(self):
        serializer = self.validar(0)
        self.assertFalse(serializer.is_valid())
        self.assertIn('estimated_hours', serializer.errors)

    def test_horas_negativas(self):
        serializer = self.validar(-2)
        self.assertFalse(serializer.is_valid())
        self.assertIn('estimated_hours', serializer.errors)

    def test_horas_no_numericas(self):
        serializer = self.validar('abc')
        self.assertFalse(serializer.is_valid())
        self.assertIn('estimated_hours', serializer.errors)


@override_settings(JWT_SECRET=TEST_JWT_SECRET, JWT_EXPIRATION_HOURS=8)
class AuthenticationTest(SimpleTestCase):
    def login(self, profile, email='user-b@example.com', password='StrongPassword!2026'):
        queryset = Mock()
        queryset.first.return_value = profile
        with patch('tasks.views.Profile.objects.filter', return_value=queryset):
            return self.client.post(
                '/login',
                data=json.dumps({'email': email, 'password': password}),
                content_type='application/json',
            )

    def test_successful_login_returns_eight_hour_jwt_and_user(self):
        profile = profile_stub()
        response = self.login(profile)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        payload = jwt.decode(data['token'], TEST_JWT_SECRET, algorithms=['HS256'])
        self.assertEqual(payload['sub'], profile.id)
        self.assertEqual(payload['exp'] - payload['iat'], 8 * 60 * 60)
        self.assertEqual(data['user'], {
            'id': profile.id,
            'name': profile.name,
            'email': profile.email,
            'daily_limit_hours': 6,
        })

    def test_wrong_password_and_unknown_email_share_the_same_error(self):
        wrong_password = self.login(profile_stub(), password='WrongPassword!2026')
        missing_profile = self.login(None, email='missing@example.com')
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(missing_profile.status_code, 401)
        self.assertEqual(wrong_password.json(), {'error': 'Credenciales inválidas'})
        self.assertEqual(missing_profile.json(), wrong_password.json())

    def test_empty_login_fields_use_global_validation_format(self):
        response = self.client.post(
            '/login',
            data=json.dumps({'email': '', 'password': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            'error': 'Revisa los campos marcados.',
            'fields': {
                'email': 'El correo es obligatorio.',
                'password': 'La contraseña es obligatoria.',
            },
        })

    def test_me_returns_authenticated_user(self):
        profile = profile_stub()
        token = create_access_token(profile.id)
        with patch('tasks.authentication.Profile.objects.get', return_value=profile):
            response = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], profile.id)

    def test_request_without_token_returns_global_401(self):
        response = self.client.get('/me')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {
            'error': 'Tu sesión expiró o no has iniciado sesión.',
        })

    def test_expired_token_returns_global_401(self):
        now = timezone.now()
        token = jwt.encode(
            {'sub': 'user-b', 'iat': now - timedelta(hours=9), 'exp': now - timedelta(hours=1)},
            TEST_JWT_SECRET,
            algorithm='HS256',
        )
        response = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {
            'error': 'Tu sesión expiró o no has iniciado sesión.',
        })

    def test_tampered_token_returns_global_401(self):
        token = create_access_token('user-b') + 'altered'
        response = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {
            'error': 'Tu sesión expiró o no has iniciado sesión.',
        })


class CreateUserCommandTest(SimpleTestCase):
    def test_command_hashes_password_and_generates_id(self):
        manager_filter = Mock()
        manager_filter.exists.return_value = False
        created = {}

        def capture_create(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(**kwargs)

        with (
            patch('tasks.management.commands.crear_usuario.Profile.objects.filter', return_value=manager_filter),
            patch('tasks.management.commands.crear_usuario.Profile.objects.create', side_effect=capture_create),
        ):
            call_command(
                'crear_usuario',
                'Integrante Prueba',
                'INTEGRANTE@example.com',
                password='StrongPassword!2026',
                stdout=StringIO(),
            )

        self.assertTrue(created['id'])
        self.assertEqual(created['email'], 'integrante@example.com')
        self.assertNotEqual(created['password_hash'], 'StrongPassword!2026')
        self.assertTrue(check_password('StrongPassword!2026', created['password_hash']))


@override_settings(JWT_SECRET=TEST_JWT_SECRET, JWT_EXPIRATION_HOURS=8)
class TodayEndpointTest(SimpleTestCase):
    """Pruebas para GET /today sin modificar Supabase."""

    def setUp(self):
        self.today = date(2026, 10, 1)
        self.user = profile_stub()
        self.token = create_access_token(self.user.id)
        event = SimpleNamespace(id='event-1', name='Evento de prueba')
        self.overdue = self.create_subtask(
            'subtask-1', event, 'Subtarea vencida', date(2026, 9, 30), '3.00'
        )
        self.today_short = self.create_subtask(
            'subtask-2', event, 'Subtarea corta de hoy', self.today, '1.00'
        )
        self.today_long = self.create_subtask(
            'subtask-3', event, 'Subtarea larga de hoy', self.today, '2.00'
        )
        self.upcoming = self.create_subtask(
            'subtask-4', event, 'Subtarea próxima', date(2026, 10, 5), '4.00'
        )

    def create_subtask(self, identifier, event, name, target_date, estimated_hours):
        return SimpleNamespace(
            id=identifier,
            event_id=event.id,
            event=event,
            name=name,
            target_date=target_date,
            estimated_hours=Decimal(estimated_hours),
            status='Pendiente',
            created_at=None,
            updated_at=None,
        )

    def prepare_queryset(self):
        queryset = Mock()
        queryset.exclude.return_value = queryset
        queryset.select_related.return_value = queryset
        queryset.order_by.return_value = queryset

        def filter_by_date(**filters):
            if 'event_id' in filters or 'status' in filters:
                return queryset
            if 'target_date__lt' in filters:
                return [self.overdue]
            if 'target_date' in filters:
                return [self.today_short, self.today_long]
            if 'target_date__gt' in filters:
                return [self.upcoming]
            return []

        queryset.filter.side_effect = filter_by_date
        return queryset

    def request_today(self, queryset, query='', event_error=None):
        with (
            patch('tasks.authentication.Profile.objects.get', return_value=self.user),
            patch('tasks.views.Subtask.objects.filter', return_value=queryset) as initial_filter,
            patch('tasks.views.timezone.localdate', return_value=self.today),
            patch('tasks.views.get_object_or_404') as event_lookup,
        ):
            if event_error is not None:
                event_lookup.side_effect = event_error
            response = self.client.get(
                f'/today{query}',
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )
        return response, initial_filter, event_lookup

    def test_returns_subtasks_classified_by_date(self):
        response, _, _ = self.request_today(self.prepare_queryset())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item['name'] for item in data['vencidas']], ['Subtarea vencida'])
        self.assertEqual(
            [item['name'] for item in data['hoy']],
            ['Subtarea corta de hoy', 'Subtarea larga de hoy'],
        )
        self.assertEqual([item['name'] for item in data['proximas']], ['Subtarea próxima'])

    def test_includes_event_name(self):
        response, _, _ = self.request_today(self.prepare_queryset())
        data = response.json()
        for subtask in data['vencidas'] + data['hoy'] + data['proximas']:
            self.assertEqual(subtask['event_name'], 'Evento de prueba')

    def test_filters_authenticated_user_status_and_order(self):
        queryset = self.prepare_queryset()
        _, initial_filter, _ = self.request_today(queryset)
        initial_filter.assert_called_once_with(event__user_id=self.user.id)
        queryset.exclude.assert_called_once_with(status='Ejecutada')
        queryset.select_related.assert_called_once_with('event')
        queryset.order_by.assert_called_once_with('target_date', 'estimated_hours')
        queryset.filter.assert_has_calls([
            call(target_date__lt=self.today),
            call(target_date=self.today),
            call(target_date__gt=self.today),
        ])

    def test_filters_by_event(self):
        queryset = self.prepare_queryset()
        response, _, event_lookup = self.request_today(queryset, '?event_id=event-1')
        self.assertEqual(response.status_code, 200)
        event_lookup.assert_called_once_with(Event, pk='event-1', user_id=self.user.id)
        queryset.filter.assert_any_call(event_id='event-1')

    def test_filters_by_status(self):
        queryset = self.prepare_queryset()
        response, _, event_lookup = self.request_today(queryset, '?status=Pospuesta')
        self.assertEqual(response.status_code, 200)
        event_lookup.assert_not_called()
        queryset.filter.assert_any_call(status='Pospuesta')

    def test_combines_event_and_status_filters(self):
        queryset = self.prepare_queryset()
        response, _, event_lookup = self.request_today(
            queryset, '?event_id=event-1&status=Pendiente'
        )
        self.assertEqual(response.status_code, 200)
        event_lookup.assert_called_once_with(Event, pk='event-1', user_id=self.user.id)
        queryset.filter.assert_any_call(event_id='event-1')
        queryset.filter.assert_any_call(status='Pendiente')

    def test_rejects_event_from_another_user(self):
        queryset = self.prepare_queryset()
        response, initial_filter, event_lookup = self.request_today(
            queryset, '?event_id=foreign-event', event_error=Http404
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'No encontramos lo que buscas.'})
        event_lookup.assert_called_once_with(Event, pk='foreign-event', user_id=self.user.id)
        initial_filter.assert_not_called()

    def test_rejects_invalid_status_with_global_error_format(self):
        queryset = self.prepare_queryset()
        response, initial_filter, event_lookup = self.request_today(
            queryset, '?status=Ejecutada'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            'error': 'Revisa los campos marcados.',
            'fields': {'status': 'El estado debe ser Pendiente o Pospuesta.'},
        })
        event_lookup.assert_not_called()
        initial_filter.assert_not_called()

    def test_preserves_date_and_estimated_hours_order(self):
        queryset = self.prepare_queryset()
        response, _, _ = self.request_today(
            queryset, '?event_id=event-1&status=Pendiente'
        )
        self.assertEqual(response.status_code, 200)
        queryset.order_by.assert_called_once_with('target_date', 'estimated_hours')
        self.assertEqual(
            [item['name'] for item in response.json()['hoy']],
            ['Subtarea corta de hoy', 'Subtarea larga de hoy'],
        )


@override_settings(JWT_SECRET=TEST_JWT_SECRET, JWT_EXPIRATION_HOURS=8)
class UserIsolationTest(SimpleTestCase):
    def setUp(self):
        self.user_b = profile_stub(identifier='user-b')
        self.request = SimpleNamespace(user=self.user_b)
        self.token = create_access_token(self.user_b.id)

    def test_event_and_subtask_querysets_are_scoped_to_user_b(self):
        event_list_queryset = Mock()
        event_list_queryset.order_by.return_value = event_list_queryset
        with patch('tasks.views.Event.objects.filter', return_value=event_list_queryset) as event_filter:
            view = EventListCreateView()
            view.request = self.request
            view.get_queryset()
            event_filter.assert_called_once_with(user_id=self.user_b.id)

        with patch('tasks.views.Event.objects.filter') as event_filter:
            view = EventDetailView()
            view.request = self.request
            view.get_queryset()
            event_filter.assert_called_once_with(user_id=self.user_b.id)

        with patch('tasks.views.Subtask.objects.filter') as subtask_filter:
            view = SubtaskDetailView()
            view.request = self.request
            view.get_queryset()
            subtask_filter.assert_called_once_with(event__user_id=self.user_b.id)

    def test_user_b_cannot_edit_event_or_subtask_from_user_a(self):
        with (
            patch('tasks.authentication.Profile.objects.get', return_value=self.user_b),
            patch.object(EventDetailView, 'get_object', side_effect=Http404),
        ):
            event_response = self.client.patch(
                '/events/event-from-user-a',
                data=json.dumps({'name': 'Intento'}),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )

        with (
            patch('tasks.authentication.Profile.objects.get', return_value=self.user_b),
            patch.object(SubtaskDetailView, 'get_object', side_effect=Http404),
        ):
            subtask_response = self.client.patch(
                '/subtasks/subtask-from-user-a',
                data=json.dumps({'name': 'Intento'}),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )

        self.assertEqual(event_response.status_code, 404)
        self.assertEqual(subtask_response.status_code, 404)
        self.assertEqual(event_response.json(), {'error': 'No encontramos lo que buscas.'})
        self.assertEqual(subtask_response.json(), {'error': 'No encontramos lo que buscas.'})
