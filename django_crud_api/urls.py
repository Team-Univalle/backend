from django.contrib import admin
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from tasks.views import EventDetailView, EventListCreateView, SubtaskDetailView, SubtaskListCreateView


def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({
            'status': 'ok',
            'database': 'connected',
            'message': 'Backend funcionando',
        })
    except DatabaseError:
        return JsonResponse({
            'status': 'error',
            'database': 'disconnected',
            'message': 'Backend activo, pero sin conexión con Supabase',
        }, status=503)

urlpatterns = [
    path('', health_check),
    path('health', health_check),
    path('admin/', admin.site.urls),
    path('events', EventListCreateView.as_view()),
    path('events/<str:pk>', EventDetailView.as_view()),
    path('events/<str:event_id>/subtasks', SubtaskListCreateView.as_view()),
    path('subtasks/<str:pk>', SubtaskDetailView.as_view()),
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('docs', SpectacularSwaggerView.as_view(url_name='schema')),
]
