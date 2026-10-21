"""Ejemplos de request/response para Swagger (/api/docs/). Solo documentación: no cambia el comportamiento.

Los cuerpos de error se arman con construir_error, la misma función que usa la API, y
tests.SwaggerExamplesMatchApiTest comprueba que estos ejemplos coinciden con respuestas reales.
"""
from drf_spectacular.utils import OpenApiExample

from .exceptions import construir_error


def respuesta(nombre, valor, status=200):
    return OpenApiExample(nombre, value=valor, response_only=True, status_codes=[str(status)])


def peticion(nombre, valor):
    return OpenApiExample(nombre, value=valor, request_only=True)


def error(nombre, status, code, mensaje, fields=None):
    return respuesta(nombre, construir_error(status, code, mensaje, fields), status)


# --- Errores comunes (formato único {status, code, error, fields}) ---
ERROR_400_CAMPOS = error('400 · Campos inválidos', 400, 'validation_error', 'Revisa los campos marcados.',
                         {'name': 'El título es obligatorio.'})
ERROR_400_JSON = error('400 · JSON mal formado', 400, 'parse_error', 'No pudimos leer los datos enviados.')
ERROR_401 = error('401 · Sin sesión', 401, 'not_authenticated', 'Tu sesión expiró o no has iniciado sesión.')
ERROR_404 = error('404 · No existe', 404, 'not_found', 'No encontramos lo que buscas.')
ERROR_500 = error('500 · Error del servidor', 500, 'server_error', 'Ocurrió un error en el servidor. Intenta de nuevo.')
ERRORES_COMUNES = [ERROR_401, ERROR_404, ERROR_500]

CONFLICTO = {
    'date': '2026-10-23',
    'conflict': True,
    'planned_hours': 5.0,
    'task_hours': 2.0,
    'total_hours': 7.0,
    'daily_limit': 6,
    'excess': 1.0,
    'message': 'Quedarías con 7h de gestión planificadas (límite 6h)',
    'options': ['mover_a_otro_dia', 'reducir_horas', 'posponer'],
}
_error_409 = construir_error(409, 'overload_conflict', CONFLICTO['message'])
_error_409['conflict'] = CONFLICTO
ERROR_409 = respuesta('409 · Sobrecarga del día', _error_409, 409)

# --- Auth ---
USUARIO = {'id': '3f0c9a52-7d1e-5c3a-9a4e-1b2c3d4e5f60', 'name': 'Usuario Demo',
           'email': 'demo@organiza-eventos.app', 'daily_limit_hours': 6}
SESION = {'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<payload>.<firma>', 'user': USUARIO}

LOGIN = [
    peticion('Iniciar sesión', {'email': 'demo@organiza-eventos.app', 'password': 'tu-contraseña'}),
    respuesta('200 · Sesión iniciada', SESION),
    error('400 · Campos vacíos', 400, 'validation_error', 'Revisa los campos marcados.',
          {'email': 'El correo es obligatorio.', 'password': 'La contraseña es obligatoria.'}),
    error('401 · Datos incorrectos', 401, 'invalid_credentials', 'Correo o contraseña incorrectos.'),
    ERROR_500,
]
REGISTER = [
    peticion('Registrarse', {'name': 'Laura Gómez', 'email': 'laura@ejemplo.com', 'password': 'una-clave-segura-2026'}),
    respuesta('201 · Usuario creado', {**SESION, 'user': {**USUARIO, 'name': 'Laura Gómez', 'email': 'laura@ejemplo.com'}}, 201),
    error('400 · Correo repetido', 400, 'validation_error', 'Revisa los campos marcados.',
          {'email': 'Ya existe un usuario con ese correo.'}),
    ERROR_500,
]
ME = [respuesta('200 · Usuario actual', USUARIO), ERROR_401, ERROR_500]

# --- Eventos ---
EVENTO = {
    'id': '8b6d1c2e-4f3a-5b9c-8d7e-6f5a4b3c2d1e',
    'user_id': USUARIO['id'],
    'name': 'Boda Laura & Andrés',
    'type': 'boda',
    'client': 'Laura Gómez',
    'event_date': '2026-11-09',
    'event_time': '16:00:00',
    'location': 'Hacienda El Bosque',
    'deadline': None,
    'created_at': '2026-10-20T15:10:00-05:00',
    'updated_at': '2026-10-20T15:10:00-05:00',
    'total_subtasks': 5,
    'completed_subtasks': 1,
    'overdue_subtasks': 1,
    'progress_percentage': 20,
}
EVENTO_NUEVO = {'name': 'Boda Laura & Andrés', 'type': 'boda', 'client': 'Laura Gómez',
                'event_date': '2026-11-09', 'event_time': '16:00', 'location': 'Hacienda El Bosque'}
EVENTOS_LISTA = [respuesta('200 · Eventos del usuario', [EVENTO]), ERROR_401, ERROR_500]
EVENTOS_CREAR = [peticion('Crear evento', EVENTO_NUEVO), respuesta('201 · Evento creado', EVENTO, 201),
                 ERROR_400_CAMPOS, ERROR_400_JSON, ERROR_401, ERROR_500]
EVENTO_DETALLE = [respuesta('200 · Evento', EVENTO), *ERRORES_COMUNES]
EVENTO_EDITAR = [peticion('Cambiar el lugar', {'location': 'Club Campestre'}),
                 respuesta('200 · Evento actualizado', {**EVENTO, 'location': 'Club Campestre'}),
                 ERROR_400_CAMPOS, *ERRORES_COMUNES]
EVENTO_ELIMINAR = [*ERRORES_COMUNES]

# --- Subtareas (gestiones) ---
GESTION = {
    'id': '1a2b3c4d-5e6f-5a7b-8c9d-0e1f2a3b4c5d',
    'event_id': EVENTO['id'],
    'name': 'Confirmar fotógrafo',
    'target_date': '2026-10-25',
    'estimated_hours': 2.0,
    'status': 'Pendiente',
    'notes': None,
    'created_at': '2026-10-20T15:12:00-05:00',
    'updated_at': '2026-10-20T15:12:00-05:00',
}
ERROR_HORAS = error('400 · Horas en 0', 400, 'validation_error', 'Revisa los campos marcados.',
                    {'estimated_hours': 'Las horas estimadas deben ser mayores que 0.'})
GESTIONES_LISTA = [respuesta('200 · Gestiones del evento', [GESTION]), *ERRORES_COMUNES]
GESTIONES_CREAR = [
    peticion('Crear gestión', {'name': 'Confirmar fotógrafo', 'target_date': '2026-10-25', 'estimated_hours': 2}),
    respuesta('201 · Gestión creada', GESTION, 201),
    ERROR_HORAS, ERROR_409, *ERRORES_COMUNES,
]
GESTION_DETALLE = [respuesta('200 · Gestión', GESTION), *ERRORES_COMUNES]
GESTION_EDITAR = [
    peticion('Reprogramar', {'target_date': '2026-10-23'}),
    peticion('Marcar como ejecutada con nota', {'status': 'Ejecutada', 'notes': 'Se pagó el 50% del depósito.'}),
    peticion('Posponer con nueva fecha', {'status': 'Pospuesta', 'target_date': '2026-10-28'}),
    respuesta('200 · Gestión actualizada',
              {**GESTION, 'status': 'Ejecutada', 'notes': 'Se pagó el 50% del depósito.'}),
    error('400 · Nota muy larga', 400, 'validation_error', 'Revisa los campos marcados.',
          {'notes': 'Las notas no pueden superar los 500 caracteres.'}),
    ERROR_409, *ERRORES_COMUNES,
]
GESTION_ELIMINAR = [*ERRORES_COMUNES]

# --- Hoy, límite diario y conflictos ---
# /today no incluye "notes" pero sí "event_name".
GESTION_HOY = {k: v for k, v in GESTION.items() if k != 'notes'} | {'event_name': EVENTO['name']}
HOY = [
    respuesta('200 · Gestiones agrupadas', {
        'vencidas': [{**GESTION_HOY, 'name': 'Reservar salón', 'target_date': '2026-10-18'}],
        'hoy': [{**GESTION_HOY, 'name': 'Enviar invitaciones', 'target_date': '2026-10-20'}],
        'proximas': [GESTION_HOY],
    }),
    error('400 · Estado no válido', 400, 'validation_error', 'Revisa los campos marcados.',
          {'status': 'El estado debe ser Pendiente o Pospuesta.'}),
    *ERRORES_COMUNES,
]
LIMITE_CONSULTAR = [respuesta('200 · Límite actual', {'daily_limit_hours': 6}), ERROR_401, ERROR_500]
LIMITE_ACTUALIZAR = [
    peticion('Cambiar a 8 horas', {'daily_limit_hours': 8}),
    respuesta('200 · Límite guardado', {'daily_limit_hours': 8}),
    error('400 · Fuera de rango', 400, 'validation_error', 'Revisa los campos marcados.',
          {'daily_limit_hours': 'El límite debe estar entre 1 y 16 horas por día'}),
    ERROR_401, ERROR_500,
]
CONFLICTOS = [
    respuesta('200 · Hay sobrecarga', {**CONFLICTO, 'suggested_dates': [
        {**CONFLICTO, 'date': '2026-10-24', 'conflict': False, 'planned_hours': 0.0, 'total_hours': 2.0,
         'excess': 0.0, 'message': 'Quedarías con 2h de gestión planificadas (límite 6h)', 'options': []},
    ]}),
    error('400 · Falta la fecha', 400, 'validation_error', 'Revisa los campos marcados.',
          {'date': 'Selecciona una fecha.'}),
    *ERRORES_COMUNES,
]
