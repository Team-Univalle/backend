"""Progreso de un evento a partir de sus subtareas (HU-10)."""

from django.db.models import Count, Q
from django.utils import timezone

ESTADO_COMPLETADA = 'Ejecutada'


def calculate_progress(total, completed):
    """Porcentaje de subtareas ejecutadas, redondeado a entero. Sin subtareas devuelve 0 (sin dividir por cero).

    Nunca devuelve 100 si falta alguna ni 0 si ya hay alguna ejecutada (ej. 199 de 200 = 99).
    Es la misma regla que usa el frontend para que /progreso y /evento/:id coincidan.
    """
    if not total:
        return 0
    percentage = round(completed * 100 / total)
    if completed < total:
        percentage = min(percentage, 99)
    if completed > 0:
        percentage = max(percentage, 1)
    return percentage


def annotate_progress(queryset):
    """Agrega los conteos de subtareas a cada evento en una sola consulta (evita N+1)."""
    today = timezone.localdate()
    return queryset.annotate(
        total_subtasks=Count('subtasks'),
        completed_subtasks=Count('subtasks', filter=Q(subtasks__status=ESTADO_COMPLETADA)),
        overdue_subtasks=Count(
            'subtasks',
            filter=Q(subtasks__target_date__lt=today) & ~Q(subtasks__status=ESTADO_COMPLETADA),
        ),
    )


def event_counts(event):
    """(total, ejecutadas, vencidas) de un evento; usa las anotaciones si existen y si no consulta la base."""
    total = getattr(event, 'total_subtasks', None)
    completed = getattr(event, 'completed_subtasks', None)
    overdue = getattr(event, 'overdue_subtasks', None)
    if total is None or completed is None or overdue is None:
        subtasks = event.subtasks.all()
        total = subtasks.count()
        completed = subtasks.filter(status=ESTADO_COMPLETADA).count()
        overdue = subtasks.filter(target_date__lt=timezone.localdate()).exclude(status=ESTADO_COMPLETADA).count()
    return total, completed, overdue
