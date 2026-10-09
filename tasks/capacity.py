"""Regla única de capacidad. Decimal evita errores en la frontera total == límite."""
from decimal import Decimal
from django.db.models import Sum
from .models import Subtask


def evaluate_capacity(profile, target_date, hours=Decimal('0'), exclude_id=None, status='Pendiente'):
    tasks = Subtask.objects.filter(event__user_id=profile.id, target_date=target_date).exclude(status='Ejecutada')
    if exclude_id:
        tasks = tasks.exclude(pk=exclude_id)
    planned = tasks.aggregate(total=Sum('estimated_hours'))['total'] or Decimal('0')
    task_hours = Decimal('0') if status == 'Ejecutada' else Decimal(str(hours))
    total = planned + task_hours
    limit = Decimal(str(profile.daily_limit_hours))
    excess = max(Decimal('0'), total - limit)
    return {
        'date': str(target_date), 'conflict': total > limit,
        'planned_hours': float(planned), 'task_hours': float(task_hours),
        'total_hours': float(total), 'daily_limit': int(limit), 'excess': float(excess),
        'message': f'Quedarías con {total.normalize():f}h de gestión planificadas (límite {limit.normalize():f}h)',
        'options': ['mover_a_otro_dia', 'reducir_horas', 'posponer'] if excess else [],
    }
