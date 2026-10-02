from datetime import timedelta

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import Profile


SESSION_ERROR = 'Tu sesión expiró o no has iniciado sesión.'


def jwt_secret():
    if not settings.JWT_SECRET:
        raise ImproperlyConfigured('Configura JWT_SECRET en las variables de entorno.')
    return settings.JWT_SECRET


def create_access_token(profile_id):
    issued_at = timezone.now()
    expires_at = issued_at + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    return jwt.encode(
        {
            'sub': str(profile_id),
            'iat': issued_at,
            'exp': expires_at,
        },
        jwt_secret(),
        algorithm='HS256',
    )


class JWTAuthentication(BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        header = get_authorization_header(request).split()

        if not header:
            return None

        if len(header) != 2 or header[0].decode().lower() != self.keyword.lower():
            raise AuthenticationFailed(SESSION_ERROR, code='invalid_session')

        try:
            token = header[1].decode()
            payload = jwt.decode(
                token,
                jwt_secret(),
                algorithms=['HS256'],
                options={'require': ['sub', 'exp']},
            )
            profile = Profile.objects.get(pk=payload['sub'])
        except (UnicodeDecodeError, jwt.InvalidTokenError, Profile.DoesNotExist):
            raise AuthenticationFailed(SESSION_ERROR, code='invalid_session') from None

        return profile, token

    def authenticate_header(self, request):
        return self.keyword


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'tasks.authentication.JWTAuthentication'
    name = 'BearerAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
