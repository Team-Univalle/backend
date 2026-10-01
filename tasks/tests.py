from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.conf import settings
from django.http import Http404
from django.test import SimpleTestCase

from .models import Event
from .serializers import SubtaskSerializer

class EstimatedHoursTest(SimpleTestCase):
    """HU-02: estimated_hours debe ser un número mayor que 0."""

    def validar(self, horas):
        datos = {'name': 'Reservar salón', 'target_date': '2026-12-01', 'estimated_hours': horas}
        return SubtaskSerializer(data=datos)

    def test_horas_validas(self):
        self.assertTrue(self.validar(2).is_valid())
        self.assertTrue(self.validar('1.5').is_valid())

    def test_horas_en_cero(self):
        s = self.validar(0)
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)

    def test_horas_negativas(self):
        s = self.validar(-2)
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)

    def test_horas_no_numericas(self):
        s = self.validar('abc')
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)


class TodayEndpointTest(SimpleTestCase):
    """Pruebas para GET /hoy sin modificar la base de datos real."""

    def setUp(self):
        self.today = date(2026, 10, 1)

        event = SimpleNamespace(
            id='event-1',
            name='Evento de prueba',
        )

        self.overdue = self.create_subtask(
            identifier='subtask-1',
            event=event,
            name='Subtarea vencida',
            target_date=date(2026, 9, 30),
            estimated_hours='3.00',
        )

        self.today_short = self.create_subtask(
            identifier='subtask-2',
            event=event,
            name='Subtarea corta de hoy',
            target_date=date(2026, 10, 1),
            estimated_hours='1.00',
        )

        self.today_long = self.create_subtask(
            identifier='subtask-3',
            event=event,
            name='Subtarea larga de hoy',
            target_date=date(2026, 10, 1),
            estimated_hours='2.00',
        )

        self.upcoming = self.create_subtask(
            identifier='subtask-4',
            event=event,
            name='Subtarea próxima',
            target_date=date(2026, 10, 5),
            estimated_hours='4.00',
        )

    def create_subtask(
        self,
        identifier,
        event,
        name,
        target_date,
        estimated_hours,
    ):
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
            patch(
                'tasks.views.Subtask.objects.filter',
                return_value=queryset,
            ) as initial_filter,
            patch(
                'tasks.views.timezone.localdate',
                return_value=self.today,
            ),
            patch('tasks.views.get_object_or_404') as event_lookup,
        ):
            if event_error is not None:
                event_lookup.side_effect = event_error

            response = self.client.get(f'/today{query}')

        return response, initial_filter, event_lookup

    def test_returns_subtasks_classified_by_date(self):
        queryset = self.prepare_queryset()

        response, _, _ = self.request_today(queryset)

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            [item['name'] for item in data['vencidas']],
            ['Subtarea vencida'],
        )

        self.assertEqual(
            [item['name'] for item in data['hoy']],
            [
                'Subtarea corta de hoy',
                'Subtarea larga de hoy',
            ],
        )

        self.assertEqual(
            [item['name'] for item in data['proximas']],
            ['Subtarea próxima'],
        )

    def test_includes_event_name(self):
        queryset = self.prepare_queryset()

        response, _, _ = self.request_today(queryset)
        data = response.json()

        all_subtasks = (
            data['vencidas'] +
            data['hoy'] +
            data['proximas']
        )

        for subtask in all_subtasks:
            self.assertEqual(
                subtask['event_name'],
                'Evento de prueba',
            )

    def test_filters_user_status_and_order(self):
        queryset = self.prepare_queryset()

        _, initial_filter, _ = self.request_today(queryset)

        initial_filter.assert_called_once_with(
            event__user_id=settings.DEMO_USER_ID,
        )

        queryset.exclude.assert_called_once_with(
            status='Ejecutada',
        )

        queryset.select_related.assert_called_once_with('event')

        queryset.order_by.assert_called_once_with(
            'target_date',
            'estimated_hours',
        )

        queryset.filter.assert_has_calls([
            call(target_date__lt=self.today),
            call(target_date=self.today),
            call(target_date__gt=self.today),
        ])

    def test_filters_by_event(self):
        queryset = self.prepare_queryset()

        response, _, event_lookup = self.request_today(
            queryset,
            query='?event_id=event-1',
        )

        self.assertEqual(response.status_code, 200)
        event_lookup.assert_called_once_with(
            Event,
            pk='event-1',
            user_id=settings.DEMO_USER_ID,
        )
        queryset.filter.assert_any_call(event_id='event-1')

    def test_filters_by_status(self):
        queryset = self.prepare_queryset()

        response, _, event_lookup = self.request_today(
            queryset,
            query='?status=Pospuesta',
        )

        self.assertEqual(response.status_code, 200)
        event_lookup.assert_not_called()
        queryset.filter.assert_any_call(status='Pospuesta')

    def test_combines_event_and_status_filters(self):
        queryset = self.prepare_queryset()

        response, _, event_lookup = self.request_today(
            queryset,
            query='?event_id=event-1&status=Pendiente',
        )

        self.assertEqual(response.status_code, 200)
        event_lookup.assert_called_once_with(
            Event,
            pk='event-1',
            user_id=settings.DEMO_USER_ID,
        )
        queryset.filter.assert_any_call(event_id='event-1')
        queryset.filter.assert_any_call(status='Pendiente')

    def test_rejects_event_from_another_user(self):
        queryset = self.prepare_queryset()

        response, initial_filter, event_lookup = self.request_today(
            queryset,
            query='?event_id=foreign-event',
            event_error=Http404,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {'error': 'No encontramos lo que buscas.'},
        )
        event_lookup.assert_called_once_with(
            Event,
            pk='foreign-event',
            user_id=settings.DEMO_USER_ID,
        )
        initial_filter.assert_not_called()

    def test_rejects_invalid_status_with_global_error_format(self):
        queryset = self.prepare_queryset()

        response, initial_filter, event_lookup = self.request_today(
            queryset,
            query='?status=Ejecutada',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            'error': 'Revisa los campos marcados.',
            'fields': {
                'status': 'El estado debe ser Pendiente o Pospuesta.',
            },
        })
        event_lookup.assert_not_called()
        initial_filter.assert_not_called()

    def test_preserves_date_and_estimated_hours_order(self):
        queryset = self.prepare_queryset()

        response, _, _ = self.request_today(
            queryset,
            query='?event_id=event-1&status=Pendiente',
        )

        self.assertEqual(response.status_code, 200)
        queryset.order_by.assert_called_once_with(
            'target_date',
            'estimated_hours',
        )
        self.assertEqual(
            [item['name'] for item in response.json()['hoy']],
            ['Subtarea corta de hoy', 'Subtarea larga de hoy'],
        )
