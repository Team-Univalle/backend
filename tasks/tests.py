from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.conf import settings
from django.test import SimpleTestCase

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
            if 'target_date__lt' in filters:
                return [self.overdue]

            if 'target_date' in filters:
                return [self.today_short, self.today_long]

            if 'target_date__gt' in filters:
                return [self.upcoming]

            return []

        queryset.filter.side_effect = filter_by_date
        return queryset

    def request_today(self, queryset):
        with (
            patch(
                'tasks.views.Subtask.objects.filter',
                return_value=queryset,
            ) as initial_filter,
            patch(
                'tasks.views.timezone.localdate',
                return_value=self.today,
            ),
        ):
            response = self.client.get('/hoy')

        return response, initial_filter

    def test_returns_subtasks_classified_by_date(self):
        queryset = self.prepare_queryset()

        response, _ = self.request_today(queryset)

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

        response, _ = self.request_today(queryset)
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

        _, initial_filter = self.request_today(queryset)

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