# d:\AAA_Framework\ProjectFrameworksas\myapp\views.py

from django.shortcuts import render, redirect
from .models import EjecucionMatriz, Empresa, RequisitoLegal
from django.contrib.auth.decorators import login_required
# No necesitamos importar CustomUser aquí si no lo usamos directamente
# from users_app.models import CustomUser
from django.contrib import messages
from django.http import QueryDict, JsonResponse
from django_select2.views import AutoResponseView # Correcto
from django.db.models import Q
import logging # Añadir logging

logger = logging.getLogger(__name__) # Configurar logger

@login_required # Asegura que solo usuarios logueados accedan
def home(request):
    """
    Vista principal que muestra información basada en la empresa seleccionada.
    Utiliza 'request.selected_company' añadido por el middleware.
    """
    user = request.user
    # Obtener la empresa seleccionada del request (añadida por CompanyMiddleware)
    selected_company = getattr(request, 'selected_company', None)

    company_name = None
    logo_url = None

    if selected_company:
        company_name = selected_company.nombreempresa
        if selected_company.logo:
            try:
                logo_url = selected_company.logo.url
            except ValueError:
                # Esto puede pasar si el archivo del logo no existe o está corrupto
                logger.error(f"Error al obtener la URL del logo para la empresa {selected_company.codigoempresa}")
                logo_url = None # Asegurarse que es None si hay error
        logger.debug(f"Home View: Empresa={company_name}, Logo URL={logo_url}")
    else:
        logger.debug("Home View: No hay empresa seleccionada.")

    context = {
        'company_name': company_name,
        'logo_url': logo_url,
        'user': user # Pasamos el objeto user completo por si la plantilla lo necesita
    }
    # --- CORRECCIÓN IMPORTANTE: RUTA DE LA PLANTILLA ---
    # Asumiendo que home.html está en myapp/templates/myapp/home.html
    # Si está en myapp/templates/home.html, quita 'myapp/'
    return render(request, 'home.html', context)
    # ----------------------------------------------------

def mi_pagina_de_error(request, exception=None):
    """
    Vista para mostrar errores personalizados.
    """
    status_code = 500 # Por defecto
    if hasattr(exception, 'status_code'):
        status_code = exception.status_code
    elif isinstance(exception, PermissionDenied):
        status_code = 403
    # Puedes añadir más lógica para determinar el status_code

    # Asegúrate que la ruta 'myapp/mi_pagina_de_error.html' sea correcta
    return render(request, 'myapp/mi_pagina_de_error.html', {'exception': exception, 'error_code': status_code}, status=status_code)


# --- Vista AJAX para Select2 (Sin cambios respecto a tu versión) ---
class RequisitoLegalSelect2View(AutoResponseView):
    """
    Vista AJAX para el widget Select2 que busca en RequisitoLegal
    usando AutoResponseView.
    """
    queryset = RequisitoLegal.objects.select_related('pais').order_by('tema', 'numero')
    search_fields = [
        'tema__icontains',
        'entidad_que_emite__icontains',
        'numero__icontains',
        'articulo_aplicable__icontains',
        'Obligacion__icontains',
    ]
# --- FIN DE LA CLASE ---
