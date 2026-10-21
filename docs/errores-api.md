# Errores de la API

Historia de usuario de accesibilidad, usabilidad y UX Writing — subtarea de backend: normalizar y estandarizar los códigos y mensajes de error.

## Formato

Todo error de la API responde con las mismas cuatro llaves:

```json
{
  "status": 400,
  "code": "validation_error",
  "error": "Revisa los campos marcados.",
  "fields": {}
}
```

| Llave | Tipo | Qué es |
|---|---|---|
| `status` | número | Igual al código HTTP de la respuesta. |
| `code` | texto | Identificador estable en `snake_case`. Sirve para decidir comportamiento sin leer el mensaje. |
| `error` | texto | Mensaje en español, breve y sin jerga. Se muestra tal cual al usuario. |
| `fields` | objeto | Un mensaje (texto) por campo. Siempre está presente; es `{}` cuando no aplica. Los errores anidados usan `campo.subcampo`. |

**Única excepción:** el 409 de sobrecarga agrega una quinta llave, `conflict`, con el detalle de capacidad (horas planificadas, límite, exceso y días sugeridos).

El formato lo arma una sola función, `construir_error`, en `tasks/exceptions.py`. Lo usan:
- el manejador de DRF (`manejar_errores`);
- los handlers de Django (`handler400`, `handler403`, `handler404` y `handler500`) para URLs inexistentes y fallos fuera de DRF.

## Códigos

| status | code | Cuándo ocurre | error |
|---|---|---|---|
| 400 | `validation_error` | Uno o más campos no son válidos. Cada campo trae su mensaje en `fields`. | Revisa los campos marcados. |
| 400 | `parse_error` | El cuerpo no es JSON válido o no es un objeto (por ejemplo, una lista). | No pudimos leer los datos enviados. |
| 401 | `not_authenticated` | Falta el token, está vencido o fue alterado. | Tu sesión expiró o no has iniciado sesión. |
| 401 | `invalid_credentials` | `POST /login` con correo o contraseña incorrectos. | Correo o contraseña incorrectos. |
| 403 | `forbidden` | La sesión es válida pero la acción no está permitida. | No tienes permiso para hacer esto. |
| 404 | `not_found` | El recurso no existe, es de otro usuario o la URL no existe. | No encontramos lo que buscas. |
| 405 | `method_not_allowed` | El método HTTP no está disponible en esa ruta (por ejemplo, `PUT /events/<id>`). | Esta acción no está disponible. |
| 409 | `overload_conflict` | El cambio supera el límite diario de horas. Trae además `conflict`. | Quedarías con 7h de gestión planificadas (límite 6h) |
| 415 | `unsupported_media_type` | El cuerpo no se envió como JSON. | Envía los datos en formato JSON. |
| 429 | `too_many_requests` | Demasiadas solicitudes (no hay límite configurado hoy). | Hiciste demasiadas solicitudes. Espera un momento e intenta de nuevo. |
| 500 | `server_error` | Error inesperado. El detalle técnico va al log del servidor, nunca a la respuesta. | Ocurrió un error en el servidor. Intenta de nuevo. |
| otro | `code` de la excepción | Cualquier otro error. | No se pudo completar la solicitud. Intenta de nuevo. |

> **`DEBUG`:** las URLs inexistentes y los errores fuera de DRF solo responden en JSON con `DEBUG=False`. Es el valor por defecto y el de Render. Con `DEBUG=True`, Django muestra su página HTML de depuración.

## Ejemplos

Las respuestas de 400, 401 y 404 son reales: se obtuvieron contra el servidor local. La de 500 sale de los tests (`ErrorFormatTest`), porque no se rompe código real para provocarla.

### 400 — validación (`POST /events` con título vacío)

```json
{"status": 400, "code": "validation_error", "error": "Revisa los campos marcados.", "fields": {"name": "El título es obligatorio."}}
```

### 400 — JSON malformado (`POST /events` con `{"name": "x",`)

```json
{"status": 400, "code": "parse_error", "error": "No pudimos leer los datos enviados.", "fields": {}}
```

### 401 — sin sesión (`GET /events` sin token o con token inválido)

```json
{"status": 401, "code": "not_authenticated", "error": "Tu sesión expiró o no has iniciado sesión.", "fields": {}}
```

### 401 — login incorrecto (`POST /login`)

```json
{"status": 401, "code": "invalid_credentials", "error": "Correo o contraseña incorrectos.", "fields": {}}
```

### 404 — recurso o URL inexistente (`GET /events/no-existe-123`, `GET /esto-no-existe`)

```json
{"status": 404, "code": "not_found", "error": "No encontramos lo que buscas.", "fields": {}}
```

### 405 — método no disponible (`PUT /events/<id>`)

```json
{"status": 405, "code": "method_not_allowed", "error": "Esta acción no está disponible.", "fields": {}}
```

### 409 — sobrecarga (`PATCH /subtasks/<id>`)

```json
{
  "status": 409,
  "code": "overload_conflict",
  "error": "Quedarías con 7h de gestión planificadas (límite 6h)",
  "fields": {},
  "conflict": {"date": "2026-10-20", "conflict": true, "planned_hours": 5.0, "task_hours": 2.0, "total_hours": 7.0, "daily_limit": 6, "excess": 1.0, "options": ["mover_a_otro_dia", "reducir_horas", "posponer"]}
}
```

### 500 — error del servidor

```json
{"status": 500, "code": "server_error", "error": "Ocurrió un error en el servidor. Intenta de nuevo.", "fields": {}}
```

## Nota para frontend

- **Muestra `error` tal cual.** Está pensado para el usuario: no lo traduzcas ni le agregues el código HTTP. Ponlo en una región con `role="alert"` o `aria-live` para que lo anuncien los lectores de pantalla.
- **Pon cada mensaje de `fields` junto a su input.** La llave es el nombre del campo en la API (`name`, `target_date`, `estimated_hours`, `notes`…). Asocia el mensaje al input con `aria-describedby` y marca el input con `aria-invalid="true"`.
- **Decide comportamiento con `code`, no con el texto.** Por ejemplo, con `not_authenticated` se cierra la sesión y se lleva a `/login`; con `overload_conflict` se lee `conflict`.
- **`fields` siempre llega**, aunque sea `{}`. Para saber si hay errores de campo, revisa que tenga llaves: `Object.keys(fields).length > 0`.
