"""Progreso de un evento a partir de sus subtareas."""

from django.db.models import Count, Q

ESTADO_COMPLETADA = "Ejecutada"


def calculate_progress(total, completed):
    """Porcentaje de subtareas ejecutadas con un decimal. Sin subtareas devuelve 0.0 (sin dividir por cero)."""
    if not total:
        return 0.0
    return round(completed * 100 / total, 1)


def annotate_progress(queryset):
    """Agrega total_subtasks y completed_subtasks a cada evento en una sola consulta (evita N+1)."""
    return queryset.annotate(
        total_subtasks=Count("subtasks"),
        completed_subtasks=Count(
            "subtasks", filter=Q(subtasks__status=ESTADO_COMPLETADA)
        ),
    )


def event_counts(event):
    """(total, ejecutadas) de un evento; usa las anotaciones si existen y si no consulta la base."""
    total = getattr(event, "total_subtasks", None)
    completed = getattr(event, "completed_subtasks", None)
    if total is None or completed is None:
        total = event.subtasks.count()
        completed = event.subtasks.filter(status=ESTADO_COMPLETADA).count()
    return total, completed
