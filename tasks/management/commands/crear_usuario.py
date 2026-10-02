from getpass import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError

from tasks.models import Profile, generar_id


class Command(BaseCommand):
    help = 'Crea un perfil con correo único y contraseña protegida con hash de Django.'

    def add_arguments(self, parser):
        parser.add_argument('nombre', help='Nombre completo del integrante.')
        parser.add_argument('correo', help='Correo único del integrante.')
        parser.add_argument(
            '--password',
            help='Contraseña. Si se omite, se solicita de forma segura sin mostrarla.',
        )

    def handle(self, *args, **options):
        nombre = options['nombre'].strip()
        correo = options['correo'].strip().lower()
        password = options['password']

        if not nombre:
            raise CommandError('El nombre es obligatorio.')
        if not correo:
            raise CommandError('El correo es obligatorio.')

        try:
            validate_email(correo)
        except ValidationError as exc:
            raise CommandError('El correo no tiene un formato válido.') from exc

        if Profile.objects.filter(email__iexact=correo).exists():
            raise CommandError('Ya existe un usuario con ese correo.')

        if password is None:
            password = getpass('Contraseña: ')
            confirmation = getpass('Confirma la contraseña: ')
            if password != confirmation:
                raise CommandError('Las contraseñas no coinciden.')

        if not password:
            raise CommandError('La contraseña es obligatoria.')

        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages)) from exc

        try:
            profile = Profile.objects.create(
                id=generar_id(),
                name=nombre,
                email=correo,
                password_hash=make_password(password),
            )
        except IntegrityError as exc:
            raise CommandError('No se pudo crear el usuario; verifica que el correo sea único.') from exc

        self.stdout.write(self.style.SUCCESS(
            f'Usuario creado: {profile.name} <{profile.email}> (id={profile.id})'
        ))
