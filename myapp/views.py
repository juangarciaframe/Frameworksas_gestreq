# d:\AAA_Framework\ProjectFrameworksas\myapp\views.py

from django.shortcuts import render, redirect
from .models import EjecucionMatriz, Empresa, RequisitoLegal, Plan # Asegúrate de importar Plan
from django.contrib.auth.decorators import login_required
# No necesitamos importar CustomUser aquí si no lo usamos directamente
# from users_app.models import CustomUser
from django.contrib import messages
from django.http import QueryDict, JsonResponse
from django_select2.views import AutoResponseView # Correcto
from django.db.models import Q
import logging # Añadir logging
import json # Para convertir a JSON
from django.urls import reverse # Para generar URLs del admin
from django.utils.html import escape # Para seguridad en el nombre

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

# --- Vista para el Gantt Chart (MODIFICADA) ---
@login_required # Es buena idea proteger esta vista
def plan_gantt_chart(request):
    # Obtener la empresa seleccionada por el usuario (si aplica)
    selected_company_id = request.session.get('selected_company_id')
    if not selected_company_id:
        # Redirigir o mostrar error si no hay empresa seleccionada
        # (Ajusta según tu lógica de selección de empresa)
        return render(request, 'myapp/error.html', {'message': 'Por favor, seleccione una empresa.'})

    try:
        selected_company = Empresa.objects.get(id=selected_company_id) # type: ignore
    except Empresa.DoesNotExist:
        return render(request, 'myapp/error.html', {'message': 'Empresa seleccionada no válida.'})

    # Filtrar planes por la empresa seleccionada y ordenar
    plans = Plan.objects.select_related(
        'requisito_empresa__requisito',
        'responsable_ejecucion',
        'sede',
        'empresa'
    ).filter(
        empresa=selected_company
        # Puedes añadir más filtros si es necesario (ej. por año)
    ).order_by('fecha_proximo_cumplimiento', 'sede__nombre') # Ordenar

    tasks = []
    for plan in plans:
        # --- Construir el nombre descriptivo ---
        tema = escape(plan.requisito_empresa.requisito.tema) if plan.requisito_empresa and plan.requisito_empresa.requisito else "N/A"
        obligacion = escape(plan.requisito_empresa.requisito.Obligacion) if plan.requisito_empresa and plan.requisito_empresa.requisito else "N/A"
        responsable_username = escape(plan.responsable_ejecucion.username) if plan.responsable_ejecucion else "N/A"
        sede_nombre = escape(plan.sede.nombre) if plan.sede else "N/A"

        # Formato: Tema / Obligación - Sede - Resp: Usuario
        task_name = f"{tema} / {obligacion} - Sede: {sede_nombre} - Resp: {responsable_username}"

        # --- Generar URL del Admin ---
        # Asegúrate que 'myapp' es el nombre correcto de tu app en el admin
        admin_url = reverse('admin:myapp_plan_change', args=[plan.id])

        # --- Fechas ---
        # Usamos fecha_proximo_cumplimiento como inicio y fin (tarea puntual)
        # Podrías ajustar esto si tienes una duración estimada
        start_date = plan.fecha_proximo_cumplimiento
        end_date = plan.fecha_proximo_cumplimiento

        if start_date and end_date: # Solo añadir tareas con fechas válidas
            tasks.append({
                'id': str(plan.id), # ID debe ser string
                'name': task_name, # Nombre descriptivo
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d'),
                'progress': 0, # Puedes calcular esto si tienes estado de ejecución
                'dependencies': '', # Añadir dependencias si aplica
                'custom_class': 'bar-milestone', # Estilo para tareas puntuales
                'admin_url': admin_url # URL para el clic
            })

    context = {
        # Convertir a JSON de forma segura para el template
        'tasks_json': json.dumps(tasks)
    }
    return render(request, 'myapp/plan_gantt_chart.html', context)
# --- FIN VISTA GANTT ---
