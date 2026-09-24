# Backend — Organizador de eventos

## Ejecutar en Windows

1. Verifica que exista `backend/.env` con la variable `DATABASE_URL` de Supabase.
2. Haz doble clic en `start-backend.cmd` o ejecútalo desde PowerShell:

```powershell
.\start-backend.cmd
```

El script crea `.venv` si hace falta, instala las dependencias, comprueba Django, verifica la conexión con Supabase y levanta el servidor en `http://127.0.0.1:8000`.

Para confirmar que funciona, abre `http://127.0.0.1:8000/health`. Debe responder:

```json
{"status": "ok", "database": "connected", "message": "Backend funcionando"}
```

Si aparece que el puerto 8000 está ocupado, ya hay otro backend ejecutándose. Detén esa terminal con `Ctrl+C` antes de volver a iniciar el script.

Si aparece `No fue posible conectar con Supabase`, revisa la conexión a Internet y vuelve a intentar. Un fallo `getaddrinfo failed` indica que Windows no pudo resolver temporalmente el servidor de Supabase.

El aviso sobre migraciones de `admin`, `auth`, `contenttypes` y `sessions` no detiene esta API. Las tablas de eventos y subtareas de este proyecto ya son administradas por Supabase.
