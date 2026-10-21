"""Formato único de errores de la API (HU-11, accesibilidad y UX Writing).

Todo error responde con las mismas cuatro llaves:
    {"status": 400, "code": "validation_error", "error": "Revisa los campos marcados.", "fields": {}}

- status: igual al código HTTP.
- code: identificador estable en snake_case para que el frontend decida sin leer el texto.
- error: mensaje en español, breve y sin jerga; el frontend lo muestra tal cual.
- fields: un mensaje (string) por campo, para mostrarlo junto a su input. {} cuando no aplica.

Única excepción: el 409 de sobrecarga agrega la llave "conflict" con el detalle de capacidad,
porque el frontend lo usa para explicar el conflicto y sugerir otros días.
Ver docs/errores-api.md.
"""
import logging

from django.http import Http404, JsonResponse
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)

MENSAJE_VALIDACION = 'Revisa los campos marcados.'
MENSAJE_DATOS_ILEGIBLES = 'No pudimos leer los datos enviados.'
MENSAJE_SESION = 'Tu sesión expiró o no has iniciado sesión.'
MENSAJE_PROHIBIDO = 'No tienes permiso para hacer esto.'
MENSAJE_NO_ENCONTRADO = 'No encontramos lo que buscas.'
MENSAJE_METODO = 'Esta acción no está disponible.'
MENSAJE_FORMATO = 'Envía los datos en formato JSON.'
MENSAJE_DEMASIADAS = 'Hiciste demasiadas solicitudes. Espera un momento e intenta de nuevo.'
MENSAJE_GENERICO = 'No se pudo completar la solicitud. Intenta de nuevo.'
MENSAJE_SERVIDOR = 'Ocurrió un error en el servidor. Intenta de nuevo.'


class InvalidCredentials(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Correo o contraseña incorrectos.'
    default_code = 'invalid_credentials'


class OverloadConflict(APIException):
    status_code = 409
    default_code = 'overload_conflict'

    def __init__(self, capacity):
        self.capacity = capacity
        super().__init__(capacity['message'])


def construir_error(status_code, code, error, fields=None):
    """Único lugar donde se arma el cuerpo de un error."""
    return {
        'status': status_code,
        'code': code,
        'error': str(error),
        'fields': fields or {},
    }


def _primer_texto(valor):
    if isinstance(valor, (list, tuple)):
        return _primer_texto(valor[0]) if valor else ''
    return str(valor)


def aplanar_campos(detalle, prefijo=''):
    """Un string por campo. Los errores anidados quedan como "campo.subcampo" (o "campo.0.subcampo" en listas)."""
    campos = {}
    for campo, valor in detalle.items():
        clave = f'{prefijo}{campo}'
        if isinstance(valor, dict):
            campos.update(aplanar_campos(valor, f'{clave}.'))
        elif isinstance(valor, (list, tuple)) and any(isinstance(item, dict) for item in valor):
            for indice, item in enumerate(valor):
                if isinstance(item, dict) and item:
                    campos.update(aplanar_campos(item, f'{clave}.{indice}.'))
        else:
            campos[clave] = _primer_texto(valor)
    return campos


def _cuerpo_no_es_objeto(context):
    """True si el cliente envió algo que no es un objeto JSON (por ejemplo una lista o un número)."""
    request = context.get('request') if context else None
    try:
        data = request.data if request is not None else None
    except Exception:  # noqa: BLE001 - si ni siquiera se puede leer, tampoco es un objeto válido
        return True
    return data is not None and not hasattr(data, 'items')


def _error_de_validacion(exc, context):
    detalle = exc.detail
    if not isinstance(detalle, dict):
        # ValidationError('texto') o ValidationError([...]) lanzado desde una vista: no hay campos.
        return construir_error(400, 'validation_error', _primer_texto(detalle) or MENSAJE_VALIDACION)

    campos = aplanar_campos(detalle)
    no_de_campo = campos.pop(api_settings.NON_FIELD_ERRORS_KEY, None)
    if no_de_campo and not campos and _cuerpo_no_es_objeto(context):
        # DRF responde "Se esperaba un diccionario pero es un list": es un cuerpo mal formado.
        return construir_error(400, 'parse_error', MENSAJE_DATOS_ILEGIBLES)
    # Los errores que no son de un campo concreto van en "error" para mostrarse arriba del formulario.
    return construir_error(400, 'validation_error', no_de_campo or MENSAJE_VALIDACION, campos)


def _cuerpo_para(exc, response, context):
    if isinstance(exc, ValidationError):
        return _error_de_validacion(exc, context)
    if isinstance(exc, ParseError):
        return construir_error(400, 'parse_error', MENSAJE_DATOS_ILEGIBLES)
    if isinstance(exc, InvalidCredentials):
        return construir_error(401, 'invalid_credentials', exc.detail)
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return construir_error(401, 'not_authenticated', MENSAJE_SESION)
    if isinstance(exc, PermissionDenied):
        return construir_error(403, 'forbidden', MENSAJE_PROHIBIDO)
    if isinstance(exc, (NotFound, Http404)):
        return construir_error(404, 'not_found', MENSAJE_NO_ENCONTRADO)
    if isinstance(exc, MethodNotAllowed):
        return construir_error(405, 'method_not_allowed', MENSAJE_METODO)
    if isinstance(exc, UnsupportedMediaType):
        return construir_error(415, 'unsupported_media_type', MENSAJE_FORMATO)
    if isinstance(exc, Throttled):
        return construir_error(429, 'too_many_requests', MENSAJE_DEMASIADAS)
    # Cualquier otro error de DRF: mismo formato, sin pasar el texto interno de DRF.
    code = getattr(exc, 'default_code', None) or 'error'
    return construir_error(response.status_code, code, MENSAJE_GENERICO)


def manejar_errores(exc, context):
    """EXCEPTION_HANDLER de DRF (settings.REST_FRAMEWORK). Todas las respuestas usan construir_error."""
    if isinstance(exc, OverloadConflict):
        body = construir_error(409, 'overload_conflict', exc.capacity['message'])
        body['conflict'] = exc.capacity
        return Response(body, status=409)

    response = exception_handler(exc, context)

    # Error inesperado (bug, base de datos caída...): el detalle va al log, nunca al cliente.
    if response is None:
        logger.exception('Error no controlado', exc_info=exc)
        return Response(construir_error(500, 'server_error', MENSAJE_SERVIDOR), status=500)

    # Sin sesión siempre es 401 (DRF respondería 403 si la autenticación no define WWW-Authenticate).
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        response.status_code = status.HTTP_401_UNAUTHORIZED

    body = _cuerpo_para(exc, response, context)
    response.status_code = body['status']
    response.data = body
    return response


# Errores fuera de DRF (URL inexistente, fallos en middleware o en vistas que no son de DRF).
# Se registran en django_crud_api/urls.py y Django SOLO los usa con DEBUG=False;
# con DEBUG=True muestra su página de depuración en HTML.
def handler400(request, exception=None):
    return JsonResponse(construir_error(400, 'bad_request', MENSAJE_DATOS_ILEGIBLES), status=400)


def handler403(request, exception=None):
    return JsonResponse(construir_error(403, 'forbidden', MENSAJE_PROHIBIDO), status=403)


def handler404(request, exception=None):
    return JsonResponse(construir_error(404, 'not_found', MENSAJE_NO_ENCONTRADO), status=404)


def handler500(request):
    # Django ya registró la excepción en el log antes de llamar a este handler.
    return JsonResponse(construir_error(500, 'server_error', MENSAJE_SERVIDOR), status=500)
