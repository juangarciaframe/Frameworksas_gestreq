"""
WSGI config for ProjectFrameworksas project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from whitenoise import WhiteNoise # Importar WhiteNoise
from django.core.wsgi import get_wsgi_application
from django.conf import settings # Importar settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ProjectFrameworksas.settings")

application = get_wsgi_application()

# Los archivos estáticos son servidos por WhiteNoiseMiddleware configurado en settings.py

# Si necesitas servir archivos MEDIA con WhiteNoise (no ideal para producción a gran escala,
# pero puede ser necesario si no tienes otra opción de servidor de archivos):
if not settings.DEBUG: # Usualmente en DEBUG, Django puede servir media si se configura en urls.py
    # Asegurarse de que MEDIA_ROOT exista si WhiteNoise lo va a usar
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    application = WhiteNoise(application) # Envuelve la aplicación Django
    application.add_files(settings.MEDIA_ROOT, prefix=settings.MEDIA_URL) # Añade los archivos de media
