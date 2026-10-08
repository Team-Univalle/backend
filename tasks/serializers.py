from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers

from .models import Event, Profile, Subtask


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'id',
            'name',
            'email',
            'daily_limit_hours'
        ]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            'required': 'El correo es obligatorio.',
            'blank': 'El correo es obligatorio.',
            'invalid': 'El correo no tiene un formato válido.',
        },
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        error_messages={
            'required': 'La contraseña es obligatoria.',
            'blank': 'La contraseña es obligatoria.',
        },
    )


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=True,
        error_messages={
            'required': 'El nombre es obligatorio.',
            'blank': 'El nombre es obligatorio.',
        },
    )
    email = serializers.EmailField(
        required=True,
        error_messages={
            'required': 'El correo es obligatorio.',
            'blank': 'El correo es obligatorio.',
            'invalid': 'El correo no tiene un formato válido.',
        },
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        trim_whitespace=False,
        error_messages={
            'required': 'La contraseña es obligatoria.',
            'blank': 'La contraseña es obligatoria.',
        },
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if Profile.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Ya existe un usuario con ese correo.')
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(' '.join(exc.messages))
        return value


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = ProfileSerializer()


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'id', 'user_id', 'name', 'type', 'client', 'event_date',
            'event_time', 'location', 'deadline', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user_id', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {'error_messages': {
                'required': 'El título es obligatorio.',
                'blank': 'El título es obligatorio.',
                'null': 'El título es obligatorio.',
            }},
            'type': {'error_messages': {
                'required': 'El tipo de evento es obligatorio.',
                'blank': 'El tipo de evento es obligatorio.',
                'null': 'El tipo de evento es obligatorio.',
            }},
            'event_date': {'error_messages': {
                'required': 'La fecha del evento es obligatoria.',
                'null': 'La fecha del evento es obligatoria.',
                'invalid': 'La fecha no es válida. Usa el formato AAAA-MM-DD.',
            }},
        }


class SubtaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subtask
        fields = [
            'id', 'event_id', 'name', 'target_date', 'estimated_hours',
            'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'event_id', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {'error_messages': {
                'required': 'El título de la subtarea es obligatorio.',
                'blank': 'El título de la subtarea es obligatorio.',
                'null': 'El título de la subtarea es obligatorio.',
            }},
            'target_date': {'error_messages': {
                'required': 'La fecha objetivo es obligatoria.',
                'null': 'La fecha objetivo es obligatoria.',
                'invalid': 'La fecha no es válida. Usa el formato AAAA-MM-DD.',
            }},
            'estimated_hours': {'error_messages': {
                'required': 'Las horas estimadas son obligatorias.',
                'null': 'Las horas estimadas son obligatorias.',
                'invalid': 'Las horas estimadas deben ser un número.',
                'max_digits': 'Las horas estimadas son demasiado grandes.',
                'max_decimal_places': 'Usa máximo 2 decimales en las horas estimadas.',
            }},
            'status': {'error_messages': {
                'invalid_choice': 'El estado debe ser Pendiente, Ejecutada o Pospuesta.',
            }},
        }

    def validate_estimated_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'Las horas estimadas deben ser mayores que 0.'
            )
        return value

    def validate(self, attrs):

        target_date = attrs.get('target_date')

        # CREACIÓN DE SUBTAREA
        if self.instance is None:

            event = self.context.get('event')

            if (
                event
                and target_date
                and target_date > event.event_date
            ):
                raise serializers.ValidationError({
                    'target_date':
                    'La fecha de la gestión no puede ser posterior a la fecha del evento.'
                })

        # EDICIÓN DE SUBTAREA
        else:

            event = self.instance.event

            if (
                target_date
                and target_date > event.event_date
            ):
                raise serializers.ValidationError({
                    'target_date':
                    'La fecha de la gestión no puede ser posterior a la fecha del evento.'
                })

        return attrs


class TodaySerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)

    class Meta:
        model = Subtask
        fields = [
            'id', 'event_id', 'event_name', 'name', 'target_date', 'estimated_hours',
            'status', 'created_at', 'updated_at',
        ]


class TodayResponseSerializer(serializers.Serializer):
    vencidas = TodaySerializer(many=True)
    hoy = TodaySerializer(many=True)
    proximas = TodaySerializer(many=True)


class TodayErrorFieldsSerializer(serializers.Serializer):
    status = serializers.CharField()


class TodayValidationErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
    fields = TodayErrorFieldsSerializer()


class GlobalErrorSerializer(serializers.Serializer):
    error = serializers.CharField()

class DailyLimitSerializer(serializers.Serializer):
    daily_limit_hours = serializers.IntegerField(
        min_value=1,
        max_value=16
    )

class ConflictResponseSerializer(serializers.Serializer):
    conflict = serializers.BooleanField()
    planned_hours = serializers.FloatField()
    daily_limit = serializers.IntegerField()
    message = serializers.CharField(required=False)
    options = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )