from datetime import date
import json
from django.contrib import admin
from django.forms import ValidationError
from import_export import resources
from myapp.models import Empresa, RequisitoLegal, EjecucionMatriz, RequisitosPorEmpresa, Plan, Pais, Industria, RequisitoPorEmpresaDetalle , Sede
from users_app.models import CustomUser, UserCompany # Add UserCompany here
from .utils import duplicate_requisitos_to_plan
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.urls import path, reverse, reverse_lazy
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.html import format_html
from django.db.models import Q
from django.contrib.auth.hashers import make_password
from django.contrib.admin import SimpleListFilter
from django_select2.forms import ModelSelect2Widget, Select2Widget
# Import the correct model and classes for semantic_admin
from semantic_admin import SemanticModelAdmin, SemanticStackedInline, SemanticTabularInline
from semantic_admin.contrib.import_export.admin import SemanticImportExportModelAdmin
from import_export.admin import ImportExportModelAdmin

from .forms import CustomAdminLoginForm # Add this line
from django.core.exceptions import PermissionDenied 
from .forms import RequisitoPorEmpresaDetalleForm

from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import render # Necesario para la vista
from django.http import HttpResponseRedirect # Necesario para la vista
from django.contrib import messages # Necesario para la vista
from django.db import transaction # Necesario para la vista POST
from .forms import CreateMatrixWithRequirementsForm # Crearemos este formulario
from .models import RequisitoLegal, RequisitoPorEmpresaDetalle # Necesario para la vista POST
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
import json
from django.utils.html import escape # Para seguridad


def app_resort(func):
    def inner(*args, **kwargs):
        app_list = func(*args, **kwargs)
        app_sort_key = 'name'
        app_ordering = {
            "Gestion de Requisitos": 1,
            "Usuarios por Empresa": 2,
        }

        resorted_app_list = sorted(app_list, key=lambda x: app_ordering[x[app_sort_key]] if x[app_sort_key] in app_ordering else 1000)

        model_sort_key = 'object_name'
        model_ordering = {
            "Pais": 1,
            "Industria": 2,
            "Empresa": 3,
            "Sede": 4, # <-- Añade esta línea
            "RequisitoLegal": 5, # Ajusta los números siguientes si es necesario
            "RequisitosPorEmpresa": 6,
            "RequisitoPorEmpresaDetalle": 7,
            "Plan": 8,
            "EjecucionMatriz": 9,

        }
        for app in resorted_app_list:
            app['models'].sort(key=lambda x: model_ordering[x[model_sort_key]] if x[model_sort_key] in model_ordering else 1000)
        return resorted_app_list
    return inner

@admin.site.admin_view # O @staff_member_required si prefieres
def create_with_requirements_view(request):
    """
    Vista independiente para crear una Matriz con Requisitos seleccionados.
    """
    # El usuario se obtiene de request.user
    form = CreateMatrixWithRequirementsForm(request.POST or None, user=request.user)
    all_requisitos = RequisitoLegal.objects.select_related('pais').all()

    if request.method == 'POST':
        if form.is_valid():
            selected_req_ids = request.POST.getlist('requisitos')
            if not selected_req_ids:
                messages.error(request, "Debe seleccionar al menos un requisito.")
            else:
                try:
                    # Crear la matriz principal
                    nueva_matriz = form.save()

                    # Crear los detalles
                    detalles_a_crear = []
                    requisitos_seleccionados = RequisitoLegal.objects.filter(pk__in=selected_req_ids)
                    for req in requisitos_seleccionados:
                        # Asumiendo que necesitas la sede aquí también (usando la seleccionada globalmente)
                        sede_seleccionada = getattr(request, 'selected_company', None) # Obtener empresa global
                        sede_para_detalle = None
                        if sede_seleccionada:
                             # Obtener la primera sede de esa empresa (o ajustar lógica si necesitas elegirla)
                             sede_para_detalle = Sede.objects.filter(empresa=sede_seleccionada).first()

                        if not sede_para_detalle:
                             messages.warning(request, f"No se encontró una sede para la empresa seleccionada al añadir requisito {req.pk}. Se omitirá la sede.")
                             # Decide si quieres continuar sin sede o mostrar un error más fuerte

                        detalles_a_crear.append(
                            RequisitoPorEmpresaDetalle(
                                matriz=nueva_matriz,
                                requisito=req,
                                sede=sede_para_detalle, # Asignar la sede encontrada
                                # Copiar valores por defecto
                                periodicidad=req.periodicidad,
                                tiempo_validacion=req.tiempo_validacion,
                                # Puedes añadir fecha_inicio si es necesario
                            )
                        )

                    if detalles_a_crear:
                        RequisitoPorEmpresaDetalle.objects.bulk_create(detalles_a_crear)
                        messages.success(request, f"Matriz '{nueva_matriz.nombre}' creada exitosamente con {len(detalles_a_crear)} requisitos.")
                        # Redirigir a la lista de matrices
                        return redirect('admin:myapp_requisitosporempresa_changelist')
                    else:
                         messages.warning(request, "No se pudieron crear detalles de requisitos (posiblemente por falta de sede).")


                except Exception as e:
                    messages.error(request, f"Error al crear la matriz o sus detalles: {e}")
                    # Considera loggear el error completo: logger.exception("Error en create_with_requirements_view POST")

        else: # Formulario no válido
            messages.error(request, "Por favor corrija los errores en el formulario.")

    # Contexto para GET o POST con error
    context = {
        'form': form,
        'all_requisitos': all_requisitos,
        'title': "Creacion masiva de Requisitos por Empresa",
        'opts': RequisitosPorEmpresa._meta, # Necesario para breadcrumbs y título
        'has_view_permission': True, # Asumiendo que si llega aquí, tiene permiso
        # Añade cualquier otro contexto que necesite la plantilla base del admin
        'site_header': admin.site.site_header,
        'site_title': admin.site.site_title,
        'is_popup': False,
        'is_nav_sidebar_enabled': True, # O False según tu config
    }
    # Asegúrate que la ruta de la plantilla sea correcta
    return render(request, 'admin/myapp/requisitosporempresa/create_with_reqs.html', context)
# --- FIN DE LA VISTA MOVIDA ---


@admin.site.admin_view # O @login_required
def plan_gantt_view(request):
    target_year = request.GET.get('year', date.today().year) # Obtener año del GET o usar actual
    selected_company = getattr(request, 'selected_company', None)
    #plans_qs = Plan.objects.select_related('requisito_empresa__requisito') # Incluir datos relacionados
    # --- MODIFICADO: Añadir select_related para sede ---
    plans_qs = Plan.objects.select_related(
        'requisito_empresa__requisito',
        'sede' # Asegúrate de incluir sede
    )

    try:
        target_year = int(target_year)
    except (ValueError, TypeError):
        target_year = date.today().year # Fallback

    if selected_company:
        plans_qs = plans_qs.filter(empresa=selected_company, year=target_year)
    else:
        # Decide qué hacer si no hay empresa: mostrar todo (si es superuser) o nada
        if not request.user.is_superuser:
            plans_qs = plans_qs.none()
        else:
             plans_qs = plans_qs.filter(year=target_year) # Superuser ve todo el año

    # **Transformar Datos para Frappe Gantt:**
    tasks_for_gantt = []
    for plan in plans_qs:
        # Asumimos que cada tarea dura 1 día para simplificar
        start_date = plan.fecha_proximo_cumplimiento
        if not start_date: continue # Omitir si no hay fecha

        end_date = start_date # Frappe necesita start y end
        # --- MODIFICADO: Construir nombre descriptivo ---
        tema = escape(plan.requisito_empresa.requisito.tema) if plan.requisito_empresa and plan.requisito_empresa.requisito else "N/A"
        obligacion = escape(plan.requisito_empresa.requisito.Obligacion) if plan.requisito_empresa and plan.requisito_empresa.requisito else "N/A"
        sede_nombre = escape(plan.sede.nombre) if plan.sede else "N/A"
        # Formato: Tema / Obligación - Sede
        task_name = f"{tema} / {obligacion} - Sede: {sede_nombre}"
        # --------


        tasks_for_gantt.append({
            'id': str(plan.id), # ID único como string
            #'name': f"{plan.requisito_empresa.requisito.tema} ({plan.requisito_empresa.sede.nombre})", # Nombre descriptivo
            'name': task_name, # <-- Usar el nombre descriptivo
            'start': start_date.isoformat(), # Formato YYYY-MM-DD
            'end': end_date.isoformat(),     # Formato YYYY-MM-DD
            'progress': 0, # Progreso (podría calcularse de EjecucionMatriz después)
            'dependencies': '', # Dependencias (vacío por ahora)
            # 'custom_class': 'bar-milestone' # Clases CSS opcionales
        })

    # Convertir a JSON de forma segura para pasarlo a la plantilla
    gantt_data_json = json.dumps(tasks_for_gantt, cls=DjangoJSONEncoder)

    context = {
        'title': f"Plan de Cumplimiento (Gantt) - Año {target_year}",
        'gantt_data_json': gantt_data_json,
        'selected_year': target_year,
        # Necesario para la plantilla base del admin
        'opts': Plan._meta,
        'site_header': admin.site.site_header,
        'site_title': admin.site.site_title,
        'is_popup': False,
        'is_nav_sidebar_enabled': True,
    }
    # Renderizar una nueva plantilla HTML
    return render(request, 'admin/myapp/plan/plan_gantt.html', context)



class UserCompanyInline(admin.TabularInline): #new class
    model = UserCompany
    extra = 1
    verbose_name = "Empresa del usuario"  # Correct label
    verbose_name_plural = "Empresas del usuario"  # Correct label (plural)
    fields = ('company',) # This is the line we need.
    
    
class YearPlanListFilter(admin.SimpleListFilter):
    title = 'Año'
    parameter_name = 'year'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            years = Plan.objects.values_list('year', flat=True).distinct()
        elif request.selected_company:
            years = Plan.objects.filter(empresa=request.selected_company).values_list('year', flat=True).distinct()
        else:
            years = []
        return [(year, str(year)) for year in sorted(years)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(year=self.value())
        return queryset

    def choices(self, changelist):
        all_choice = next(super().choices(changelist))
        yield all_choice
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }
  

##### inicio de resources para importar  ###################

class PaisResource(resources.ModelResource):
    class Meta:
        model = Pais
        import_id_fields = ('codigo',)


class IndustriaResource(resources.ModelResource):
    class Meta:
        model = Industria
        import_id_fields = ('nombre',)


class EmpresaResource(resources.ModelResource):
    class Meta:
        model = Empresa
        import_id_fields = ('codigoempresa',)


class SedeResource(resources.ModelResource):
    class Meta:
        model = Sede
        # Puedes elegir un campo único o una combinación como import_id_fields
        # Si no tienes un campo único aparte del ID, puedes usar 'id'
        # o una combinación como ('empresa', 'nombre') si unique_together lo permite
        # Para este ejemplo, asumiremos que 'id' es suficiente para importación si no hay otro identificador único.
        # Si necesitas importar y la combinación empresa+nombre es única, úsala:
        # import_id_fields = ('empresa', 'nombre')
        # Si usas 'empresa', necesitarás un Field en el resource para manejar la relación por codigoempresa
        # Por simplicidad, si no vas a importar sedes masivamente por ahora, puedes omitir import_id_fields
        # o usar 'id' si es la PK autogenerada.
        # Vamos a usar 'id' como PK autogenerada por defecto.
        import_id_fields = ('id',) # O considera ('empresa', 'nombre') si es más útil para tu caso de uso
        fields = ('id', 'empresa__codigoempresa', 'nombre', 'direccion', 'telefono', 'email', 'activo', 'descripcion') # Ejemplo de campos a exportar/importar
        export_order = fields # Define el orden de exportación



class RequisitoLegalResource(resources.ModelResource):
    class Meta:
        model = RequisitoLegal
        import_id_fields = ('id',)


class RequisitosPorEmpresaResource(resources.ModelResource):
    class Meta:
        model = RequisitosPorEmpresa
        import_id_fields = ('id',)


class RequisitoPorEmpresaDetalleResource(resources.ModelResource):
    class Meta:
        model = RequisitoPorEmpresaDetalle
        import_id_fields = ('matriz', 'requisito',)


class EjecucionMatrizResource(resources.ModelResource):
    class Meta:
        model = EjecucionMatriz
        import_id_fields = ('matriz', 'requisito',)


class PlanResource(resources.ModelResource):
    class Meta:
        model = Plan
        import_id_fields = ('id',)


class CustomUserResource(resources.ModelResource):
    class Meta:
        model = CustomUser
        import_id_fields = ('username')


##### fin de resources para importar  ###################

##### inicio creacion de classes para admin ###################

# new classes for filters ################################

class EmpresaRequisitoLegalListFilter(admin.SimpleListFilter):
    title = 'Requisito Legal'
    parameter_name = 'requisito'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            queryset = RequisitoLegal.objects.all()
        elif request.selected_company: # New change
            queryset = RequisitoLegal.objects.filter(requisitoporempresadetalle__matriz__empresa=request.selected_company).distinct() # New Change
        else:
            queryset = RequisitoLegal.objects.none()
        return [(r.id, str(r)) for r in queryset]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(requisito__id=self.value())
        return queryset

class EmpresaRequisitosPorEmpresaListFilter(admin.SimpleListFilter):
    title = 'Requisito por Empresa'
    parameter_name = 'matriz'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            queryset = RequisitosPorEmpresa.objects.all()
        elif request.selected_company: # New change
            queryset = RequisitosPorEmpresa.objects.filter(empresa=request.selected_company) # New change
        else:
            queryset = RequisitosPorEmpresa.objects.none() # New Change
        return [(r.id, str(r)) for r in queryset]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(matriz__id=self.value())
        return queryset
    
class EmpresaPlanListFilter(admin.SimpleListFilter):
    title = 'Plan'
    parameter_name = 'plan'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            queryset = Plan.objects.all()
        elif request.selected_company: # New Change
            queryset = Plan.objects.filter(empresa=request.selected_company) # New Change
        else:
            queryset = Plan.objects.none()
        return [(r.id, str(r)) for r in queryset]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(plan__id=self.value())
        return queryset

class EmpresaPlanFilter(admin.SimpleListFilter):
    title = 'Empresa'
    parameter_name = 'empresa'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            return [(e.codigoempresa, e.nombreempresa) for e in Empresa.objects.all()]
        elif request.selected_company: # New Change
            return [(request.selected_company.codigoempresa, request.selected_company.nombreempresa)] # New Change
        else:
            return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(empresa__codigoempresa=self.value())
        return queryset

class EmpresaRequisitoPorEmpresaDetalleListFilter(admin.SimpleListFilter):
    title = 'Requisito por Empresa'
    parameter_name = 'requisito_empresa'

    def lookups(self, request, model_admin):
        if request.user.is_superuser:
            return [(r.id, str(r)) for r in RequisitoPorEmpresaDetalle.objects.all()]
        elif request.selected_company: # New Change
            return [(r.id, str(r)) for r in RequisitoPorEmpresaDetalle.objects.filter(matriz__empresa=request.selected_company)] # New change
        else:
            return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(requisito_empresa__id=self.value())
        return queryset

# End of new classes for filters ###########################


class PaisAdmin(SemanticImportExportModelAdmin):
    resource_classes = [PaisResource]
    list_display = ('codigo', 'nombre')
    list_filter = ('codigo', 'nombre')
    search_fields = ('codigo', 'nombre')

    class Meta:
        verbose_name = " Pais "
        model = Pais


class IndustriaAdmin(SemanticImportExportModelAdmin):
    resource_classes = [IndustriaResource]
    list_display = ('nombre', 'descripcion')
    list_filter = ('nombre', 'descripcion')
    search_fields = ('nombre', 'descripcion')

    class Meta:
        verbose_name = " Industria "
        model = Industria


class EmpresaAdmin(SemanticImportExportModelAdmin):
    resource_classes = [EmpresaResource]
    list_display = ('codigoempresa', 'nombreempresa')
    list_filter = ('codigoempresa', 'nombreempresa')
    search_fields = ('codigoempresa', 'nombreempresa')

    class Meta:
        verbose_name = " Empresa "
        model = Empresa


class SedeAdmin(SemanticImportExportModelAdmin):
    """
    Configuración del Admin para el modelo Sede.
    Permite la gestión de las sedes por empresa.
    """
    resource_classes = [SedeResource] # Asocia el resource creado arriba
    list_display = ('nombre', 'empresa', 'direccion', 'telefono', 'activo')
    # Usa el filtro de empresa existente para filtrar las sedes por la empresa seleccionada
    list_filter = (EmpresaPlanFilter, 'activo')
    search_fields = ('nombre', 'empresa__nombreempresa', 'direccion', 'telefono', 'email')
    list_editable = ('activo',) # Permite editar el estado activo directamente en la lista

    # Filtra el queryset del campo 'empresa' en el formulario de añadir/editar
    # para mostrar solo la empresa seleccionada si el usuario no es superuser.
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "empresa":
            if not request.user.is_superuser and hasattr(request, 'selected_company') and request.selected_company:
                 # Restringe el queryset a la empresa seleccionada por el usuario
                 kwargs["queryset"] = Empresa.objects.filter(codigoempresa=request.selected_company.codigoempresa)
            elif not request.user.is_superuser:
                 # Si no es superuser y no hay empresa seleccionada (caso raro en admin con middleware),
                 # podrías restringir a las empresas asociadas al usuario si tu CustomUser tiene esa relación.
                 # Asumiendo que el middleware ya maneja esto, este caso podría no ser necesario o requerir lógica adicional.
                 # Por ahora, si no hay selected_company para un no-superuser, no mostramos empresas.
                 kwargs["queryset"] = Empresa.objects.none() # O Empresa.objects.filter(users=request.user) si tienes esa relación
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # Filtra el queryset principal de la lista de sedes
    # para mostrar solo las sedes de la empresa seleccionada si el usuario no es superuser.
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request, 'selected_company') and request.selected_company:
            return qs.filter(empresa=request.selected_company)
        # Si no es superuser y no hay empresa seleccionada, no muestra ninguna sede.
        return qs.none()

    class Meta:
        verbose_name = " Sede "
        verbose_name_plural = " Sedes "
        model = Sede


class RequisitosLegalAdmin(SemanticImportExportModelAdmin):
    resource_classes = [RequisitoLegalResource]
    list_display = ('id', 'entidad_que_emite', 'jerarquia_de_la_norma', 'fecha', 'Obligacion', 'articulo_aplicable', 'periodicidad', 'pais', 'industria')
    list_filter = ('tema', 'entidad_que_emite' ) # <-- Añadido aquí (opcional)
    search_fields = ('tema', 'entidad_que_emite') # <-- Añadido aquí (opcional, buscar en DurationField puede ser limitado)

    class Meta:
        verbose_name = " Requisito Legal "
        model = RequisitoLegal

class RequisitosPorEmpresaDetalleInline(SemanticTabularInline):
    """
    Inline para mostrar y editar los detalles de los requisitos asociados
    a una 'RequisitosPorEmpresa'. Hereda de SemanticTabularInline.
    """
    # --- Atributos Esenciales ---
    model = RequisitoPorEmpresaDetalle
    #form = RequisitoPorEmpresaDetalleForm  # Usa el formulario personalizado si lo tienes. Se ha quitado ya que no hay ningun campo que se modifique
    extra = 1  # Número de formularios extra vacíos

    # --- Campos que se mostrarán ---
    fields = (
        'requisito',
        'sede',
        'descripcion_cumplimiento',
        'periodicidad',
        'fecha_inicio',
        'tiempo_validacion',
        'fecha_final'  # Campo calculado
    )

    # --- Campos de solo lectura ---
    readonly_fields = ('fecha_final',)

    # --- Nombres para la UI ---
    verbose_name = "Detalle de Requisito por Empresa"
    verbose_name_plural = "Detalles de Requisitos por Empresa"

    # --- Personalización de Widgets ---


# myapp/admin.py (DENTRO de RequisitosPorEmpresaDetalleInline)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Personaliza el widget y el queryset para los campos ForeignKey.
        Filtra 'sede' por empresa y usa Select2 para 'requisito'.
        """
        if db_field.name == "sede":
            sede_queryset = Sede.objects.none() # Inicializar

            # 1. Prioridad: Editando matriz existente
            if request.GET.get('matriz__empresa'):
                empresa_id = request.GET.get('matriz__empresa')
                # print(f"DEBUG (formfield_for_foreignkey - sede): Editando matriz, filtrando por empresa ID: {empresa_id}") # DEBUG - Puede quitarse
                sede_queryset = Sede.objects.filter(empresa_id=empresa_id).order_by('nombre')

            # 2. Añadiendo (Estándar o Personalizado)
            elif hasattr(request, 'selected_company') and request.selected_company:
                selected_company = request.selected_company
                # print(f"DEBUG (formfield_for_foreignkey - sede): Añadiendo, filtrando por selected_company: {selected_company.codigoempresa}") # DEBUG - Puede quitarse
                sede_queryset = Sede.objects.filter(empresa=selected_company).order_by('nombre')

            # 3. Fallback
            else:
                # print("DEBUG (formfield_for_foreignkey - sede): No se encontró contexto de empresa. Queryset vacío.") # DEBUG - Puede quitarse
                pass # sede_queryset ya es Sede.objects.none()


            # Asignar el queryset filtrado a kwargs
            kwargs['queryset'] = sede_queryset


        elif db_field.name == "requisito":
            # Aplicar Select2 con AJAX para 'requisito'
            kwargs['widget'] = Select2Widget(
                 attrs={
                     'style': 'min-width: 400px;',
                     'data-ajax--url': reverse_lazy('myapp:select2_requisito_legal'),
                     'data-ajax--cache': 'true',
                     'data-minimum-input-length': '2',
                     'data-placeholder': 'Buscar requisito...',
                 }
             )

        # Llamar al método padre DESPUÉS de haber modificado kwargs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)



    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Personaliza widgets para campos normales (ej. tamaño de Textarea)."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'descripcion_cumplimiento':
            # Ajusta el tamaño del widget Textarea
            formfield.widget.attrs['rows'] = 2
            formfield.widget.attrs['cols'] = 40
        return formfield


        
class RequisitosPorEmpresaAdmin(SemanticImportExportModelAdmin):
    # ... (resource_classes, list_display sin 'duplicate_link', list_filter, search_fields, inlines) ...
    resource_classes = [RequisitosPorEmpresaResource]
    # Quitamos 'duplicate_link' si esa funcionalidad ya no se usa o se reemplaza
    list_display = ('id', 'nombre', 'descripcion', 'get_empresa_nombre')
    list_filter = (EmpresaPlanFilter, 'nombre')
    search_fields = ('empresa__nombreempresa', 'nombre', 'descripcion')
    inlines = [RequisitosPorEmpresaDetalleInline]

    def get_empresa_nombre(self, obj):
        return obj.empresa.nombreempresa
    get_empresa_nombre.short_description = 'Empresa'
    get_empresa_nombre.admin_order_field = 'empresa__nombreempresa'

    # --- NUEVA VISTA PERSONALIZADA (INICIO) ---


    # --- Sobrescribir get_urls ---
    # --- Opcional: Modificar changelist_view para añadir botón ---
    # (Alternativa a modificar la plantilla)
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        # --- PASAR EL NOMBRE CORTO DE LA URL AL CONTEXTO ---
        # El nombre corto que definimos en get_urls
        extra_context['create_with_reqs_url_name'] = 'create_with_reqs'
        # Ya no necesitamos llamar a reverse() aquí
        # -------------------------------------------------

        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'duplicate_to_plan/',
                self.admin_site.admin_view(self.duplicate_to_plan),
                name='myapp_requisitosporempresa_duplicate_to_plan',
            ),
        ]
        return custom_urls + urls


    # --- Fin changelist_view ---
    
    class Meta:
        verbose_name = "Requisito Por Empresa"
        verbose_name_plural = "Requisitos Por Empresa"
        model = RequisitosPorEmpresa





    """
    Configuración del Admin para el modelo RequisitosPorEmpresa.
    Permite la gestión de las matrices de requisitos por empresa y
    la duplicación de requisitos a planes anuales.
    """
    resource_classes = [RequisitosPorEmpresaResource] # Para import/export
    list_display = ('id', 'nombre', 'descripcion', 'get_empresa_nombre', 'duplicate_link')
    list_filter = (EmpresaPlanFilter, 'nombre') # Usar filtro de empresa personalizado
    search_fields = ('empresa__nombreempresa', 'nombre', 'descripcion') # Buscar por nombre de empresa
    inlines = [RequisitosPorEmpresaDetalleInline] # Incluir el inline definido arriba

    def get_empresa_nombre(self, obj):
        """Método para mostrar el nombre de la empresa en list_display."""
        return obj.empresa.nombreempresa
    get_empresa_nombre.short_description = 'Empresa'
    get_empresa_nombre.admin_order_field = 'empresa__nombreempresa'

    # --- Funcionalidad de Duplicación ---
    def duplicate_to_plan(self, request):
        """
        Vista personalizada del admin para manejar la duplicación de requisitos
        de todas las matrices a los planes de un año específico.
        """
        if request.method == 'POST':
            target_year = request.POST.get('target_year')
            if target_year:
                try:
                    target_year = int(target_year)
                    # Llama a la función de utilidad que realiza la duplicación
                    # (Asegúrate que la función `duplicate_requisitos_to_plan` esté definida en utils.py)
                    duplicate_requisitos_to_plan(target_year)
                    messages.success(request, f'Requisitos duplicados al plan del año {target_year} exitosamente.')
                except ValueError:
                    messages.error(request, 'Año inválido. Debe ser un número entero.')
                except Exception as e:
                    messages.error(request, f'Error al duplicar: {e}')
            else:
                messages.error(request, 'Debe seleccionar un año de destino.')

            # Redirige de vuelta a la lista de RequisitosPorEmpresa después de la acción
            return HttpResponseRedirect(reverse('admin:myapp_requisitosporempresa_changelist'))

        # Contexto para renderizar la plantilla del formulario de duplicación
        context = dict(
           self.admin_site.each_context(request),
           opts=self.model._meta, # Pasa las opciones del modelo a la plantilla
           title="Duplicar Requisitos al Plan Anual" # Título para la página
        )
        # Renderiza la plantilla HTML que contiene el formulario para ingresar el año
        return render(request, 'admin/duplicate_to_plan.html', context)

    duplicate_to_plan.short_description = "Creacion del Plan Anual basado en los requisitos por Empresa"

    def get_urls(self):
        """Añade la URL personalizada para la vista de duplicación."""
        urls = super().get_urls()
        custom_urls = [
            path(
                'duplicate_to_plan/',
                self.admin_site.admin_view(self.duplicate_to_plan),
                # Nombre único para la URL, incluyendo app_label y model_name
                name='myapp_requisitosporempresa_duplicate_to_plan',
            ),
        ]
        return custom_urls + urls

    def duplicate_link(self, obj):
        """
        Genera un enlace en la columna 'duplicate_link' de list_display
        para acceder a la vista de duplicación.
        Nota: Este enlace aparecerá en cada fila, pero la acción es global.
              Podría ser más intuitivo mover esto a las acciones globales del admin.
        """
        # Enlaza a la vista de duplicación general
        url = reverse('admin:myapp_requisitosporempresa_duplicate_to_plan')
        return format_html('<a href="{}">Generar Plan</a>', url)

    duplicate_link.short_description = "Generar Plan" # Nombre de la columna

    # --- Fin Funcionalidad de Duplicación ---

    class Meta:
        verbose_name = "Requisito Por Empresa" # Nombre singular
        verbose_name_plural = "Requisitos Por Empresa" # Nombre plural
        model = RequisitosPorEmpresa

class EjecucionMatrizAdmin(SemanticImportExportModelAdmin):
    resource_classes = [EjecucionMatrizResource]
    list_display = (
        'matriz', 'requisito', 'plan', 'porcentaje_cumplimiento', 'responsable', 'fecha_ejecucion', 'ejecucion',
        'get_conforme', 'get_next_compliance_date')
    list_filter = (
        EmpresaRequisitosPorEmpresaListFilter,
        EmpresaRequisitoLegalListFilter,
        EmpresaPlanListFilter,
        'ejecucion',
        'conforme',
        'porcentaje_cumplimiento',
        'fecha_ejecucion',
        )
    search_fields = (
        'matriz__nombre', 'requisito__tema', 'plan__empresa__nombreempresa', 'plan__periodicidad', 'responsable')
    
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['razon_no_conforme'].label = "Razon"
        return form
    
    
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'plan':
            kwargs['label'] = "Plan"
            if not request.user.is_superuser and request.selected_company: # Change this line
                kwargs['queryset'] = Plan.objects.filter(empresa=request.selected_company) #Change this line

        if db_field.name == 'matriz':
            kwargs['label'] = "Requisito por Empresa"
            if not request.user.is_superuser and request.selected_company: # Change this line
                kwargs['queryset'] = RequisitosPorEmpresa.objects.filter(empresa=request.selected_company) # Change this line
        
        if db_field.name == 'requisito':
            kwargs['label'] = "Requisito Legal"
            if not request.user.is_superuser and request.selected_company: # Change this line
                kwargs['queryset'] = RequisitoLegal.objects.filter(requisitoporempresadetalle__matriz__empresa=request.selected_company).distinct() # Change this line

            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_next_compliance_date(self, obj):
        # --- Corrección: Acceder directamente al campo del Plan ---
        if obj.plan:
            return obj.plan.fecha_proximo_cumplimiento # Ya no se llama al método
        return None

    get_next_compliance_date.short_description = "Fecha Próximo Cumplimiento"
    get_next_compliance_date.admin_order_field = 'plan__fecha_proximo_cumplimiento'

    def get_conforme(self, obj):
        if obj.conforme == 'Si':
            return 'Sí'
        else:
            return 'No'

    get_conforme.short_description = 'Conforme'
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'conforme':
            kwargs['widget'] = admin.widgets.AdminRadioSelect(attrs={'class': 'ui'}) #change this line
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.selected_company: # Change this line
            return qs.filter(plan__empresa=request.selected_company) #Change this line
        else:
            return qs.none()

    def save_model(self, request, obj, form, change):
        if obj.conforme == 'No' and (obj.razon_no_conforme is None or obj.razon_no_conforme.strip() == ''):
            print("Excepción capturada osvaldo check:")
            form_errors = {'razon_no_conforme': ["Si el resultado es 'No conforme', debe especificar una razón."]}
            first_error_message = " ".join(form_errors['razon_no_conforme'])
            raise PermissionDenied(first_error_message)
        try:
            super().save_model(request, obj, form, change)
        except Exception as e:
            print("Excepción general capturada:", e)
            raise PermissionDenied(f"An unexpected error occurred: {e}")

                 
    class Meta:
        verbose_name = " Ejecucion Del Plan "
        model = EjecucionMatriz

class PlanAdmin(SemanticImportExportModelAdmin):
    resource_classes = [PlanResource]
    # Escríbelo así, con cuidado:
    list_display = ('id', 'year', 'empresa', 'get_requisito_info', 'fecha_proximo_cumplimiento' , 'responsable_ejecucion')
    #list_display = ('id', 'empresa', 'get_requisito_info', 'periodicidad', 'fecha_proximo_cumplimiento', 'responsable_ejecucion', 'descripcion_periodicidad', 'year')

    list_filter = (
        EmpresaPlanFilter,
        'periodicidad',
        'year',
        'fecha_proximo_cumplimiento',
        'responsable_ejecucion'
    )
    search_fields = (
        'empresa__nombreempresa',
        'requisito_empresa__requisito__tema',
        'requisito_empresa__requisito__Obligacion', 
        'periodicidad',
        'descripcion_periodicidad',
        'responsable_ejecucion__username',
        'responsable_ejecucion__first_name',
        'responsable_ejecucion__last_name'
    )
    raw_id_fields = ('responsable_ejecucion',)

    # --- MÉTODO MODIFICADO PARA MOSTRAR TEMA Y OBLIGACIÓN ---
    def get_requisito_info(self, obj):
        """Muestra el Tema y un extracto de la Obligación del RequisitoLegal."""
        if obj.requisito_empresa and obj.requisito_empresa.requisito:
            tema = obj.requisito_empresa.requisito.tema
            obligacion = obj.requisito_empresa.requisito.Obligacion
            # Truncar la obligación para que no sea demasiado larga en la tabla
            max_len = 80 # Ajusta este número según necesites
            obligacion_trunc = (obligacion[:max_len-3] + '...') if len(obligacion) > max_len else obligacion
            # Combinar tema y obligación truncada
            return f"{tema}: {obligacion_trunc}"
        return "N/A" # Valor por defecto si falta la relación
    # Actualizar descripción y campo de ordenación
    get_requisito_info.short_description = 'Requisito (Tema/Obligación)' # Nuevo título de columna
    get_requisito_info.admin_order_field = 'requisito_empresa__requisito__tema' # Ordenar por tema sigue siendo lo más práctico
    # -------------------------------------------------------

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "responsable_ejecucion":
             pass # Por ahora, muestra todos
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Meta:
        verbose_name = " Plan (Tarea) "
        verbose_name_plural = " Planes (Tareas) "
        model = Plan


    
class CustomUserAdmin(SemanticImportExportModelAdmin):
    resource_classes = [CustomUserResource]
    list_display = ('username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active', 'get_empresa_name')  # I add get_empresa_name here
    list_filter = ('username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active')
    #filter_horizontal = ('Empresa',) #remove this line
    inlines = [UserCompanyInline] #Add this line

    def get_empresa_name(self, obj):
        return ", ".join([e.nombreempresa for e in obj.Empresa.all()])

    get_empresa_name.short_description = 'Empresa'

    def save_model(self, request, obj, form, change):
        if 'password' in form.changed_data:
            obj.password = make_password(obj.password)
        super().save_model(request, obj, form, change)

    # def save_related(self, request, form, formsets, change): #remove this function
    #     # Call super to save M2M relations that do not need to be on our table
    #     super().save_related(request, form, formsets, change)
    #     #delete all registers for recreate the values.
    #     UserCompany.objects.filter(user=form.instance).delete()
    #     # Iterate through the selected companies and create UserCompany instances
    #     for company in form.cleaned_data['Empresa']:
    #         UserCompany.objects.create(user=form.instance, company=company)

    class Meta:
        verbose_name = " Usuarios Empresa "
        model = CustomUser


        
##### fin prepracion de clases para el admin  #######


admin.site.site_header = "Framework SAS"
admin.site.site_title = "Framework SAS"
admin.site.index_title = "Framework SAS"
admin.site.login_form = CustomAdminLoginForm # Add this line



admin.site.register(Pais, PaisAdmin)
admin.site.register(Industria, IndustriaAdmin)
admin.site.register(Empresa, EmpresaAdmin)
admin.site.register(Sede, SedeAdmin)
admin.site.register(RequisitoLegal, RequisitosLegalAdmin)
admin.site.register(RequisitosPorEmpresa, RequisitosPorEmpresaAdmin)  # Renamed from MatrizEmpresa
admin.site.register(EjecucionMatriz, EjecucionMatrizAdmin)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Plan, PlanAdmin)

admin.site.get_app_list = app_resort(admin.site.get_app_list)
