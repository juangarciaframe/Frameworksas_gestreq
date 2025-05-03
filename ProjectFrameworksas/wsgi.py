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

# Asegurarse de que MEDIA_ROOT exista antes de que WhiteNoise lo use
os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

# Añadir WhiteNoise para servir media (NO RECOMENDADO PARA PRODUCCIÓN)
application = WhiteNoise(application, root=settings.MEDIA_ROOT)
application.add_files(settings.MEDIA_ROOT, prefix=settings.MEDIA_URL)
