# Backend — Organizador de eventos

API Django REST conectada a PostgreSQL/Supabase. Los endpoints de negocio usan JWT HS256 y aíslan los eventos y subtareas por usuario.

## Configuración local

Crea `backend/.env` a partir de `.env.example`:

```env
DATABASE_URL=postgresql://usuario:contraseña@host:5432/base_de_datos
JWT_SECRET=una-clave-aleatoria-larga
FRONTEND_URL=https://tu-frontend.vercel.app
```

`DATABASE_URL` y `JWT_SECRET` son secretos. El archivo `.env` está ignorado por Git y nunca debe subirse al repositorio.

Puedes generar `JWT_SECRET` con:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

En Render configura las mismas variables en **Environment**. `FRONTEND_URL` debe ser el dominio HTTPS real de Vercel. `django-cors-headers` permite el encabezado `Authorization` desde los orígenes configurados.

Instalación y ejecución en Windows:

```powershell
cd C:\Users\Ideapad\Desktop\MiniProyecto1\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Verificación pública de operación:

```http
GET /health
```

La documentación Swagger está en `http://127.0.0.1:8000/docs`.

## Migración de `profiles` en Supabase

El SQL reproducible está en `sql/profile_auth.sql`:

```sql
BEGIN;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS password_hash varchar(128);

CREATE UNIQUE INDEX IF NOT EXISTS profiles_email_ci_unique
    ON public.profiles (LOWER(email));

COMMIT;
```

Si la base tenía la columna heredada `password` en texto plano, después de ejecutar el SQL se migra una sola vez con:

```powershell
.\.venv\Scripts\python.exe manage.py migrar_passwords_profiles
```

El comando:

1. Genera cada hash con `make_password` de Django.
2. Verifica que ningún perfil quede sin hash.
3. Marca `password_hash` como `NOT NULL`.
4. Elimina la columna heredada `password`.

Nunca imprime ni registra las contraseñas.

## Crear integrantes

El comando genera automáticamente el ID, normaliza el correo, valida que sea único y guarda exclusivamente `password_hash`:

```powershell
.\.venv\Scripts\python.exe manage.py crear_usuario "Nombre completo" correo@ejemplo.com
```

La contraseña se solicita dos veces sin mostrarla. Para automatización existe `--password`, pero se recomienda omitirlo porque el valor podría quedar en el historial de la terminal.

Los cuatro integrantes ya existentes se migraron conservando sus IDs y sus contraseñas previas, ahora protegidas con hash. Los dos eventos asociados a `camilo123` permanecen con ese perfil real; Camilo debe iniciar sesión con su correo y contraseña existentes. No se reasignaron datos ni se mantuvo un usuario demo global.

## Autenticación

`POST /login` devuelve un JWT HS256 con:

- `sub`: ID del perfil.
- `iat`: fecha de emisión.
- `exp`: vencimiento ocho horas después.

En Postman, para los endpoints protegidos agrega:

```http
Authorization: Bearer <token>
```

Ejemplo de login:

```http
POST /login
Content-Type: application/json

{
  "email": "correo@ejemplo.com",
  "password": "contraseña-del-usuario"
}
```

Respuesta `200`:

```json
{
  "token": "eyJ...",
  "user": {
    "id": "identificador",
    "name": "Nombre completo",
    "email": "correo@ejemplo.com"
  }
}
```

En Postman puedes guardar el token automáticamente desde **Scripts → Post-response**:

```javascript
const data = pm.response.json();
pm.environment.set("token", data.token);
```

Luego usa en las demás peticiones:

```http
Authorization: Bearer {{token}}
```

Para comprobar una sesión al recargar el frontend:

```http
GET /me
Authorization: Bearer {{token}}
```

Token ausente, alterado o vencido (`401`):

```json
{
  "error": "Tu sesión expiró o no has iniciado sesión."
}
```

Correo inexistente y contraseña incorrecta comparten la respuesta `401`:

```json
{
  "error": "Credenciales inválidas"
}
```

## Endpoints y códigos

| Método y ruta | Éxito | Errores esperados |
|---|---:|---|
| `POST /login` | `200` | `400` campos inválidos, `401` credenciales inválidas |
| `GET /me` | `200` | `401` sesión ausente, inválida o vencida |
| `GET /events` | `200` | `401` |
| `POST /events` | `201` | `400`, `401` |
| `GET /events/<id>` | `200` | `401`, `404` |
| `PATCH /events/<id>` | `200` | `400`, `401`, `404` |
| `DELETE /events/<id>` | `204` | `401`, `404` |
| `GET /events/<id>/subtasks` | `200` | `401`, `404` |
| `POST /events/<id>/subtasks` | `201` | `400`, `401`, `404` |
| `GET /subtasks/<id>` | `200` | `401`, `404` |
| `PATCH /subtasks/<id>` | `200` | `400`, `401`, `404` |
| `DELETE /subtasks/<id>` | `204` | `401`, `404` |
| `GET /today` | `200` | `400` estado inválido, `401`, `404` evento ajeno o inexistente |

Los recursos se consultan siempre con el ID del usuario autenticado. Un evento o subtarea de otro usuario responde `404`, no `403`, para no revelar su existencia.

Filtros combinables de `/today`:

```http
GET /today?event_id=<id>&status=Pendiente
Authorization: Bearer {{token}}
```

`status` solo acepta `Pendiente` o `Pospuesta`.

## Formato global de errores

Campos inválidos (`400`):

```json
{
  "error": "Revisa los campos marcados.",
  "fields": {
    "campo": "Mensaje específico."
  }
}
```

Recurso inexistente o perteneciente a otro usuario (`404`):

```json
{
  "error": "No encontramos lo que buscas."
}
```

## Pruebas

Las pruebas usan mocks y no crean, modifican ni eliminan datos de Supabase:

```powershell
.\.venv\Scripts\python.exe manage.py test
```

Salida verificada:

```text
Found 23 test(s).
System check identified no issues (0 silenced).
.......................
----------------------------------------------------------------------
Ran 23 tests

OK
```

La suite cubre login, errores indistinguibles de credenciales, campos vacíos, JWT de ocho horas, `/me`, ausencia de token, token vencido, token alterado, comando de usuarios, filtros y orden de `/today`, y aislamiento de eventos y subtareas entre dos usuarios.

## Sprint 3: capacidad persistente y resolución

`GET /daily-limit` consulta el límite del usuario autenticado. `PUT /daily-limit` (también PATCH por compatibilidad) recibe `{"daily_limit_hours": 6}`: entero inclusivo 1–16; decimales, vacío y texto responden 400 con `fields`. El default de un perfil es 6. Un límite menor que la carga existente informa sobrecarga en /conflicts, pero no cambia fechas ni tareas.

`GET /conflicts?date=2026-10-11&subtask_id=ID&estimated_hours=2` evalúa la propuesta. `status` es opcional. Sin subtarea evalúa la carga existente. Devuelve `date`, `conflict`, `planned_hours`, `task_hours`, `total_hours`, `daily_limit`, `excess`, `message`, `options` y `suggested_dates`. No cuentan ejecutadas ni otro organizador; la tarea editada se excluye antes de sumar su propuesta. Total igual al límite es válido. Horas admitidas: >0, hasta 999.99, máximo 2 decimales.

`PATCH /subtasks/ID` y `POST /events/ID/subtasks` vuelven a evaluar capacidad al persistir. Un mutex transaccional por perfil evita aceptar dos cambios concurrentes que juntos sobrecarguen el día. Si excede: 409 con `{"error":"...","code":"overload_conflict","conflict":{...}}`, sin guardar cambios parciales. Recursos ajenos: 404; sin JWT válido: 401 global. Posponer explícitamente conserva fecha/horas y sigue contando como carga; cancelar no es un endpoint y no cambia nada.

Fechas desde hoy (zona America/Bogota), no después del evento. Las pruebas de persistencia reales usan SQLite temporal, nunca Supabase: `python manage.py test`.

### Entorno QA local aislado

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=django_crud_api.qa_settings
.\.venv\Scripts\python.exe manage.py preparar_qa --settings=django_crud_api.qa_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=django_crud_api.qa_settings
```

Este settings usa exclusivamente `qa.sqlite3` ignorado por Git, datos ficticios y clave local, nunca producción. El comando imprime las cuentas de prueba. `qa-fail-next.flag` provoca un único 503 antes del próximo PATCH/PUT sin escritura; `qa-delay.flag` retrasa consultas 2 segundos. Ambos funcionan solo con qa_settings; retirar el archivo de demora al terminar. No configurar estos settings en Render. Las evidencias locales no certifican automáticamente el despliegue externo.
