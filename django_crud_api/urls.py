import logging

from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from tasks.views import (
    EventDetailView,
    EventListCreateView,
    LoginView,
    MeView,
    RegisterView,
    SubtaskDetailView,
    SubtaskListCreateView,
    TodayListNoExecute,
    ConflictCheckView,
    DailyLimitView,
)


logger = logging.getLogger(__name__)


def health_check(request):
    """GET /health: pública (sin sesión). Comprueba la base sin exponer detalles técnicos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({
            'status': 'ok',
            'database': 'connected',
            'message': 'Backend funcionando',
        })
    except Exception:  # noqa: BLE001 - base caída o mal configurada: 503 controlado, el detalle va al log
        logger.exception('Health check: sin conexión con la base de datos')
        return JsonResponse({
            'status': 'error',
            'database': 'disconnected',
            'message': 'Backend activo, pero sin conexión con Supabase',
        }, status=503)

urlpatterns = [
    path('', health_check),
    path('health', health_check),
    path('admin/', admin.site.urls),
    path('login', LoginView.as_view()),
    path('register', RegisterView.as_view(), name='register'),
    path('me', MeView.as_view()),
    path('today', TodayListNoExecute.as_view()),
    
    path('events', EventListCreateView.as_view()),
    path('events/<str:pk>', EventDetailView.as_view()),
    path('events/<str:event_id>/subtasks', SubtaskListCreateView.as_view()),
    path('subtasks/<str:pk>', SubtaskDetailView.as_view()),

    path('conflicts', ConflictCheckView.as_view()),
    path('daily-limit', DailyLimitView.as_view()),

    # Swagger: /api/docs/ y /api/schema/ (rutas oficiales) y /docs, /schema (las anteriores, se mantienen).
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('docs', SpectacularSwaggerView.as_view(url_name='schema')),
]

# Errores fuera de DRF (URL inexistente, fallos en middleware...) con el mismo formato JSON de la API.
# OJO: Django solo usa estos handlers con DEBUG=False; con DEBUG=True responde su página HTML de depuración.
handler400 = 'tasks.exceptions.handler400'
handler403 = 'tasks.exceptions.handler403'
handler404 = 'tasks.exceptions.handler404'
handler500 = 'tasks.exceptions.handler500'
