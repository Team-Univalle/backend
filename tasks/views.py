from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
from datetime import timedelta
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import create_access_token
from .exceptions import InvalidCredentials, OverloadConflict
from .capacity import evaluate_capacity
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
    DailyLimitSerializer,
    CapacityQuerySerializer,
    ConflictResponseSerializer,
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
    
    def get_serializer_context(self):

        context = super().get_serializer_context()

        try:
            context['event'] = self.get_event()
        except Exception:
            pass

        return context

    def perform_create(self, serializer):
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=self.request.user.id)
            values = serializer.validated_data
            capacity = evaluate_capacity(profile, values['target_date'], values['estimated_hours'])
            if capacity['conflict']:
                raise OverloadConflict(capacity)
            serializer.save(event=self.event, status='Pendiente')


class SubtaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET, PATCH y DELETE /subtasks/<id> (solo subtareas de eventos del usuario)."""

    serializer_class = SubtaskSerializer
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        return Subtask.objects.filter(event__user_id=usuario_actual_id(self.request))

    def update(self, request, *args, **kwargs):
        self.get_object()  # 404 antes de adquirir el mutex para recursos ajenos.
        # El perfil actúa como mutex por organizador, incluso entre eventos distintos.
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=request.user.id)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            changed = any(key in values and values[key] != getattr(instance, key)
                          for key in ('target_date', 'estimated_hours', 'status'))
            if changed:
                capacity = evaluate_capacity(profile, values.get('target_date', instance.target_date),
                    values.get('estimated_hours', instance.estimated_hours), instance.id,
                    values.get('status', instance.status))
                only_postponing = (values.get('status') == 'Pospuesta'
                    and values.get('target_date', instance.target_date) == instance.target_date
                    and values.get('estimated_hours', instance.estimated_hours) == instance.estimated_hours
                    and instance.status != 'Ejecutada')
                if capacity['conflict'] and not only_postponing:
                    raise OverloadConflict(capacity)
            serializer.save()
            return Response(serializer.data)


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

class DailyLimitView(APIView):

    @extend_schema(
        summary='Consultar límite diario',
        responses={200: DailyLimitSerializer}
    )
    def get(self, request):

        return Response({
            'daily_limit_hours': request.user.daily_limit_hours
        })

    @extend_schema(
        summary='Actualizar límite diario',
        request=DailyLimitSerializer,
        responses={200: DailyLimitSerializer}
    )
    def patch(self, request):

        serializer = DailyLimitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=request.user.id)
            profile.daily_limit_hours = serializer.validated_data['daily_limit_hours']
            profile.save(update_fields=['daily_limit_hours'])
            request.user.daily_limit_hours = profile.daily_limit_hours

        return Response({
            'daily_limit_hours': request.user.daily_limit_hours
        })

    @extend_schema(request=DailyLimitSerializer, responses={200: DailyLimitSerializer, 400: GlobalErrorSerializer})
    def put(self, request):
        return self.patch(request)

def calcular_carga_diaria(user, fecha):

    total = (
        Subtask.objects
        .filter(
            event__user=user,
            target_date=fecha
        )
        .exclude(status='Ejecutada')
        .aggregate(
            total=Sum('estimated_hours')
        )
    )

    return float(total["total"] or 0)

class ConflictCheckView(APIView):

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Fecha a analizar.'
            ),
            OpenApiParameter(name='subtask_id', type=OpenApiTypes.STR, description='Gestión propia que se sustituye, sin contarla dos veces.'),
            OpenApiParameter(name='estimated_hours', type=OpenApiTypes.NUMBER, description='Horas propuestas, > 0, hasta dos decimales.'),
            OpenApiParameter(name='status', enum=['Pendiente', 'Pospuesta', 'Ejecutada']),
        ],
        responses={200: ConflictResponseSerializer, 400: GlobalErrorSerializer, 401: GlobalErrorSerializer, 404: GlobalErrorSerializer},
    )
    
    def get(self, request):
        serializer = CapacityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        item = None
        if values.get('subtask_id'):
            item = get_object_or_404(Subtask, pk=values['subtask_id'], event__user_id=request.user.id)
        hours = values.get('estimated_hours', item.estimated_hours if item else 0)
        status = values.get('status', item.status if item else 'Pendiente')
        capacity = evaluate_capacity(request.user, values['date'], hours, item.id if item else None, status)
        capacity['suggested_dates'] = []
        if item and capacity['conflict']:
            for offset in range(1, 15):
                candidate = max(values['date'], timezone.localdate()) + timedelta(days=offset)
                if candidate > item.event.event_date:
                    break
                result = evaluate_capacity(request.user, candidate, hours, item.id, status)
                if not result['conflict']:
                    capacity['suggested_dates'].append(result)
                if len(capacity['suggested_dates']) == 3:
                    break
        return Response(capacity)
