# d:\AAA_Framework\ProjectFrameworksas\core\management\commands\create_initial_superuser.py
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates a superuser non-interactively using environment variables, if it does not already exist.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        if not all([username, email, password]):
            self.stdout.write(self.style.ERROR(
                'Missing DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, or DJANGO_SUPERUSER_PASSWORD environment variables.'
            ))
            return # Salir si faltan variables

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists. Skipping creation.'))
        else:
            self.stdout.write(f'Creating superuser "{username}"...')
            try:
                User.objects.create_superuser(username=username, email=email, password=password)
                self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created successfully.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating superuser: {e}'))

