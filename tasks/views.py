from django.conf import settings
from rest_framework import generics

from .models import Event
from .serializers import EventSerializer


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


class EventDetailView(generics.RetrieveAPIView):
    """GET /events/<id> -> detalle de un evento del usuario."""

    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(user_id=usuario_actual_id(self.request))
