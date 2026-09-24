from rest_framework import serializers

from .models import Event


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
