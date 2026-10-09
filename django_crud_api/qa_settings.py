"""Entorno QA local aislado, sin credenciales ni datos de producción."""
from .settings import *  # noqa: F403
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'qa.sqlite3'}}
JWT_SECRET = 'local-qa-only-not-a-production-secret'
TIME_ZONE = 'America/Bogota'
MIDDLEWARE = ['tasks.qa_middleware.QAFailureMiddleware'] + MIDDLEWARE
