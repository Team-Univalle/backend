"""Historia de despliegue: /health, CORS, ajustes de producción, seed_demo y ejemplos de Swagger."""
import json
import os
import subprocess
import sys
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import api_docs
from .authentication import create_access_token
from .management.commands.seed_demo import demo_id
from .models import Event, Profile, Subtask

BASE_DIR = Path(settings.BASE_DIR)
FRONTEND = 'https://frontend-vert-one-pt320cfqws.vercel.app'


class HealthTests(TestCase):
    def test_health_es_publico_y_comprueba_la_base(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_health_sin_base_responde_503_sin_detalle(self):
        with patch('django_crud_api.urls.connection.cursor', side_effect=RuntimeError('host=db password=SECRETO')), \
                self.assertLogs('django_crud_api.urls', level='ERROR'):
            response = self.client.get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['database'], 'disconnected')
        self.assertNotIn('SECRETO', response.content.decode())

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r'^health$', r'^$'])
    def test_redireccion_https_respeta_health(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        response = self.client.get('/events')
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response['Location'].startswith('https://'))


class CorsTests(SimpleTestCase):
    def preflight(self, origin):
        return self.client.options(
            '/events', HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization',
        )

    def test_frontend_de_produccion_esta_permitido(self):
        response = self.preflight(FRONTEND)
        self.assertEqual(response['Access-Control-Allow-Origin'], FRONTEND)
        self.assertIn('authorization', response['Access-Control-Allow-Headers'])

    def test_otro_origen_es_rechazado(self):
        self.assertNotIn('Access-Control-Allow-Origin', self.preflight('https://sitio-falso.com'))


def settings_en_subproceso(**env):
    """Carga settings.py con otro entorno (como lo vería Render) y devuelve los valores relevantes."""
    code = (
        'import json, os, django\n'
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_crud_api.settings')\n"
        'django.setup()\n'
        'from django.conf import settings as s\n'
        "print(json.dumps({'DEBUG': s.DEBUG, 'ALLOWED_HOSTS': s.ALLOWED_HOSTS, 'CORS': s.CORS_ALLOWED_ORIGINS,"
        " 'REDIRECT': getattr(s, 'SECURE_SSL_REDIRECT', False), 'PROXY': getattr(s, 'SECURE_PROXY_SSL_HEADER', None),"
        " 'COOKIES': getattr(s, 'SESSION_COOKIE_SECURE', False), 'SECRET_LEN': len(s.SECRET_KEY),"
        " 'CONN_MAX_AGE': s.DATABASES['default'].get('CONN_MAX_AGE')}))\n"
    )
    base = {k: v for k, v in os.environ.items() if k not in (
        'RENDER', 'DJANGO_ENV', 'DEBUG', 'CORS_ALLOWED_ORIGINS', 'ALLOWED_HOSTS', 'FRONTEND_URL', 'SECRET_KEY',
        'RENDER_EXTERNAL_HOSTNAME', 'DB_CONN_MAX_AGE',
    )}
    # Valores vacíos/ficticios explícitos: load_dotenv no pisa variables ya definidas, así no se usa el .env real.
    base.update({'DATABASE_URL': 'postgresql://u:p@localhost:5432/db', 'JWT_SECRET': 'ficticio-' + 'x' * 40})
    base.update(env)
    result = subprocess.run([sys.executable, '-c', code], cwd=BASE_DIR, env=base, capture_output=True, text=True)
    return result


class ProductionSettingsTests(SimpleTestCase):
    def valores(self, **env):
        result = settings_en_subproceso(**env)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_en_render_aplica_https_y_cors_estricto(self):
        v = self.valores(RENDER='true', RENDER_EXTERNAL_HOSTNAME='backend-qs5z.onrender.com', SECRET_KEY='s' * 60)
        self.assertFalse(v['DEBUG'])
        self.assertTrue(v['REDIRECT'])
        self.assertEqual(v['PROXY'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        self.assertTrue(v['COOKIES'])
        self.assertIn('backend-qs5z.onrender.com', v['ALLOWED_HOSTS'])
        self.assertNotIn('localhost', v['ALLOWED_HOSTS'])
        self.assertEqual(v['CORS'], [FRONTEND])  # sin variable: el frontend actual, nunca localhost

    def test_cors_desde_variable_sin_barra_final(self):
        v = self.valores(RENDER='true', CORS_ALLOWED_ORIGINS='https://a.vercel.app/ , https://b.vercel.app')
        self.assertEqual(v['CORS'], ['https://a.vercel.app', 'https://b.vercel.app'])

    def test_en_local_no_redirige_y_permite_vite(self):
        v = self.valores()
        self.assertFalse(v['REDIRECT'])
        self.assertIn('http://localhost:5173', v['CORS'])
        self.assertIn('localhost', v['ALLOWED_HOSTS'])

    def test_secret_key_nunca_viene_escrita_en_el_codigo(self):
        self.assertNotIn('django-insecure', (BASE_DIR / 'django_crud_api' / 'settings.py').read_text())
        self.assertGreaterEqual(self.valores(RENDER='true')['SECRET_LEN'], 50)  # derivada de JWT_SECRET
        result = settings_en_subproceso(RENDER='true', JWT_SECRET='', SECRET_KEY='')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY', result.stderr)

    def test_pooler_de_transacciones_no_reutiliza_conexiones(self):
        v = self.valores(DATABASE_URL='postgresql://u:p@host.pooler.supabase.com:6543/postgres')
        self.assertEqual(v['CONN_MAX_AGE'], 0)
        self.assertEqual(self.valores()['CONN_MAX_AGE'], 600)


@patch.dict(os.environ, {'DEMO_EMAIL': 'demo@organiza-eventos.app', 'DEMO_PASSWORD': 'Demo-Prueba-Segura-2026'})
@override_settings(JWT_SECRET='isolated-seed-tests-secret-not-for-production')
class SeedDemoTests(TestCase):
    EMAIL = 'demo@organiza-eventos.app'

    def seed(self, *args):
        out = StringIO()
        call_command('seed_demo', *args, stdout=out)
        return out.getvalue()

    def client_demo(self):
        client = APIClient()
        response = client.post('/login', {'email': self.EMAIL, 'password': 'Demo-Prueba-Segura-2026'}, format='json')
        self.assertEqual(response.status_code, 200)
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['token'])
        return client

    def test_es_idempotente(self):
        self.seed()
        cuentas = (Profile.objects.count(), Event.objects.count(), Subtask.objects.count())
        self.assertIn('Nuevos: 0 perfil, 0 eventos, 0 gestiones', self.seed())
        self.assertEqual((Profile.objects.count(), Event.objects.count(), Subtask.objects.count()), cuentas)
        self.assertEqual(cuentas, (1, 4, 13))

    def test_password_hasheada_y_login_real(self):
        self.seed()
        profile = Profile.objects.get(email=self.EMAIL)
        self.assertNotIn('Demo-Prueba-Segura-2026', profile.password_hash)
        self.assertTrue(profile.password_hash.startswith('pbkdf2_'))
        data = self.client_demo().get('/events').json()
        self.assertEqual(len(data), 4)
        self.assertTrue(any(e['total_subtasks'] == 0 for e in data))  # evento vacío para Progreso

    def test_hoy_tiene_vencidas_de_hoy_y_proximas(self):
        self.seed()
        data = self.client_demo().get('/today').json()
        self.assertTrue(data['vencidas'] and data['hoy'] and data['proximas'])
        estados = set(Subtask.objects.values_list('status', flat=True))
        self.assertEqual(estados, {'Pendiente', 'Ejecutada', 'Pospuesta'})

    def test_caso_de_sobrecarga_documentado(self):
        self.seed()
        client = self.client_demo()
        fotografo = demo_id(self.EMAIL, 'boda', 'fotografo')
        dia = timezone.localdate() + timedelta(days=3)
        check = client.get('/conflicts', {'date': str(dia), 'subtask_id': fotografo}).json()
        self.assertEqual((check['conflict'], check['planned_hours'], check['total_hours'], check['excess']), (True, 5, 7, 1))
        response = client.patch('/subtasks/' + fotografo, {'target_date': str(dia)}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'overload_conflict')

    def test_refrescar_recalcula_fechas(self):
        self.seed()
        salon = Subtask.objects.get(id=demo_id(self.EMAIL, 'boda', 'salon'))
        Subtask.objects.filter(pk=salon.pk).update(target_date=salon.target_date - timedelta(days=30), status='Ejecutada')
        self.seed('--refrescar')
        salon.refresh_from_db()
        self.assertEqual((salon.target_date, salon.status), (timezone.localdate() - timedelta(days=2), 'Pendiente'))

    def test_no_toca_un_perfil_real_con_el_mismo_correo(self):
        Profile.objects.create(id='real-1', name='Real', email=self.EMAIL, password_hash=make_password('x' * 12))
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(Event.objects.count(), 0)

    def test_sin_password_no_crea_nada(self):
        with patch.dict(os.environ, {'DEMO_PASSWORD': ''}), self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(Profile.objects.count(), 0)


@override_settings(JWT_SECRET='isolated-swagger-tests-secret-not-for-production')
class SwaggerExamplesMatchApiTest(TestCase):
    """Los ejemplos de Swagger coinciden con lo que la API responde de verdad."""

    def setUp(self):
        self.user = Profile.objects.create(id='qa-docs', name='QA', email='qa-docs@example.invalid',
                                           password_hash=make_password('Clave-QA-Docs-2026'))
        today = timezone.localdate()
        self.event = Event.objects.create(user=self.user, name='Evento QA', type='boda', event_date=today + timedelta(days=20))
        self.item = Subtask.objects.create(event=self.event, name='Gestión QA', estimated_hours=2, target_date=today + timedelta(days=5))
        Subtask.objects.create(event=self.event, name='Carga QA', estimated_hours=5, target_date=today + timedelta(days=3))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.user.id))

    def ejemplo(self, ejemplos, nombre):
        return next(e.value for e in ejemplos if e.name == nombre)

    def test_swagger_publicado(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertEqual(self.client.get('/api/docs/').status_code, 200)
        self.assertEqual(self.client.get('/docs').status_code, 200)  # ruta anterior se mantiene

    def test_errores_identicos_a_la_api(self):
        anon = APIClient()
        casos = [
            (anon.post('/login', {'email': '', 'password': ''}, format='json'), api_docs.LOGIN, '400 · Campos vacíos'),
            (anon.post('/login', {'email': 'x@example.invalid', 'password': 'mal'}, format='json'), api_docs.LOGIN, '401 · Datos incorrectos'),
            (anon.get('/me'), api_docs.ME, '401 · Sin sesión'),
            (self.client.post('/events', {'name': '', 'type': 'boda', 'event_date': '2026-12-01'}, format='json'), api_docs.EVENTOS_CREAR, '400 · Campos inválidos'),
            (self.client.post('/events', '{"name":', content_type='application/json'), api_docs.EVENTOS_CREAR, '400 · JSON mal formado'),
            (self.client.get('/events/no-existe'), api_docs.EVENTO_DETALLE, '404 · No existe'),
            (self.client.patch('/subtasks/' + self.item.id, {'estimated_hours': 0}, format='json'), api_docs.GESTIONES_CREAR, '400 · Horas en 0'),
            (self.client.patch('/subtasks/' + self.item.id, {'notes': 'a' * 501}, format='json'), api_docs.GESTION_EDITAR, '400 · Nota muy larga'),
            (self.client.patch('/daily-limit', {'daily_limit_hours': 99}, format='json'), api_docs.LIMITE_ACTUALIZAR, '400 · Fuera de rango'),
            (self.client.get('/conflicts'), api_docs.CONFLICTOS, '400 · Falta la fecha'),
            (self.client.get('/today', {'status': 'Otro'}), api_docs.HOY, '400 · Estado no válido'),
        ]
        for response, ejemplos, nombre in casos:
            with self.subTest(nombre):
                self.assertEqual(response.json(), self.ejemplo(ejemplos, nombre))

    def test_respuestas_exitosas_tienen_las_mismas_llaves(self):
        dia = timezone.localdate() + timedelta(days=3)
        conflicto = self.client.patch('/subtasks/' + self.item.id, {'target_date': str(dia)}, format='json').json()
        casos = [
            (self.client.get('/events/' + self.event.id).json(), api_docs.EVENTO),
            (self.client.get('/subtasks/' + self.item.id).json(), api_docs.GESTION),
            (self.client.get('/today').json()['proximas'][0], api_docs.GESTION_HOY),
            (self.client.get('/me').json(), api_docs.USUARIO),
            (self.client.get('/daily-limit').json(), self.ejemplo(api_docs.LIMITE_CONSULTAR, '200 · Límite actual')),
            (self.client.get('/conflicts', {'date': str(dia), 'subtask_id': self.item.id}).json(),
             self.ejemplo(api_docs.CONFLICTOS, '200 · Hay sobrecarga')),
            (conflicto, self.ejemplo(api_docs.GESTION_EDITAR, '409 · Sobrecarga del día')),
            (conflicto['conflict'], api_docs.CONFLICTO),
        ]
        login = APIClient().post('/login', {'email': 'qa-docs@example.invalid', 'password': 'Clave-QA-Docs-2026'}, format='json')
        casos.append((login.json(), api_docs.SESION))
        for real, ejemplo in casos:
            with self.subTest(sorted(ejemplo)):
                self.assertEqual(set(real), set(ejemplo))
