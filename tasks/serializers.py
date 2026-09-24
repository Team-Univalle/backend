from rest_framework import serializers

from .models import Event, Subtask


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
        read_only_fields = ['id', 'event_id', 'status', 'created_at', 'updated_at']
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
        }

    def validate_estimated_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError('Las horas estimadas deben ser mayores que 0.')
        return value
