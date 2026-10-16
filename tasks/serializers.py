from drf_spectacular.types import OpenApiTypes  # nuevo
from drf_spectacular.utils import extend_schema_field
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal

from .models import Event, Profile, Subtask
from .progress import calculate_progress, event_counts
from .sanitizers import sanitize_text


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["id", "name", "email", "daily_limit_hours"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            "required": "El correo es obligatorio.",
            "blank": "El correo es obligatorio.",
            "invalid": "El correo no tiene un formato válido.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        error_messages={
            "required": "La contraseña es obligatoria.",
            "blank": "La contraseña es obligatoria.",
        },
    )


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=True,
        error_messages={
            "required": "El nombre es obligatorio.",
            "blank": "El nombre es obligatorio.",
        },
    )
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": "El correo es obligatorio.",
            "blank": "El correo es obligatorio.",
            "invalid": "El correo no tiene un formato válido.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        trim_whitespace=False,
        error_messages={
            "required": "La contraseña es obligatoria.",
            "blank": "La contraseña es obligatoria.",
        },
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if Profile.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Ya existe un usuario con ese correo.")
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return value


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = ProfileSerializer()


class EventSerializer(serializers.ModelSerializer):
    total_subtasks = serializers.SerializerMethodField()
    completed_subtasks = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "user_id",
            "name",
            "type",
            "client",
            "event_date",
            "event_time",
            "location",
            "deadline",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user_id", "created_at", "updated_at"]
        extra_kwargs = {
            "name": {
                "error_messages": {
                    "required": "El título es obligatorio.",
                    "blank": "El título es obligatorio.",
                    "null": "El título es obligatorio.",
                }
            },
            "type": {
                "error_messages": {
                    "required": "El tipo de evento es obligatorio.",
                    "blank": "El tipo de evento es obligatorio.",
                    "null": "El tipo de evento es obligatorio.",
                }
            },
            "event_date": {
                "error_messages": {
                    "required": "La fecha del evento es obligatoria.",
                    "null": "La fecha del evento es obligatoria.",
                    "invalid": "La fecha no es válida. Usa el formato AAAA-MM-DD.",
                }
            },
        }

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_subtasks(self, obj):
        return event_counts(obj)[0]

    @extend_schema_field(OpenApiTypes.INT)
    def get_completed_subtasks(self, obj):
        return event_counts(obj)[1]

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_progress_percentage(self, obj):
        return calculate_progress(*event_counts(obj))


class SubtaskStatusField(serializers.ChoiceField):
    """Acepta Pendiente/Ejecutada/Pospuesta y sus equivalentes PENDING/DONE/POSTPONED.

    Siempre se guarda y se devuelve el valor en español.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", Subtask.ESTADOS)
        kwargs.setdefault("required", False)
        kwargs.setdefault(
            "error_messages",
            {
                "invalid_choice": "El estado debe ser Pendiente, Ejecutada o Pospuesta (o PENDING, DONE, POSTPONED).",
                "null": "El estado no puede estar vacío.",
            },
        )
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = Subtask.ESTADOS_ALIAS.get(data.strip().upper(), data.strip())
        return super().to_internal_value(data)


class SubtaskSerializer(serializers.ModelSerializer):
    status = SubtaskStatusField()
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=False,
        # Tope bruto para no procesar cargas enormes; el límite real se valida ya sanitizado.
        max_length=Subtask.NOTES_MAX_LENGTH * 10,
        error_messages={
            "invalid": "Las notas deben ser texto.",
            "max_length": f"Las notas no pueden superar los {Subtask.NOTES_MAX_LENGTH} caracteres.",
        },
    )

    class Meta:
        model = Subtask
        fields = [
            "id",
            "event_id",
            "name",
            "target_date",
            "estimated_hours",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "event_id", "created_at", "updated_at"]
        extra_kwargs = {
            "name": {
                "error_messages": {
                    "required": "El título de la subtarea es obligatorio.",
                    "blank": "El título de la subtarea es obligatorio.",
                    "null": "El título de la subtarea es obligatorio.",
                }
            },
            "target_date": {
                "error_messages": {
                    "required": "La fecha objetivo es obligatoria.",
                    "null": "La fecha objetivo es obligatoria.",
                    "invalid": "La fecha no es válida. Usa el formato AAAA-MM-DD.",
                }
            },
            "estimated_hours": {
                "error_messages": {
                    "required": "Las horas estimadas son obligatorias.",
                    "null": "Las horas estimadas son obligatorias.",
                    "invalid": "Las horas estimadas deben ser un número.",
                    "max_digits": "Las horas estimadas son demasiado grandes.",
                    "max_decimal_places": "Usa máximo 2 decimales en las horas estimadas.",
                }
            },
        }

    def validate_notes(self, value):
        notes = sanitize_text(value) if value is not None else None
        if notes is not None and len(notes) > Subtask.NOTES_MAX_LENGTH:
            raise serializers.ValidationError(
                f"Las notas no pueden superar los {Subtask.NOTES_MAX_LENGTH} caracteres."
            )
        return notes

    def validate_estimated_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Las horas estimadas deben ser mayores que 0."
            )
        return value

    def validate(self, attrs):

        target_date = attrs.get("target_date")
        if target_date and target_date < timezone.localdate():
            raise serializers.ValidationError(
                {"target_date": "La fecha objetivo no puede ser anterior a hoy."}
            )

        # CREACIÓN DE SUBTAREA
        if self.instance is None:
            event = self.context.get("event")

            if event and target_date and target_date > event.event_date:
                raise serializers.ValidationError(
                    {
                        "target_date": "La fecha de la gestión no puede ser posterior a la fecha del evento."
                    }
                )

        # EDICIÓN DE SUBTAREA
        else:
            event = self.instance.event

            if target_date and target_date > event.event_date:
                raise serializers.ValidationError(
                    {
                        "target_date": "La fecha de la gestión no puede ser posterior a la fecha del evento."
                    }
                )

        return attrs


class TodaySerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source="event.name", read_only=True)

    class Meta:
        model = Subtask
        fields = [
            "id",
            "event_id",
            "event_name",
            "name",
            "target_date",
            "estimated_hours",
            "status",
            "created_at",
            "updated_at",
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


class ValidationErrorSerializer(serializers.Serializer):
    """400: un mensaje por campo inválido."""

    error = serializers.CharField()
    fields = serializers.DictField(child=serializers.CharField())


class OverloadErrorSerializer(serializers.Serializer):
    """409: el cambio superaría el límite diario de horas."""

    error = serializers.CharField()
    code = serializers.CharField()
    conflict = serializers.DictField()


class DailyLimitSerializer(serializers.Serializer):
    daily_limit_hours = serializers.IntegerField(min_value=1, max_value=16)


class ConflictResponseSerializer(serializers.Serializer):
    suggested_dates = serializers.ListField(
        child=serializers.DictField(), required=False
    )
    conflict = serializers.BooleanField()
    planned_hours = serializers.FloatField()
    daily_limit = serializers.IntegerField()
    date = serializers.DateField()
    task_hours = serializers.FloatField()
    total_hours = serializers.FloatField()
    excess = serializers.FloatField()
    message = serializers.CharField(required=False)
    options = serializers.ListField(child=serializers.CharField(), required=False)


class CapacityQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
    subtask_id = serializers.CharField(required=False)
    estimated_hours = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    status = serializers.ChoiceField(
        choices=["Pendiente", "Pospuesta", "Ejecutada"], required=False
    )
