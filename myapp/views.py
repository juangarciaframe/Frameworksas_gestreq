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

# Nuevas importaciones para ejecucion_matriz_direct_form_view
from django.shortcuts import get_object_or_404
from django.http import Http404
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
@admin.site.admin_view # O @login_required si prefieres que no sea solo para admin
def plan_gantt_view(request):
    target_year_str = request.GET.get('year', str(date.today().year))
    logger.critical(f"plan_gantt_view: LA VISTA HA SIDO LLAMADA. Año str: {target_year_str}") # Log de alta prioridad
    selected_responsable_id_str = request.GET.get('responsable_id')
    selected_months_str = request.GET.getlist('months') # Obtener lista de meses seleccionados
    selected_company = getattr(request, 'selected_company', None)

    logger.debug(f"plan_gantt_view - Request GET: {request.GET}")
    logger.debug(f"plan_gantt_view - Selected Company: {selected_company.nombreempresa if selected_company else 'None'}")

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
            selected_responsable_id = ""

    # **Transformar Datos para Frappe Gantt:**
    initial_tasks_list = [] # Renombrar para claridad y evitar UnboundLocalError
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
        logger.debug(f"Filtrando por meses seleccionados: {selected_months_str}")
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

    logger.info(f"plan_gantt_view - Número de tareas generadas para Gantt: {len(final_tasks_for_gantt)}")
    gantt_data_json = json.dumps(final_tasks_for_gantt, cls=DjangoJSONEncoder)
    current_year_for_template = date.today().year
    year_options = [current_year_for_template + i for i in range(-2, 5)]

    try:
        add_ejecucion_url_base = reverse('admin:myapp_ejecucionmatriz_add')
    except Exception as e:
        logger.error(f"No se pudo generar la URL para admin:myapp_ejecucionmatriz_add: {e}")
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
        'is_nav_sidebar_enabled': True,
    }
    return render(request, 'admin/myapp/plan/plan_gantt.html', context)
# --- FIN VISTA GANTT ---





@login_required
def dashboard_view(request):
    logger.debug("Dashboard view called.")
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
        logger.debug("Dashboard: No hay empresa seleccionada y no es superusuario.")


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
    logger.debug("EjecucionMatriz direct form view called.")
    selected_company = getattr(request, 'selected_company', None)

    if not selected_company and not request.user.is_superuser:
        messages.error(request, "Por favor, seleccione una empresa para gestionar la ejecución.")
        return redirect('users_app:select_company')
    
    plan_id = request.GET.get('plan')
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
