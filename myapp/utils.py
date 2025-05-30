# myapp/utils.py

# Asegúrate que estos imports estén al principio
from .models import RequisitoPorEmpresaDetalle, Plan, Empresa, Pais # Añadir Pais si no está
from django.forms import ValidationError
from datetime import date, timedelta
import holidays # Importar la librería
import logging # Usar logging para mejor manejo de errores
from dateutil.relativedelta import relativedelta # Importar relativedelta
from calendar import monthrange # Para calcular días en mes si es necesario


logger = logging.getLogger(__name__) # Configurar logger

# --- FUNCION MODIFICADA PARA CALCULAR DIAS HABILES POR PAIS ---
def add_working_days(start_date, num_working_days, country_code):
    """
    Calcula una fecha futura añadiendo un número específico de días hábiles
    a una fecha de inicio, excluyendo fines de semana y festivos del país especificado.

    Args:
        start_date (date): La fecha de inicio.
        num_working_days (int): El número de días hábiles a añadir (debe ser >= 0).
        country_code (str): El código ISO 3166-1 alpha-2 del país (ej: 'CO', 'MX', 'US').

    Returns:
        date: La fecha resultante después de añadir los días hábiles,
              o None si la entrada es inválida o no se pueden obtener los festivos.
    """
    if not isinstance(start_date, date) or not isinstance(num_working_days, int) or num_working_days < 0:
        logger.warning(f"Entrada inválida para add_working_days: start_date={start_date}, num_working_days={num_working_days}")
        return None
    if not isinstance(country_code, str) or not country_code:
        logger.warning(f"Código de país inválido para add_working_days: {country_code}")
        # Podrías decidir calcular solo con fines de semana si no hay país,
        # pero es mejor retornar None para indicar que el cálculo completo no fue posible.
        return None

    if num_working_days == 0:
        return start_date

    country_holidays = {} # Inicializar vacío
    try:
        # Obtener los festivos dinámicamente usando el código del país
        # Se obtienen para el año de inicio y el siguiente para cubrir cruces de año
        years_to_check = [start_date.year, start_date.year + 1]
        # Usar holidays.CountryHoliday para obtener los festivos del país
        country_holidays = holidays.CountryHoliday(country_code, years=years_to_check)
        logger.debug(f"Festivos obtenidos para {country_code} años {years_to_check}")

    except KeyError:
        logger.warning(f"La librería 'holidays' no tiene soporte para el código de país: '{country_code}'. Calculando solo con fines de semana.")
        # Continuamos sin festivos si el país no está soportado
    except Exception as e:
        logger.error(f"Error inesperado al obtener festivos para {country_code}: {e}")
        # Podrías decidir retornar None o continuar sin festivos
        # Optamos por continuar sin festivos para no detener el proceso, pero loggeamos el error.

    current_date = start_date
    days_added = 0

    # Bucle para añadir días hábiles
    # Se limita a un número máximo de iteraciones para evitar bucles infinitos (ej. 3 años)
    max_iterations = num_working_days + 365 * 3
    iterations = 0

    while days_added < num_working_days and iterations < max_iterations:
        current_date += timedelta(days=1)
        iterations += 1

        # Verificar si es fin de semana (sab=5, dom=6)
        is_weekend = current_date.weekday() >= 5
        # Verificar si es festivo (solo si se obtuvieron festivos)
        is_holiday = current_date in country_holidays if country_holidays else False

        if not is_weekend and not is_holiday:
            days_added += 1

    if iterations >= max_iterations:
         logger.error(f"Se alcanzó el límite de iteraciones ({max_iterations}) calculando días hábiles para {start_date} + {num_working_days} días en {country_code}. Retornando fecha parcial.")
         # Retornar la fecha alcanzada puede ser mejor que None en este caso extremo

    return current_date
# --- FIN FUNCION MODIFICADA ---


def calculate_compliance_dates_for_year(start_date, periodicidad, target_year):
    """
    Calcula una lista de fechas de cumplimiento programadas dentro de un año específico,
    basado en una fecha de inicio y una periodicidad.

    Args:
        start_date (date): La fecha base de inicio del requisito.
        periodicidad (str): La frecuencia ('Mensual', 'Semestral', etc.).
        target_year (int): El año para el cual generar las fechas.

    Returns:
        list[date]: Una lista de objetos date representando las fechas de cumplimiento.
    """
    compliance_dates = []
    if not isinstance(start_date, date):
        try:
            start_date = date.fromisoformat(str(start_date))
        except (TypeError, ValueError):
            logger.error(f"Fecha de inicio inválida para calcular fechas del plan: {start_date}")
            return [] # Retorna lista vacía si la fecha es inválida

    # Definir el inicio y fin del año objetivo
    year_start = date(target_year, 1, 1)
    year_end = date(target_year, 12, 31)

    # Caso especial: Periodicidad Única
    if periodicidad == 'Unica':
        # Solo se incluye si la fecha de inicio cae dentro del año objetivo
        if year_start <= start_date <= year_end:
            compliance_dates.append(start_date)
        return compliance_dates

    # Calcular el delta según la periodicidad
    delta = None
    if periodicidad == 'Diaria': delta = relativedelta(days=1)
    elif periodicidad == 'Semanal': delta = relativedelta(weeks=1)
    elif periodicidad == 'Quincenal': delta = relativedelta(weeks=2)
    elif periodicidad == 'Mensual': delta = relativedelta(months=1)
    elif periodicidad == 'Bimestral': delta = relativedelta(months=2)
    elif periodicidad == 'Trimestral': delta = relativedelta(months=3)
    elif periodicidad == 'Semestral': delta = relativedelta(months=6)
    elif periodicidad == 'Anual': delta = relativedelta(years=1)
    elif periodicidad == 'Otro':
        logger.warning(f"Periodicidad 'Otro' no es calculable para fechas automáticas.")
        return [] # No se pueden generar fechas para 'Otro'
    else:
        logger.error(f"Periodicidad desconocida: {periodicidad}")
        return [] # Periodicidad no reconocida

    # Encontrar la primera fecha de cumplimiento DENTRO o DESPUÉS del año objetivo
    current_date = start_date
    while current_date < year_start:
        try:
            current_date += delta
        except Exception as e: # Captura errores si el delta es inválido
             logger.error(f"Error aplicando delta {delta} a {current_date}: {e}")
             return [] # Salir si hay error en el cálculo

    # Generar fechas dentro del año objetivo
    while current_date <= year_end:
        compliance_dates.append(current_date)
        try:
            current_date += delta
        except Exception as e:
             logger.error(f"Error aplicando delta {delta} a {current_date}: {e}")
             break # Salir del bucle si hay error

    logger.debug(f"Fechas calculadas para {start_date}, {periodicidad}, {target_year}: {compliance_dates}")
    return compliance_dates




# --- FUNCIÓN duplicate_requisitos_to_plan MODIFICADA ---
def duplicate_requisitos_to_plan(target_year, company_id=None, default_responsable_id=None):
    """
    Crea registros Plan para un año específico basados en RequisitoPorEmpresaDetalle,
    generando múltiples entradas según la periodicidad.

    Args:
        target_year (int): El año para el cual crear los registros Plan.
        company_id (str, optional): El ID de una empresa específica. Si es None, procesa todas.
        default_responsable_id (int, optional): El ID del usuario a asignar como responsable por defecto.
    """
    if not isinstance(target_year, int) or target_year < 1900 or target_year > 2100:
        raise ValueError("target_year debe ser un año válido entre 1900 y 2100.")
    
    # Importar aquí para evitar dependencia circular a nivel de módulo
    from users_app.models import CustomUser

    default_responsable_user = None
    if default_responsable_id:
        try:
            default_responsable_user = CustomUser.objects.get(pk=default_responsable_id)
        except CustomUser.DoesNotExist:
            logger.warning(f"No se encontró el usuario responsable con ID {default_responsable_id}. Los planes se crearán sin responsable.")
        except Exception as e:
            logger.error(f"Error al obtener usuario responsable ID {default_responsable_id}: {e}")


    # Obtener los detalles de requisitos a procesar
    if company_id:
        try:
            company = Empresa.objects.get(codigoempresa=company_id) # type: ignore
            requisitos_detalle_qs = RequisitoPorEmpresaDetalle.objects.select_related(
                'matriz__empresa', 'requisito__pais' # Incluir relaciones necesarias
            ).filter(matriz__empresa=company)
        except Empresa.DoesNotExist:
            raise ValidationError(f"No se encuentra la empresa {company_id}.")
    else:
        requisitos_detalle_qs = RequisitoPorEmpresaDetalle.objects.select_related(
            'matriz__empresa', 'requisito__pais', 'sede' # Asegúrate de incluir 'sede'
        ).all()

    # Listas para bulk_create y contadores
    plans_to_create = []
    created_count = 0
    skipped_count = 0
    processed_details = 0

    # Iterar sobre los detalles de requisitos
    for requisito_detalle in requisitos_detalle_qs:
        processed_details += 1
        logger.debug(f"Procesando ReqDetalle ID: {requisito_detalle.id}, Periodicidad: {requisito_detalle.periodicidad}")

        # Calcular las fechas de cumplimiento para el año objetivo
        compliance_dates = calculate_compliance_dates_for_year(
            requisito_detalle.fecha_inicio,
            requisito_detalle.periodicidad,
            target_year
        )

        if not compliance_dates:
            logger.warning(f"No se generaron fechas para ReqDetalle ID {requisito_detalle.id}. Omitiendo.")
            continue # Pasar al siguiente requisito_detalle

        # Crear un registro Plan para cada fecha calculada
        for compliance_date in compliance_dates:
            # Verificar si ya existe un plan EXACTO (mismo detalle, año y fecha)
            # Usamos get_or_create para manejar concurrencia y simplificar
            plan_obj, created = Plan.objects.get_or_create(
                requisito_empresa=requisito_detalle,
                year=target_year,
                fecha_proximo_cumplimiento=compliance_date,
                sede=requisito_detalle.sede, # <-- Copiar la sede aquí
                defaults={ # Valores a usar si se CREA un nuevo objeto
                    'empresa': requisito_detalle.matriz.empresa,
                    'periodicidad': requisito_detalle.periodicidad,
                    'fecha_inicio': requisito_detalle.fecha_inicio,
                    'descripcion_periodicidad': requisito_detalle.descripcion_cumplimiento if requisito_detalle.periodicidad == 'Otro' else None, # Copiar descripción si es 'Otro'
                    # 'sede' ya está en los campos clave de get_or_create
                }
            )

            if created:
                logger.debug(f"Plan CREADO para ReqDetalle ID {requisito_detalle.id}, Fecha: {compliance_date}")
                created_count += 1
                # Asignar responsables después de crear el plan
                responsables_a_asignar = []
                if default_responsable_user:
                    responsables_a_asignar.append(default_responsable_user)
                else:
                    # Intentar asignar el primer usuario de la empresa del plan
                    # Asumiendo que CustomUser tiene una relación M2M 'Empresa'
                    try:
                        empresa_del_plan = requisito_detalle.matriz.empresa
                        primer_usuario_empresa = CustomUser.objects.filter(Empresa=empresa_del_plan).first()
                        if primer_usuario_empresa:
                            responsables_a_asignar.append(primer_usuario_empresa)
                            logger.info(f"Asignando a {primer_usuario_empresa.username} al nuevo Plan ID {plan_obj.id} para la empresa {empresa_del_plan.nombreempresa}")
                        else:
                            logger.warning(f"No se encontraron usuarios para la empresa {empresa_del_plan.nombreempresa} para asignar al Plan ID {plan_obj.id}")
                    except Exception as e:
                        logger.error(f"Error al intentar asignar usuario por defecto de la empresa al Plan ID {plan_obj.id}: {e}")
                
                if responsables_a_asignar:
                    plan_obj.responsables_ejecucion.set(responsables_a_asignar)

            else:
                logger.info(f"Plan ya existe para ReqDetalle ID {requisito_detalle.id}, Fecha: {compliance_date}. Omitiendo.")
                skipped_count += 1

    logger.info(f"Duplicación a Plan año {target_year} completada. Detalles procesados: {processed_details}. Planes Creados: {created_count}, Omitidos: {skipped_count}")
# --- FIN FUNCIÓN MODIFICADA ---