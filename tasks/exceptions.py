import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def manejar_errores(exc, context):
    """Todas las respuestas de error tienen la forma {"error": "...", "fields": {...}}."""
    response = exception_handler(exc, context)

    # Error inesperado (bug, base de datos caída...): 500 con mensaje entendible
    if response is None:
        logger.exception('Error no controlado')
        return Response(
            {'error': 'Ocurrió un error en el servidor. Intenta de nuevo.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Datos inválidos: un mensaje por campo para mostrarlo junto a cada input
    if isinstance(exc, ValidationError) and isinstance(response.data, dict):
        fields = {campo: mensajes[0] if isinstance(mensajes, list) else mensajes
                  for campo, mensajes in response.data.items()}
        response.data = {'error': 'Revisa los campos marcados.', 'fields': fields}
        return response

    if isinstance(exc, (NotFound, Http404)):
        response.data = {'error': 'No encontramos lo que buscas.'}
        return response

    # Otros errores de DRF (405...)
    response.data = {'error': response.data.get('detail', 'No se pudo completar la solicitud.')}
    return response
