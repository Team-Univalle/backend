from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event, Subtask
from .serializers import EventSerializer, SubtaskSerializer, TodaySerializer


def usuario_actual_id(request):
    """Sprint 1: siempre el usuario demo. Con login (US-06) se cambia por el usuario autenticado."""
    return settings.DEMO_USER_ID


class EventListCreateView(generics.ListCreateAPIView):
    """GET /events -> lista los eventos del usuario. POST /events -> crea un evento."""

    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(user_id=usuario_actual_id(self.request)).order_by('event_date')

    def perform_create(self, serializer):
        serializer.save(user_id=usuario_actual_id(self.request))


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET, PATCH y DELETE /events/<id>. Al eliminar un evento se eliminan sus subtareas (cascada)."""

    serializer_class = EventSerializer
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        return Event.objects.filter(user_id=usuario_actual_id(self.request))


class SubtaskListCreateView(generics.ListCreateAPIView):
    """GET /events/<id>/subtasks -> subtareas del evento. POST -> crea una subtarea en ese evento."""

    serializer_class = SubtaskSerializer

    def get_event(self):
        # 404 si el evento no existe o no es del usuario
        return get_object_or_404(Event, pk=self.kwargs['event_id'], user_id=usuario_actual_id(self.request))

    def get_queryset(self):
        return Subtask.objects.filter(event=self.get_event()).order_by('target_date')

    def create(self, request, *args, **kwargs):
        self.event = self.get_event()  # primero buscar el evento, después validar los datos
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(event=self.event, status='Pendiente')  # toda subtarea nueva empieza Pendiente


class SubtaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET, PATCH y DELETE /subtasks/<id> (solo subtareas de eventos del usuario)."""

    serializer_class = SubtaskSerializer
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        return Subtask.objects.filter(event__user_id=usuario_actual_id(self.request))

class TodayListNoExecute(APIView):
    """GET/HOY ->TAREAS NO EJECUTADAS EN EL DIA"""

    def get(self, request):
        # 404 si el evento no existe o no es del usuario
        today=timezone.now().localdate()

        subtask=(
            Subtask.objects
            .filter(event__user_id=usuario_actual_id(request))
            .exclude(status='Ejecutada')
            .select_related('event')
            .order_by('target_date', 'estimated_hours')
        )

        overdue=subtask.filter(target_date__lt=today)
        today_subtask=subtask.filter(target_date=today)
        upcoming=subtask.filter(target_date__gt=today)

        return Response({
                'vencidas': TodaySerializer(overdue, many=True).data,
                'hoy': TodaySerializer(today_subtask, many=True).data,
                'proximas': TodaySerializer(upcoming, many=True).data,
            })