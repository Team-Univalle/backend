from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import create_access_token
from .exceptions import InvalidCredentials
from .models import Event, Profile, Subtask, generar_id
from .serializers import (
    EventSerializer,
    GlobalErrorSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
    SubtaskSerializer,
    TodayResponseSerializer,
    TodaySerializer,
    TodayValidationErrorSerializer,
)


def usuario_actual_id(request):
    return request.user.id


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 400: GlobalErrorSerializer, 401: GlobalErrorSerializer},
        auth=[],
        summary='Iniciar sesión',
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']
        profile = Profile.objects.filter(email__iexact=email).first()

        if profile is None or not check_password(password, profile.password_hash):
            raise InvalidCredentials()

        return Response({
            'token': create_access_token(profile.id),
            'user': ProfileSerializer(profile).data,
        })


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: LoginResponseSerializer, 400: GlobalErrorSerializer},
        auth=[],
        summary='Registrar nuevo usuario',
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data['name'].strip()
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        profile = Profile.objects.create(
            id=generar_id(),
            name=name,
            email=email,
            password_hash=make_password(password),
        )

        return Response({
            'token': create_access_token(profile.id),
            'user': ProfileSerializer(profile).data,
        }, status=201)


class MeView(APIView):
    @extend_schema(responses={200: ProfileSerializer, 401: GlobalErrorSerializer}, summary='Usuario actual')
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)


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
        return get_object_or_404(Event, pk=self.kwargs['event_id'], user_id=usuario_actual_id(self.request))

    def get_queryset(self):
        return Subtask.objects.filter(event=self.get_event()).order_by('target_date')

    def create(self, request, *args, **kwargs):
        self.event = self.get_event()
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(event=self.event, status='Pendiente')


class SubtaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET, PATCH y DELETE /subtasks/<id> (solo subtareas de eventos del usuario)."""

    serializer_class = SubtaskSerializer
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        return Subtask.objects.filter(event__user_id=usuario_actual_id(self.request))


class TodayListNoExecute(APIView):
    """GET /today -> subtareas no ejecutadas, agrupadas por fecha."""

    VALID_STATUSES = {'Pendiente', 'Pospuesta'}

    @extend_schema(
        summary='Consultar subtareas de hoy',
        description=(
            'Devuelve las subtareas no ejecutadas del usuario actual agrupadas '
            'en vencidas, hoy y próximas. Los filtros pueden combinarse.'
        ),
        parameters=[
            OpenApiParameter(
                name='event_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description='ID de un evento perteneciente al usuario actual.',
            ),
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=['Pendiente', 'Pospuesta'],
                description='Estado de las subtareas que se desean consultar.',
            ),
        ],
        responses={
            200: TodayResponseSerializer,
            400: TodayValidationErrorSerializer,
            404: GlobalErrorSerializer,
        },
    )
    def get(self, request):
        today = timezone.localdate()
        user_id = usuario_actual_id(request)
        event_id = request.query_params.get('event_id')
        requested_status = request.query_params.get('status')

        if requested_status is not None and requested_status not in self.VALID_STATUSES:
            raise ValidationError({
                'status': 'El estado debe ser Pendiente o Pospuesta.',
            })

        if event_id is not None:
            get_object_or_404(Event, pk=event_id, user_id=user_id)

        subtasks = (
            Subtask.objects
            .filter(event__user_id=user_id)
            .exclude(status='Ejecutada')
        )

        if event_id is not None:
            subtasks = subtasks.filter(event_id=event_id)

        if requested_status is not None:
            subtasks = subtasks.filter(status=requested_status)

        subtasks = (
            subtasks
            .select_related('event')
            .order_by('target_date', 'estimated_hours')
        )

        resueltas_vencidas = subtasks.filter(target_date__lt=today)
        resueltas_hoy = subtasks.filter(target_date=today)
        resueltas_proximas = subtasks.filter(target_date__gt=today)

        return Response({
            'vencidas': TodaySerializer(resueltas_vencidas, many=True).data,
            'hoy': TodaySerializer(resueltas_hoy, many=True).data,
            'proximas': TodaySerializer(resueltas_proximas, many=True).data,
        })