# d:\AAA_Framework\ProjectFrameworksas\myapp\views.py

from django.shortcuts import render, redirect
from .models import EjecucionMatriz, Empresa, RequisitoLegal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import QueryDict, JsonResponse
from django_select2.views import AutoResponseView # Correcto
from django.db.models import Q
import logging # Añadir logging
from django.contrib import admin # Para el decorador @admin.site.admin_view
from datetime import date, timedelta # Para fechas en Gantt
import json # Para pasar datos a la plantilla Gantt
from django.core.serializers.json import DjangoJSONEncoder # Para serializar fechas, etc.
from django.utils.html import escape # Para seguridad en Gantt
from users_app.models import CustomUser # Necesario para el filtro de responsables en Gantt
from .models import Plan # Asegúrate de importar Plan
from .utils import add_working_days # Para calcular fechas finales en Gantt

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
    # Necesitarías importar PermissionDenied de django.core.exceptions
    # from django.core.exceptions import PermissionDenied
    # elif isinstance(exception, PermissionDenied):
    #     status_code = 403
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


# --- Vista Gantt para Planes (Tareas) ---
@admin.site.admin_view # O @login_required si prefieres que no sea solo para admin
def plan_gantt_view(request):
    target_year_str = request.GET.get('year', str(date.today().year))
    logger.critical(f"plan_gantt_view: LA VISTA HA SIDO LLAMADA. Año str: {target_year_str}") # Log de alta prioridad
    selected_responsable_id_str = request.GET.get('responsable_id')
    selected_company = getattr(request, 'selected_company', None)

    logger.debug(f"plan_gantt_view - Request GET: {request.GET}")
    logger.debug(f"plan_gantt_view - Selected Company: {selected_company.nombreempresa if selected_company else 'None'}")

    # Optimizar consulta para incluir datos necesarios
    plans_qs = Plan.objects.select_related(
        'requisito_empresa__requisito__pais',
        'sede',
        'empresa'
    ).prefetch_related(
        'ejecucionmatriz_set',
        'responsables_ejecucion'
    )

    try:
        target_year = int(target_year_str)
    except (ValueError, TypeError):
        target_year = date.today().year
        logger.warning(f"Año inválido '{target_year_str}', usando año actual: {target_year}")

    if selected_company:
        plans_qs = plans_qs.filter(empresa=selected_company, year=target_year)
        logger.debug(f"plan_gantt_view - Después de filtrar por empresa y año: {plans_qs.count()} planes.")

    else:
        if not request.user.is_superuser:
            plans_qs = plans_qs.none()
            logger.debug(f"plan_gantt_view - No superusuario y sin empresa: 0 planes.")

        else:
            plans_qs = plans_qs.filter(year=target_year) # Superuser ve todo el año
            logger.debug(f"plan_gantt_view - Superusuario, filtrado por año: {plans_qs.count()} planes.")


    # --- Lógica de filtro por responsable ---
    responsable_ids_in_current_view = set()
    # Iterar sobre el queryset *antes* de aplicar el filtro de responsable
    # para obtener todos los posibles responsables en la vista actual (año/empresa)
    temp_plans_for_responsable_scan = list(plans_qs) # Evaluar el queryset una vez para esto

    for plan_item in temp_plans_for_responsable_scan:
        for resp in plan_item.responsables_ejecucion.all():
            responsable_ids_in_current_view.add(resp.id)
    
    responsables_disponibles = CustomUser.objects.filter(id__in=list(responsable_ids_in_current_view)).order_by('username')
    logger.debug(f"Responsables disponibles para filtro: {[r.username for r in responsables_disponibles]} (Total: {responsables_disponibles.count()})")

    selected_responsable_id = None
    if selected_responsable_id_str:
        if selected_responsable_id_str.isdigit():
            try:
                selected_responsable_id = int(selected_responsable_id_str)
                plans_qs = plans_qs.filter(responsables_ejecucion__id=selected_responsable_id)
                logger.debug(f"Plans_qs después de filtrar por responsable ID {selected_responsable_id}: {plans_qs.count()} planes.")
            except ValueError:
                selected_responsable_id = None
                logger.warning(f"Error al convertir ID de responsable: {selected_responsable_id_str}. No se filtra por responsable.")
        elif selected_responsable_id_str == "": # Opción "Todos los responsables"
            logger.debug("Opción 'Todos los Responsables' seleccionada. No se filtra adicionalmente por responsable.")
            # selected_responsable_id ya es None o se puede establecer a "" para el template
            selected_responsable_id = "" 
    
    # **Transformar Datos para Frappe Gantt:**
    tasks_for_gantt = []
    for plan in plans_qs: # Iterar sobre el queryset ya filtrado (incluyendo por responsable si aplica)
        start_date_obj = plan.fecha_proximo_cumplimiento
        if not start_date_obj:
            logger.debug(f"plan_gantt_view - Plan ID {plan.id} OMITIDO porque fecha_proximo_cumplimiento es None.")
            continue

        end_date_obj = start_date_obj
        tiempo_val = None
        country_code = None

        if plan.requisito_empresa:
            tiempo_val = plan.requisito_empresa.tiempo_validacion
            if plan.requisito_empresa.requisito and plan.requisito_empresa.requisito.pais:
                country_code = plan.requisito_empresa.requisito.pais.codigo

        if tiempo_val is not None and tiempo_val > 0:
            dias_a_sumar_para_gantt = tiempo_val - 1
            calculated_end_date = None
            if country_code:
                calculated_end_date = add_working_days(start_date_obj, dias_a_sumar_para_gantt, country_code)
            
            if calculated_end_date:
                end_date_obj = calculated_end_date
            else:
                end_date_obj = start_date_obj + timedelta(days=max(0, dias_a_sumar_para_gantt))
        
        progress = 0
        ejecucion_asociada = plan.ejecucionmatriz_set.first()
        if ejecucion_asociada:
            progress = ejecucion_asociada.porcentaje_cumplimiento

        tema = escape(plan.requisito_empresa.requisito.tema) if plan.requisito_empresa and plan.requisito_empresa.requisito and plan.requisito_empresa.requisito.tema else "N/A"
        obligacion = escape(plan.requisito_empresa.requisito.Obligacion) if plan.requisito_empresa and plan.requisito_empresa.requisito and plan.requisito_empresa.requisito.Obligacion else "N/A"
        sede_nombre = escape(plan.sede.nombre) if plan.sede else "N/A"
        task_name = f"{tema} / {obligacion} - Sede: {sede_nombre}"

        tasks_for_gantt.append({
            'id': str(plan.id),
            'name': task_name,
            'start': start_date_obj.isoformat(),
            'end': end_date_obj.isoformat(),
            'progress': progress,
            'dependencies': '',
        })

    logger.info(f"plan_gantt_view - Número de tareas generadas para Gantt: {len(tasks_for_gantt)}")
    gantt_data_json = json.dumps(tasks_for_gantt, cls=DjangoJSONEncoder)
    current_year_for_template = date.today().year
    year_options = [current_year_for_template + i for i in range(-2, 5)] # Genera 5 años: actual-2 a actual+2


    context = {
        'title': f"Plan de Cumplimiento (Gantt) - Año {target_year}",
        'gantt_data_json': gantt_data_json,
        'selected_year': target_year,
        'year_options': year_options, # Pasar las opciones de año a la plantilla
        'responsables_disponibles': responsables_disponibles,
        'selected_responsable_id': selected_responsable_id,
        'current_year': current_year_for_template, # Puede ser útil si aún lo necesitas para algo más
        'opts': Plan._meta, # Para la plantilla base del admin
        'site_header': admin.site.site_header,
        'site_title': admin.site.site_title,
        'is_popup': False,
        'is_nav_sidebar_enabled': True,
    }
    return render(request, 'admin/myapp/plan/plan_gantt.html', context)
# --- FIN VISTA GANTT ---
