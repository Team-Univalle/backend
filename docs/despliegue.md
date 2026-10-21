# Despliegue en producción

Historia de despliegue (Vercel + Render + Supabase). Esta guía es para quien despliegue el backend o lo revise.

## URLs

| Qué | URL |
|---|---|
| Frontend (Vercel) | https://frontend-vert-one-pt320cfqws.vercel.app |
| Backend (Render) | https://backend-qs5z.onrender.com |
| Salud | https://backend-qs5z.onrender.com/health |
| Swagger UI | https://backend-qs5z.onrender.com/api/docs/ |
| Esquema OpenAPI | https://backend-qs5z.onrender.com/api/schema/ |

> **Hay un segundo servicio, `backend-8-68ad.onrender.com`, que está roto** (no tiene base de datos configurada y responde 500). Es el que aparece en el Documento Maestro.
> - El servicio correcto es `backend-qs5z`: es el que usa el frontend publicado.
> - Apaga `backend-8-68ad` en Render y corrige el Documento Maestro.

El plan gratuito de Render duerme el servicio cuando no tiene uso. La primera petición tarda unos 45 segundos (medido el 20/10/2026); después responde en menos de 1 segundo. Antes de una demo, abre `/health` y espera a que responda.

## Variables de entorno en Render (servicio `backend-qs5z` → Environment)

| Variable | Obligatoria | Qué es |
|---|---|---|
| `DATABASE_URL` | Sí | Cadena de conexión de Supabase. Recomendado: el pooler de transacciones (puerto **6543**), que evita el error "max clients reached". |
| `JWT_SECRET` | Sí | Firma de los tokens de sesión. Si la cambias, todos tienen que volver a iniciar sesión. |
| `SECRET_KEY` | Recomendada | Clave de Django, distinta de `JWT_SECRET`. Si falta, se deriva de `JWT_SECRET`. |
| `CORS_ALLOWED_ORIGINS` | Recomendada | Origen exacto del frontend: `https://frontend-vert-one-pt320cfqws.vercel.app` (https y sin `/` al final; varios, separados por comas). Si falta, se usa ese mismo valor. |
| `ALLOWED_HOSTS` | Opcional | `backend-qs5z.onrender.com`. Render ya agrega su dominio solo, con `RENDER_EXTERNAL_HOSTNAME`. |
| `CSRF_TRUSTED_ORIGINS` | Opcional | Por defecto, los orígenes https de CORS. Solo afecta a `/admin`. |
| `DEMO_EMAIL` | Para `seed_demo` | Correo del usuario demo. Por defecto: `demo@organiza-eventos.app`. |
| `DEMO_PASSWORD` | Para `seed_demo` | Contraseña del demo. Se guarda con hash y nunca va en el repo. |
| `DEBUG` | **No la definas** | Si no existe, queda en `False`. Nunca la pongas en `True` en producción. |

Variables que ya existían y siguen funcionando:
- `FRONTEND_URL`: se suma a los orígenes de CORS.
- `DB_CONN_MAX_AGE`: es opcional. Vale 0 con el puerto 6543 y 600 con el 5432.

Generar claves:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Comandos en Render

| Campo | Valor |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn django_crud_api.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Health Check Path | `/health` |
| Python | `.python-version` = 3.13 (o la variable `PYTHON_VERSION`) |

**No hace falta `migrate`.** Los modelos de la app usan `managed = False`, así que Django no crea ni modifica sus tablas. Ejecutar `migrate` solo crearía en Supabase las tablas internas de Django (`auth_*` y `django_*`), y la API no las usa.

## Qué se configuró en el código para producción

En Render (que define `RENDER=true`), o con `DJANGO_ENV=production`, se activa lo siguiente:
- `DEBUG=False` y errores en JSON (`docs/errores-api.md`).
- HTTPS:
  - `SECURE_PROXY_SSL_HEADER` (Render termina el TLS);
  - redirección de http a https (salvo `/health`, para el chequeo de salud);
  - HSTS de 1 día;
  - cookies seguras.
- CORS con una lista exacta, sin `localhost` y sin `CORS_ALLOW_ALL_ORIGINS`.
- `SECRET_KEY` sin valor escrito en el código.

En local nada de eso se activa: no hay redirección a https, y CORS permite `localhost:5173`.

## Base de datos (Supabase)

- `docs/esquema.sql` tiene el esquema completo: `profiles`, `events`, `subtasks`, `daily_capacity` y `subtask_execution`.
  - Se ejecuta a mano en Supabase → SQL Editor.
  - Usa `IF NOT EXISTS`, así que no toca tablas que ya existen.
- Parches que ya se aplicaron en producción:
  - `sql/profile_auth.sql`;
  - `sql/subtasks_notes.sql`.

## Usuario demo y datos de ejemplo

En la Shell de Render, con `DEMO_PASSWORD` cargada:

```bash
python manage.py seed_demo                # idempotente: no duplica
python manage.py seed_demo --refrescar    # antes de una demo en otro día: fechas relativas a hoy
```

El comando crea:
- el usuario demo, con un límite de 6 h por día;
- 4 eventos (uno sin gestiones);
- 13 gestiones, entre vencidas, de hoy y próximas, en estado Pendiente, Ejecutada y Pospuesta.

**Caso de sobrecarga:** el día *hoy + 3* ya tiene 5 h pendientes. Reprograma **"Confirmar fotógrafo"** (2 h, del evento *Boda Laura & Andrés*) a ese día: quedaría en 7 h con un límite de 6, y la API responde 409 `overload_conflict`. Para resolverlo, se mueve a otro día, se reduce a 1 h o se pospone.

## Vercel

Variable `VITE_API_URL = https://backend-qs5z.onrender.com` (sin barra final). Después de cambiarla, vuelve a desplegar el frontend.
