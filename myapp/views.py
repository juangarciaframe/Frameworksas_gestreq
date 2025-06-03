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
from django.urls import reverse # Para generar URLs en la vista
from .models import Plan # Asegúrate de importar Plan
from .utils import add_working_days # Para calcular fechas finales en Gantt

from django.db.models import Prefetch, Q
from datetime import date, timedelta
import json
from django.core.serializers.json import DjangoJSONEncoder
from users_app.models import CustomUser # Asegúrate que esté importado
from .models import Plan, EjecucionMatriz # Asegúrate que estén importados
from django.contrib.auth.decorators import login_required # Asegúrate que esté importado
from django.shortcuts import render # Asegúrate que esté importado
from django.contrib import messages # Asegúrate que esté importado
import logging # Asegúrate que esté importado
import calendar # Para obtener el último día del mes
from django.utils import timezone # Para la fecha actual con zona horaria

# Nuevas importaciones para ejecucion_matriz_direct_form_view
from django.shortcuts import get_object_or_404
from django.http import Http404
# myapp/views.py
from django.shortcuts import render
from django.contrib.admin.models import LogEntry
from django.contrib.auth.decorators import login_required, user_passes_test


# from .forms import EjecucionMatrizDirectForm # Ya no es necesario si solo redirigimos al admin



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
@login_required
#@admin.site.admin_view # O @login_required si prefieres que no sea solo para admin
def plan_gantt_view(request):
    target_year_str = request.GET.get('year', str(date.today().year))
    selected_responsable_id_str = request.GET.get('responsable_id')
    selected_months_str = request.GET.getlist('months') # Obtener lista de meses seleccionados
    selected_company = getattr(request, 'selected_company', None)

 
    # Optimizar consulta para incluir datos necesarios
    plans_qs = Plan.objects.select_related(
        'requisito_empresa__requisito__pais',
        'sede',
        'empresa'
    ).prefetch_related(
        'ejecucionmatriz',
        'responsables_ejecucion'
    )

    try:
        target_year = int(target_year_str)
    except (ValueError, TypeError):
        target_year = date.today().year
 
    if selected_company:
        plans_qs = plans_qs.filter(empresa=selected_company, year=target_year)
 
    else:
        if not request.user.is_superuser:
            plans_qs = plans_qs.none()
 
        else:
            plans_qs = plans_qs.filter(year=target_year) # Superuser ve todo el año
 
    # Si el usuario no es superusuario, filtrar adicionalmente por los planes asignados a él.
    if not request.user.is_superuser:
        # Es seguro filtrar un queryset que ya podría ser .none()
        plans_qs = plans_qs.filter(responsables_ejecucion=request.user).distinct()
        # logger.debug(f"plan_gantt_view - Non-superuser '{request.user.username}', filtering by assigned tasks. Count: {plans_qs.count()}")


    # --- Lógica de filtro por responsable ---
    responsable_ids_in_current_view = set()
    # Iterar sobre el queryset *antes* de aplicar el filtro de responsable
    # para obtener todos los posibles responsables en la vista actual (año/empresa)
    temp_plans_for_responsable_scan = list(plans_qs) # Evaluar el queryset una vez para esto

    for plan_item in temp_plans_for_responsable_scan:
        for resp in plan_item.responsables_ejecucion.all():
            responsable_ids_in_current_view.add(resp.id)

    responsables_disponibles = CustomUser.objects.filter(id__in=list(responsable_ids_in_current_view)).order_by('username')
 
    selected_responsable_id = None
    if selected_responsable_id_str:
        if selected_responsable_id_str.isdigit():
            try:
                selected_responsable_id = int(selected_responsable_id_str)
                plans_qs = plans_qs.filter(responsables_ejecucion__id=selected_responsable_id)
            except ValueError:
                selected_responsable_id = None
        elif selected_responsable_id_str == "": # Opción "Todos los responsables"
            selected_responsable_id = ""

    # **Transformar Datos para Frappe Gantt:**
    initial_tasks_list = [] # Renombrar para claridad y evitar UnboundLocalError
    for plan in plans_qs: # Iterar sobre el queryset ya filtrado (incluyendo por responsable si aplica)
        start_date_obj = plan.fecha_proximo_cumplimiento
        if not start_date_obj:
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
        custom_class_gantt = ""
        ejecucion_asociada = getattr(plan, 'ejecucionmatriz', None)

        if ejecucion_asociada:
            progress = ejecucion_asociada.porcentaje_cumplimiento if ejecucion_asociada.porcentaje_cumplimiento is not None else 0
            if ejecucion_asociada.conforme == 'No':
                custom_class_gantt = "bar-non-conforming"
                if progress == 100 or ejecucion_asociada.ejecucion:
                    custom_class_gantt += " bar-completed-non-conforming"


        tema = escape(plan.requisito_empresa.requisito.tema) if plan.requisito_empresa and plan.requisito_empresa.requisito and plan.requisito_empresa.requisito.tema else "N/A"
        obligacion = escape(plan.requisito_empresa.requisito.Obligacion) if plan.requisito_empresa and plan.requisito_empresa.requisito and plan.requisito_empresa.requisito.Obligacion else "N/A"
        sede_nombre = escape(plan.sede.nombre) if plan.sede else "N/A"
        task_name = f"{tema} / {obligacion} - Sede: {sede_nombre}"


        initial_tasks_list.append({
            'id': str(plan.id),
            'name': task_name,
            'start': start_date_obj.isoformat(),
            'end': end_date_obj.isoformat(),
            'progress': progress,
            'dependencies': '',
            'custom_class': custom_class_gantt,
        })

    final_tasks_for_gantt = initial_tasks_list # Por defecto, usar la lista inicial

    # Filtrar por meses si se han seleccionado
    if selected_months_str:
        monthly_filtered_tasks = [] # Nueva variable para la lista filtrada por mes
        selected_months_int = [int(m) for m in selected_months_str if m.isdigit()]

        for task_data in initial_tasks_list: # Iterar sobre la lista inicial
            task_start_date = date.fromisoformat(task_data['start'])
            task_end_date = date.fromisoformat(task_data['end'])

            # Verificar si la tarea se solapa con alguno de los meses seleccionados
            task_included = False
            for month_int in selected_months_int:
                if not (1 <= month_int <= 12):
                    continue

                # Crear el rango de fechas para el mes seleccionado en el target_year
                month_start_date = date(target_year, month_int, 1)
                month_end_day = calendar.monthrange(target_year, month_int)[1]
                month_end_date = date(target_year, month_int, month_end_day)

                # Lógica de solapamiento de rangos: max(start1, start2) <= min(end1, end2)
                overlap_start = max(task_start_date, month_start_date)
                overlap_end = min(task_end_date, month_end_date)

                if overlap_start <= overlap_end:
                    task_included = True
                    break # La tarea se solapa con al menos un mes, no es necesario seguir verificando

            if task_included:
                monthly_filtered_tasks.append(task_data)
        final_tasks_for_gantt = monthly_filtered_tasks # Actualizar la lista final si se aplicó filtro de mes

    gantt_data_json = json.dumps(final_tasks_for_gantt, cls=DjangoJSONEncoder)
    current_year_for_template = date.today().year
    year_options = [current_year_for_template + i for i in range(-2, 5)]

    try:
        add_ejecucion_url_base = reverse('admin:myapp_ejecucionmatriz_add')
    except Exception as e:
        add_ejecucion_url_base = "#"

    month_choices = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre")
    ]

    selected_months_for_template = []
    if selected_months_str:
        try:
            selected_months_for_template = [int(m) for m in selected_months_str]
        except ValueError:
            logger.warning(f"Valor de mes inválido en selected_months_str: {selected_months_str}")

    context = {
        'title': f"Plan de Cumplimiento (Gantt) - Año {target_year}",
        'gantt_data_json': gantt_data_json,
        'selected_year': target_year,
        'year_options': year_options,
        'responsables_disponibles': responsables_disponibles,
        'selected_responsable_id': selected_responsable_id,
        'month_choices': month_choices,
        'selected_months': selected_months_for_template,
        'current_year': current_year_for_template,
        'add_ejecucion_url_base': add_ejecucion_url_base,
        'opts': Plan._meta,
        'site_header': admin.site.site_header,
        'site_title': admin.site.site_title,
        'is_popup': False,
        'is_nav_sidebar_enabled': True, # Asegúrate que la plantilla base del admin use esto
        'selected_company': selected_company, # <-- AÑADIR ESTA LÍNEA


    }
    return render(request, 'admin/myapp/plan/plan_gantt.html', context)
# --- FIN VISTA GANTT ---





@login_required
def dashboard_view(request):
    selected_company = getattr(request, 'selected_company', None)
    company_name = selected_company.nombreempresa if selected_company else "Todas las Empresas (Superusuario)"

    current_year = date.today().year
    target_year_str = request.GET.get('year', str(current_year))
    try:
        target_year = int(target_year_str)
    except (ValueError, TypeError):
        target_year = current_year
        logger.warning(f"Año inválido '{target_year_str}' en dashboard, usando año actual: {target_year}")

    year_options = [current_year + i for i in range(-2, 3)]

    kpis_generales = {
        'total_tareas': 0,
        'tareas_completadas': 0, # Este será el total de completadas (conformes + no conformes)
        'completadas_conformes': 0,
        'completadas_no_conformes': 0,
        'en_progreso': 0,
        'pendientes_sin_iniciar': 0,
        'tareas_pendientes': 0, # Suma de en_progreso y pendientes_sin_iniciar
        'tareas_vencidas': 0,
    }
    estado_tareas_data_json = json.dumps({'labels': [], 'data': []})
    responsables_data = []
    tareas_urgentes_list = []
    tareas_vencidas_list = [] 
    porcentaje_cumplimiento_general = 0

    if selected_company:
        plans_qs_base = Plan.objects.filter(empresa=selected_company, year=target_year) \
            .prefetch_related(
                'responsables_ejecucion',
                Prefetch('ejecucionmatriz', queryset=EjecucionMatriz.objects.all())
            ).distinct()
        logger.debug(f"Dashboard: {plans_qs_base.count()} planes encontrados para {company_name} en {target_year}.")
    elif request.user.is_superuser:
        plans_qs_base = Plan.objects.filter(year=target_year) \
            .prefetch_related(
                'responsables_ejecucion',
                Prefetch('ejecucionmatriz', queryset=EjecucionMatriz.objects.all())
            ).distinct()
        logger.debug(f"Dashboard: {plans_qs_base.count()} planes encontrados para TODAS LAS EMPRESAS (superuser) en {target_year}.")
    else:
        plans_qs_base = Plan.objects.none()
        messages.info(request, "Por favor, seleccione una empresa para ver el dashboard.")
        # logger.debug("Dashboard: No hay empresa seleccionada y no es superusuario.")

    # Si el usuario no es superusuario, filtrar adicionalmente por los planes asignados a él.
    if not request.user.is_superuser:
        plans_qs_base = plans_qs_base.filter(responsables_ejecucion=request.user).distinct()
        # logger.debug(f"Dashboard: Non-superuser '{request.user.username}', filtering by assigned tasks. Count: {plans_qs_base.count()}")


    if plans_qs_base.exists():
        hoy = date.today()
        
        temp_total_completadas = 0 
        temp_completadas_conformes = 0
        temp_completadas_no_conformes = 0
        temp_en_progreso = 0
        temp_pendientes_sin_iniciar = 0
        temp_tareas_vencidas_kpi = 0 
        
        responsables_stats_dict = {}

        for plan_item in plans_qs_base:
            ejecucion = getattr(plan_item, 'ejecucionmatriz', None)
            
            porcentaje_actual = 0
            es_conforme = True 
            es_marcada_ejecutada = False

            if ejecucion:
                porcentaje_actual = ejecucion.porcentaje_cumplimiento if ejecucion.porcentaje_cumplimiento is not None else 0
                es_marcada_ejecutada = ejecucion.ejecucion
                if ejecucion.conforme == 'No':
                    es_conforme = False
            
            # Determinar si la tarea está "finalizada" (100% o marcada como ejecutada)
            es_finalizada = es_marcada_ejecutada or (porcentaje_actual == 100)

            if es_finalizada:
                temp_total_completadas +=1
                if es_conforme:
                    temp_completadas_conformes += 1
                else:
                    temp_completadas_no_conformes += 1
            else: # No está finalizada
                if plan_item.fecha_proximo_cumplimiento:
                    if plan_item.fecha_proximo_cumplimiento < hoy: # Vencida
                        temp_tareas_vencidas_kpi += 1
                        dias_vencida = (hoy - plan_item.fecha_proximo_cumplimiento).days
                        tareas_vencidas_list.append({
                            'id': plan_item.id,
                            'nombre': f"{plan_item.requisito_empresa.requisito.tema if plan_item.requisito_empresa and plan_item.requisito_empresa.requisito else 'N/A'} (Sede: {plan_item.sede.nombre if plan_item.sede else 'N/A'})",
                            'fecha_vencimiento': plan_item.fecha_proximo_cumplimiento.isoformat(),
                            'dias_vencida': dias_vencida,
                            'responsables': ", ".join([r.username for r in plan_item.responsables_ejecucion.all()])
                        })
                    else: # No vencida y no finalizada
                        if porcentaje_actual > 0: 
                            temp_en_progreso += 1
                        else: 
                            temp_pendientes_sin_iniciar +=1
                        
                        dias_para_vencer = (plan_item.fecha_proximo_cumplimiento - hoy).days
                        if 0 <= dias_para_vencer <= 7:
                            tareas_urgentes_list.append({
                                'id': plan_item.id,
                                'nombre': f"{plan_item.requisito_empresa.requisito.tema if plan_item.requisito_empresa and plan_item.requisito_empresa.requisito else 'N/A'} (Sede: {plan_item.sede.nombre if plan_item.sede else 'N/A'})",
                                'fecha_vencimiento': plan_item.fecha_proximo_cumplimiento.isoformat(),
                                'dias_faltantes': dias_para_vencer,
                                'responsables': ", ".join([r.username for r in plan_item.responsables_ejecucion.all()])
                            })
                else: # Sin fecha de cumplimiento, no finalizada
                    if porcentaje_actual > 0:
                        temp_en_progreso += 1
                    else:
                        temp_pendientes_sin_iniciar +=1
            
            # Estadísticas por responsable (basado en si la tarea está finalizada)
            for resp in plan_item.responsables_ejecucion.all():
                if resp.id not in responsables_stats_dict:
                    responsables_stats_dict[resp.id] = {'username': resp.username, 'total_asignadas': 0, 'completadas': 0}
                responsables_stats_dict[resp.id]['total_asignadas'] += 1
                if es_finalizada: # Se cuenta como "completada" para el responsable si está finalizada
                    responsables_stats_dict[resp.id]['completadas'] += 1
        
        kpis_generales['total_tareas'] = plans_qs_base.count()
        kpis_generales['tareas_completadas'] = temp_total_completadas
        kpis_generales['completadas_conformes'] = temp_completadas_conformes
        kpis_generales['completadas_no_conformes'] = temp_completadas_no_conformes
        kpis_generales['en_progreso'] = temp_en_progreso
        kpis_generales['pendientes_sin_iniciar'] = temp_pendientes_sin_iniciar
        kpis_generales['tareas_pendientes'] = temp_en_progreso + temp_pendientes_sin_iniciar
        kpis_generales['tareas_vencidas'] = temp_tareas_vencidas_kpi

        if kpis_generales['total_tareas'] > 0:
            porcentaje_cumplimiento_general = round((temp_total_completadas / kpis_generales['total_tareas']) * 100, 1)
        else:
            porcentaje_cumplimiento_general = 0

        estado_tareas_data = {
            'labels': ['Completadas (Conformes)', 'Completadas (No Conformes)', 'En Progreso', 'Pendientes (Sin Iniciar)', 'Vencidas'],
            'data': [
                kpis_generales['completadas_conformes'],
                kpis_generales['completadas_no_conformes'],
                kpis_generales['en_progreso'],
                kpis_generales['pendientes_sin_iniciar'],
                kpis_generales['tareas_vencidas']
            ],
        }
        estado_tareas_data_json = json.dumps(estado_tareas_data, cls=DjangoJSONEncoder)

        for resp_id, stats in responsables_stats_dict.items():
            porcentaje = (stats['completadas'] / stats['total_asignadas']) * 100 if stats['total_asignadas'] > 0 else 0
            responsables_data.append({
                'username': stats['username'],
                'total_asignadas': stats['total_asignadas'],
                'completadas': stats['completadas'],
                'porcentaje_completado': round(porcentaje, 1)
            })
        responsables_data.sort(key=lambda x: x['porcentaje_completado'], reverse=True)

        tareas_urgentes_list.sort(key=lambda x: x['dias_faltantes'])
        tareas_vencidas_list.sort(key=lambda x: x['dias_vencida'], reverse=True)


    context = {
        'title': f"Dashboard de Cumplimiento - {company_name} ({target_year})",
        'selected_year': target_year,
        'year_options': year_options,
        'kpis_generales': kpis_generales,
        'estado_tareas_data_json': estado_tareas_data_json,
        'responsables_data': responsables_data,
        'tareas_urgentes': tareas_urgentes_list[:7],
        'tareas_vencidas_list': tareas_vencidas_list[:7],
        'company_name': company_name,
        'has_company_selected': selected_company is not None,
        'porcentaje_cumplimiento_general': porcentaje_cumplimiento_general,
    }
    return render(request, 'myapp/dashboard.html', context)


@login_required
def ejecucion_matriz_direct_form_view(request):
    logger.debug(f"ejecucion_matriz_direct_form_view: User: {request.user}, is_superuser: {request.user.is_superuser}")
    logger.debug(f"ejecucion_matriz_direct_form_view: Session selected_company_id: {request.session.get('selected_company_id')}")

    selected_company = getattr(request, 'selected_company', None)
    logger.debug(f"ejecucion_matriz_direct_form_view: Middleware selected_company: {selected_company}")

    if not selected_company and not request.user.is_superuser:
        messages.error(request, "Por favor, seleccione una empresa para gestionar la ejecución.")
        logger.warning(f"ejecucion_matriz_direct_form_view: Redirecting user {request.user} to select_company because selected_company is None.")
        return redirect('users_app:select_company')
    
    plan_id = request.GET.get('plan')
    logger.debug(f"ejecucion_matriz_direct_form_view: Received plan_id: {plan_id}")
    plan_instance = None
    
    if plan_id:
        try:
            plan_instance = get_object_or_404(Plan, id=int(plan_id))
            if not request.user.is_superuser and selected_company and plan_instance.empresa != selected_company:
                logger.warning(f"User {request.user} tried to access plan {plan_id} from another company.")
                messages.error(request, "No tiene permiso para acceder a la ejecución de este plan.")
                return redirect('myapp:plan_gantt_chart')
            
            # Intentar obtener la EjecucionMatriz existente
            try:
                ejecucion_instance = EjecucionMatriz.objects.get(plan=plan_instance)
                # Si existe, redirigir a la página de cambio del admin
                admin_change_url = reverse('admin:myapp_ejecucionmatriz_change', args=[ejecucion_instance.id])
                logger.debug(f"EjecucionMatriz encontrada (ID: {ejecucion_instance.id}), redirigiendo a: {admin_change_url}")
                return redirect(admin_change_url)
            except EjecucionMatriz.DoesNotExist:
                # Si no existe, redirigir a la página de añadir del admin, pre-rellenando el plan
                admin_add_url = reverse('admin:myapp_ejecucionmatriz_add') + f'?plan={plan_instance.id}'
                logger.debug(f"EjecucionMatriz no encontrada para Plan ID {plan_instance.id}, redirigiendo a: {admin_add_url}")
                return redirect(admin_add_url)
                
        except ValueError:
            logger.error(f"Invalid plan_id '{plan_id}' received.")
            messages.error(request, "El ID del plan proporcionado no es válido.")
            return redirect('myapp:plan_gantt_chart')
        except Http404:
            logger.error(f"Plan with ID {plan_id} not found.")
            messages.error(request, "El plan especificado no existe.")
            return redirect('myapp:plan_gantt_chart')
    else:
        # Si no se proporciona plan_id, redirigir al Gantt o a una página de error
        messages.error(request, "No se especificó un plan para la ejecución.")
        return redirect('myapp:plan_gantt_chart')



@login_required
def mis_tareas_view(request):
    user = request.user
    hoy = date.today() # Cambiado para consistencia con el dashboard

    # Obtener filtros de fecha del request
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')
    estado_filtro = request.GET.get('estado_filtro', 'all')
    sort_by = request.GET.get('sort_by', 'urgencia') # Nuevo: Parámetro de ordenamiento


    # Query base: planes asignados al usuario
    planes_usuario_qs = Plan.objects.filter(responsables_ejecucion=user).select_related(
        'requisito_empresa__requisito',
        'sede',
        'empresa'
    ).prefetch_related(
        'ejecucionmatriz',
        'responsables_ejecucion' # Para mostrar todos los responsables si es necesario
    ).distinct()

    # Aplicar ordenamiento
    if sort_by == 'empresa':
        planes_usuario_qs = planes_usuario_qs.order_by('empresa__nombreempresa', 'fecha_proximo_cumplimiento')
    elif sort_by == 'fecha_vencimiento_desc': # Más lejanas primero
        planes_usuario_qs = planes_usuario_qs.order_by('-fecha_proximo_cumplimiento')
    else: # Por defecto 'urgencia' (fecha_proximo_cumplimiento ascendente, próximas primero)
        planes_usuario_qs = planes_usuario_qs.order_by('fecha_proximo_cumplimiento')

    # Aplicar filtro de rango de fechas si se proporcionan
    if fecha_inicio_str:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio_str)
            planes_usuario_qs = planes_usuario_qs.filter(fecha_proximo_cumplimiento__gte=fecha_inicio)
        except ValueError:
            messages.error(request, "Formato de fecha de inicio inválido.")
    if fecha_fin_str:
        try:
            fecha_fin = date.fromisoformat(fecha_fin_str)
            planes_usuario_qs = planes_usuario_qs.filter(fecha_proximo_cumplimiento__lte=fecha_fin)
        except ValueError:
            messages.error(request, "Formato de fecha de fin inválido.")

    tareas_list = []
    for plan in planes_usuario_qs:
        estado_info = {
            'texto': 'Pendiente',
            'clase_css': 'blue', # Color por defecto para etiquetas
            'icono': 'hourglass half',
            'progreso': 0,
            'categoria_estado': 'pendiente_sin_iniciar' # Nueva categoría para filtrar
        }
        
        ejecucion = getattr(plan, 'ejecucionmatriz', None)
        porcentaje_actual = 0
        es_conforme = True
        es_marcada_ejecutada = False

        if ejecucion:
            porcentaje_actual = ejecucion.porcentaje_cumplimiento if ejecucion.porcentaje_cumplimiento is not None else 0
            es_marcada_ejecutada = ejecucion.ejecucion
            if ejecucion.conforme == 'No':
                es_conforme = False
        
        estado_info['progreso'] = porcentaje_actual
        es_finalizada = es_marcada_ejecutada or (porcentaje_actual == 100)

        if es_finalizada:
            if es_conforme:
                estado_info['texto'] = 'Completada'
                estado_info['categoria_estado'] = 'completada_conforme'
                estado_info['clase_css'] = 'green'
                estado_info['icono'] = 'check circle'
            else:
                estado_info['texto'] = 'Completada (No Conforme)'
                estado_info['categoria_estado'] = 'completada_no_conforme'
                estado_info['clase_css'] = 'orange' # O un color distintivo para no conforme
                estado_info['icono'] = 'warning circle'
        elif plan.fecha_proximo_cumplimiento:
            dias_para_vencer = (plan.fecha_proximo_cumplimiento - hoy).days
            if dias_para_vencer < 0:
                estado_info['texto'] = f'Vencida (hace {-dias_para_vencer} día(s))'
                estado_info['categoria_estado'] = 'vencida'
                estado_info['clase_css'] = 'red'
                estado_info['icono'] = 'calendar times outline'
            else: # No vencida y no finalizada
                if porcentaje_actual > 0: # En progreso
                    estado_info['texto'] = f'En Progreso ({porcentaje_actual}%)'
                    estado_info['categoria_estado'] = 'en_progreso'
                    estado_info['clase_css'] = 'blue'
                    estado_info['icono'] = 'tasks'
                else: # Pendiente sin iniciar, y no vencida
                    if 0 <= dias_para_vencer <= 7:
                        estado_info['texto'] = f'Vence en {dias_para_vencer} día(s)'
                        estado_info['categoria_estado'] = 'vence_pronto'
                        estado_info['clase_css'] = 'yellow' 
                        estado_info['icono'] = 'warning sign'
                    elif 7 < dias_para_vencer <= 30:
                        estado_info['texto'] = 'Vence este mes'
                        estado_info['categoria_estado'] = 'vence_mes'
                        estado_info['clase_css'] = 'teal' 
                        estado_info['icono'] = 'calendar alternate outline'
                    else: # Vence en más de un mes
                        estado_info['texto'] = 'Programada'
                        estado_info['categoria_estado'] = 'programada'
                        estado_info['clase_css'] = 'grey' 
                        estado_info['icono'] = 'calendar outline'
        else: # Sin fecha de cumplimiento y no finalizada
            if porcentaje_actual > 0:
                estado_info['texto'] = f'En Progreso ({porcentaje_actual}%)'
                estado_info['categoria_estado'] = 'en_progreso'
                estado_info['clase_css'] = 'blue'
                estado_info['icono'] = 'tasks'
            # Si no tiene fecha y es 0%, se queda como 'pendiente_sin_iniciar'    
        tema_req = plan.requisito_empresa.requisito.tema if plan.requisito_empresa and plan.requisito_empresa.requisito else 'N/A'
        obligacion_req = plan.requisito_empresa.requisito.Obligacion if plan.requisito_empresa and plan.requisito_empresa.requisito else 'N/A'
   


        tareas_list.append({
            'id': plan.id,
            'nombre_corto': f"{tema_req} (Sede: {plan.sede.nombre if plan.sede else 'N/A'})", # Mantenemos un nombre corto para el header
            'fecha_vencimiento': plan.fecha_proximo_cumplimiento,
            'responsables': ", ".join([r.username for r in plan.responsables_ejecucion.all()]),
            'empresa': plan.empresa.nombreempresa if plan.empresa else 'N/A',
            'tema_requisito': tema_req,
            'obligacion_requisito': obligacion_req,
            'estado_info': estado_info,
            'year': plan.year, # Para el enlace de volver al Gantt
        })
        
            # Aplicar filtro de estado si se seleccionó uno diferente a 'all'
    if estado_filtro != 'all':
        tareas_list = [t for t in tareas_list if t['estado_info']['categoria_estado'] == estado_filtro]

    # Opciones para el dropdown de filtro de estado
    opciones_estado_filtro = [
        {'value': 'all', 'text': 'Todos los Estados'},
        {'value': 'pendiente_sin_iniciar', 'text': 'Pendientes (Sin Iniciar)'},
        {'value': 'en_progreso', 'text': 'En Progreso'},
        {'value': 'vence_pronto', 'text': 'Vence Próximos 7 Días'},
        {'value': 'vence_mes', 'text': 'Vence Este Mes'},
        {'value': 'programada', 'text': 'Programadas (Más de 1 mes)'},
        {'value': 'vencida', 'text': 'Vencidas'},
        {'value': 'completada_conforme', 'text': 'Completadas (Conformes)'},
        {'value': 'completada_no_conforme', 'text': 'Completadas (No Conformes)'},
    ]

    # Opciones para el dropdown de ordenamiento
    opciones_ordenamiento = [
        {'value': 'urgencia', 'text': 'Urgencia (Próximas primero)'},
        {'value': 'empresa', 'text': 'Empresa (A-Z)'},
        {'value': 'fecha_vencimiento_desc', 'text': 'Fecha Vencimiento (Lejanas primero)'},
    ]


    context = {
        'title': f"Mis Tareas - {user.username}",
        'tareas_list': tareas_list,
        'fecha_inicio_filtro': fecha_inicio_str, # Para mantener el valor en el formulario
        'fecha_fin_filtro': fecha_fin_str,       # Para mantener el valor en el formulario
        'opciones_estado_filtro': opciones_estado_filtro,
        'estado_filtro_seleccionado': estado_filtro,
        'opciones_ordenamiento': opciones_ordenamiento, # Nuevo
        'sort_by_seleccionado': sort_by,             # Nuevo

    }
    return render(request, 'myapp/mis_tareas.html', context)


# myapp/views.py


# Un decorador para asegurar que solo el personal pueda ver esta página
def is_staff_member(user):
    return user.is_staff

@login_required
@user_passes_test(is_staff_member)
def recent_actions_custom_view(request):
    # Obtener las últimas N acciones, puedes ajustar el número
    actions = LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')[:15]
    context = {
        'title': 'Últimas Acciones del Sistema',
        'recent_actions_list': actions,
    }
    return render(request, 'admin/myapp/custom_recent_actions.html', context)
