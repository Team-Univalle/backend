"""Ejemplos y esquemas reutilizables para la documentación Swagger (/docs)."""

from drf_spectacular.utils import OpenApiExample, extend_schema

from .serializers import (
    EventSerializer,
    GlobalErrorSerializer,
    OverloadErrorSerializer,
    SubtaskSerializer,
    ValidationErrorSerializer,
)

EVENT_CON_PROGRESO = {
    "id": "b3f1c2d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
    "user_id": "9a8b7c6d-5e4f-4321-bcda-0123456789ab",
    "name": "Boda de Ana y Luis",
    "type": "Boda",
    "client": "Ana Pérez",
    "event_date": "2026-12-12",
    "event_time": "18:00:00",
    "location": "Hacienda La Palma",
    "deadline": None,
    "created_at": "2026-10-01T15:04:05Z",
    "updated_at": "2026-10-15T09:30:00Z",
    "total_subtasks": 3,
    "completed_subtasks": 1,
    "progress_percentage": 33.3,
}
EVENT_SIN_SUBTAREAS = {
    **EVENT_CON_PROGRESO,
    "name": "Cumpleaños de Sofía",
    "total_subtasks": 0,
    "completed_subtasks": 0,
    "progress_percentage": 0.0,
}
SUBTASK_RESPUESTA = {
    "id": "0d6e3c1a-7b2f-4c85-9a41-5f8e2b7d1c30",
    "event_id": EVENT_CON_PROGRESO["id"],
    "name": "Pagar anticipo del salón",
    "target_date": "2026-10-20",
    "estimated_hours": 2.0,
    "status": "Ejecutada",
    "notes": "Se pagó el anticipo al proveedor.",
    "created_at": "2026-10-01T15:10:00Z",
    "updated_at": "2026-10-15T09:45:00Z",
}
CONFLICTO = {
    "date": "2026-10-20",
    "conflict": True,
    "planned_hours": 5.0,
    "task_hours": 2.0,
    "total_hours": 7.0,
    "daily_limit": 6,
    "excess": 1.0,
    "message": "Quedarías con 7h de gestión planificadas (límite 6h)",
    "options": ["mover_a_otro_dia", "reducir_horas", "posponer"],
}


def _error(name, value, code):
    return OpenApiExample(name, value=value, response_only=True, status_codes=[code])


ERROR_400 = _error(
    "Datos inválidos (400)",
    {
        "error": "Revisa los campos marcados.",
        "fields": {"notes": "Las notas no pueden superar los 500 caracteres."},
    },
    "400",
)
ERROR_401 = _error(
    "Sin sesión válida (401)",
    {"error": "Tu sesión expiró o no has iniciado sesión."},
    "401",
)
ERROR_404 = _error(
    "No existe o es de otro usuario (404)",
    {"error": "No encontramos lo que buscas."},
    "404",
)
ERROR_409 = _error(
    "Sobrecarga diaria (409)",
    {"error": CONFLICTO["message"], "code": "overload_conflict", "conflict": CONFLICTO},
    "409",
)
ERROR_500 = _error(
    "Error del servidor (500)",
    {"error": "Ocurrió un error en el servidor. Intenta de nuevo."},
    "500",
)

# Códigos de error estándar compartidos por todos los endpoints protegidos.
RESPUESTAS_ERROR = {401: GlobalErrorSerializer, 500: GlobalErrorSerializer}

EVENT_LIST = extend_schema(
    summary="Listar eventos con su progreso",
    description=(
        "Eventos del usuario ordenados por fecha. Cada evento incluye `total_subtasks`, "
        "`completed_subtasks` (subtareas en estado Ejecutada) y `progress_percentage` "
        "(ejecutadas / total x 100, con un decimal; **0.0** si el evento no tiene subtareas)."
    ),
    responses={200: EventSerializer(many=True), **RESPUESTAS_ERROR},
    examples=[
        OpenApiExample(
            "Eventos con progreso",
            value=[EVENT_CON_PROGRESO, EVENT_SIN_SUBTAREAS],
            response_only=True,
            status_codes=["200"],
        ),
        ERROR_401,
        ERROR_500,
    ],
)
EVENT_CREATE = extend_schema(
    summary="Crear un evento",
    description="Un evento nuevo nace con `total_subtasks` 0, `completed_subtasks` 0 y `progress_percentage` 0.0.",
    request=EventSerializer,
    responses={
        201: EventSerializer,
        400: ValidationErrorSerializer,
        **RESPUESTAS_ERROR,
    },
    examples=[
        OpenApiExample(
            "Request",
            value={
                "name": "Cumpleaños de Sofía",
                "type": "Cumpleaños",
                "event_date": "2026-11-20",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Evento creado",
            value=EVENT_SIN_SUBTAREAS,
            response_only=True,
            status_codes=["201"],
        ),
        _error(
            "Datos inválidos (400)",
            {
                "error": "Revisa los campos marcados.",
                "fields": {"name": "El título es obligatorio."},
            },
            "400",
        ),
        ERROR_401,
        ERROR_500,
    ],
)
EVENT_RETRIEVE = extend_schema(
    summary="Consultar un evento y su progreso",
    description=(
        "Devuelve el evento con su progreso, que siempre se calcula en el momento: al cambiar el estado de una "
        "subtarea con `PATCH /subtasks/{id}`, la siguiente consulta ya refleja el nuevo porcentaje."
    ),
    responses={200: EventSerializer, 404: GlobalErrorSerializer, **RESPUESTAS_ERROR},
    examples=[
        OpenApiExample(
            "Con subtareas (1 de 3 ejecutadas)",
            value=EVENT_CON_PROGRESO,
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Sin subtareas (0 %)",
            value=EVENT_SIN_SUBTAREAS,
            response_only=True,
            status_codes=["200"],
        ),
        ERROR_401,
        ERROR_404,
        ERROR_500,
    ],
)
EVENT_PATCH = extend_schema(
    summary="Actualizar un evento",
    request=EventSerializer,
    responses={
        200: EventSerializer,
        400: ValidationErrorSerializer,
        404: GlobalErrorSerializer,
        **RESPUESTAS_ERROR,
    },
    examples=[
        OpenApiExample(
            "Request", value={"location": "Salón Los Robles"}, request_only=True
        ),
        OpenApiExample(
            "Evento actualizado",
            value=EVENT_CON_PROGRESO,
            response_only=True,
            status_codes=["200"],
        ),
        ERROR_400,
        ERROR_401,
        ERROR_404,
        ERROR_500,
    ],
)
EVENT_DELETE = extend_schema(
    summary="Eliminar un evento",
    description="Elimina también todas sus subtareas.",
    responses={204: None, 404: GlobalErrorSerializer, **RESPUESTAS_ERROR},
    examples=[ERROR_401, ERROR_404, ERROR_500],
)

SUBTASK_PATCH = extend_schema(
    summary="Actualizar estado y notas de una subtarea",
    description=(
        "Actualización parcial. `status` acepta Pendiente, Ejecutada y Pospuesta (también PENDING, DONE y "
        "POSTPONED; siempre se devuelve en español). `notes` es texto plano de hasta 500 caracteres: se sanitiza "
        "en el servidor (sin etiquetas HTML ni caracteres de control) y, si queda vacío, se guarda como null. "
        "Marcar una subtarea como Ejecutada aumenta `completed_subtasks` y `progress_percentage` de su evento."
    ),
    request=SubtaskSerializer,
    responses={
        200: SubtaskSerializer,
        400: ValidationErrorSerializer,
        404: GlobalErrorSerializer,
        409: OverloadErrorSerializer,
        **RESPUESTAS_ERROR,
    },
    examples=[
        OpenApiExample(
            "Marcar como ejecutada con nota",
            value={"status": "DONE", "notes": "Se pagó el anticipo al proveedor."},
            request_only=True,
        ),
        OpenApiExample(
            "Solo posponer", value={"status": "POSTPONED"}, request_only=True
        ),
        OpenApiExample(
            "Subtarea actualizada",
            value=SUBTASK_RESPUESTA,
            response_only=True,
            status_codes=["200"],
        ),
        ERROR_400,
        ERROR_401,
        ERROR_404,
        ERROR_409,
        ERROR_500,
    ],
)
