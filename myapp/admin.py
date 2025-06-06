from datetime import date, timedelta # Añadir timedelta
import json
from django.contrib import admin
from django.forms import ValidationError
from import_export import resources
from myapp.models import Empresa, RequisitoLegal, EjecucionMatriz, RequisitosPorEmpresa, Plan, Pais, Industria, RequisitoPorEmpresaDetalle , Sede
from users_app.models import CustomUser, UserCompany # Add UserCompany here
from .utils import duplicate_requisitos_to_plan, add_working_days # Añadir add_working_days
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
import logging # Asegúrate que esté importado

logger = logging.getLogger(__name__) # Configura el logger para este módulo



# Coloca esto cerca del inicio de tu admin.py, después de los imports
MYAPP_MODEL_ORDER = [
    "Paises",
    "Industrias",
    "Empresas",
    "Sedes",
    "Requisitos Legales",
    "Requisitos Por Empresa",
    "Planes (Tareas)",             # Este es el verbose_name_plural de Plan
    "Ejecucion de los Planes",     # Este es el verbose_name_plural de EjecucionMatriz
]



def app_resort(func):
    """
    Decorador para ordenar la lista de aplicaciones y modelos en el admin de Django.
    - Ordena las aplicaciones alfabéticamente por su nombre visible.
    - Ordena los modelos dentro de la app "Gestion de Requisitos" (myapp) según MYAPP_MODEL_ORDER.
    - Ordena los modelos dentro de otras apps alfabéticamente.
    """
    def inner(request, *args, **kwargs):
        app_list = func(request) # Llama a la función original para obtener la lista de apps
        if not app_list:
            return app_list # Devuelve la lista vacía o None si eso es lo que se obtuvo

        try:
            # 1. Ordenar las aplicaciones por su nombre visible (ej. "Gestion de Requisitos", "Usuarios Empresa")
            # Si solo tienes una app principal, este paso podría no ser crítico, pero es bueno tenerlo.
            app_list.sort(key=lambda app: str(app.get('name', '')).lower())

            # 2. Ordenar los modelos dentro de cada aplicación
            for app in app_list:
                if app.get('models'): # Asegurarse de que la app tiene modelos
                    # Identificar tu aplicación 'myapp' por su verbose_name o app_label
                    # El verbose_name de myapp es "Gestion de Requisitos"
                    if app.get('name') == "Gestion de Requisitos" or app.get('app_label') == 'myapp':
                        # Crear un mapa para el orden deseado de los modelos de myapp
                        order_map = {name: i for i, name in enumerate(MYAPP_MODEL_ORDER)}
                        
                        # Ordenar los modelos de myapp:
                        # - Primero por el orden definido en MYAPP_MODEL_ORDER.
                        # - Los modelos no listados en MYAPP_MODEL_ORDER irán al final, ordenados alfabéticamente.
                        app['models'].sort(key=lambda model: (
                            order_map.get(str(model.get('name', '')), float('inf')), # Clave primaria: orden personalizado
                            str(model.get('name', '')).lower()  # Clave secundaria: alfabético para los demás
                        ))
                    else:
                        # Para cualquier otra aplicación, ordenar sus modelos alfabéticamente
                        app['models'].sort(key=lambda model: str(model.get('name', '')).lower())
        except Exception as e:
            logger.error(f"Error al intentar ordenar app_list en app_resort: {e}")
            # En caso de error durante la ordenación, es crucial devolver la lista original
            # obtenida de func(request) para evitar que el admin se rompa.
            return func(request) 
            
        return app_list # Devolver la lista de aplicaciones (ordenada o parcialmente ordenada)
    return inner


@admin.site.admin_view # O @staff_member_required si prefieres
#@transaction.atomic # Asegurar que todas las operaciones de BD sean atómicas
def create_with_requirements_view(request):
    
    #Vista independiente para crear una Matriz con Requisitos seleccionados.
    
    # El usuario se obtiene de request.user
    form = CreateMatrixWithRequirementsForm(request.POST or None, user=request.user)
    all_requisitos = RequisitoLegal.objects.select_related('pais').order_by('tema', 'numero') # Añadir un orden

    if request.method == 'POST':
        if form.is_valid():
            selected_req_ids = request.POST.getlist('requisitos')
            if not selected_req_ids:
                messages.error(request, "Debe seleccionar al menos un requisito.") # type: ignore
            else:
                try:
                    # Crear la matriz principal
                    nueva_matriz = form.save()

                    # Crear los detalles
                    detalles_a_crear = []
                    requisitos_seleccionados = RequisitoLegal.objects.filter(pk__in=selected_req_ids)
                    
                    # Obtener la sede una vez si es la misma para todos los detalles
                    # Usar la empresa de la matriz recién creada para asegurar consistencia
                    empresa_de_la_matriz = nueva_matriz.empresa 
                    sede_predeterminada_para_detalles = Sede.objects.filter(empresa=empresa_de_la_matriz).first()

                    if not sede_predeterminada_para_detalles:
                        messages.warning(request, f"La empresa '{empresa_de_la_matriz.nombreempresa}' no tiene sedes configuradas. Los requisitos se añadirán sin sede específica.") # type: ignore
                        # Considera si esto debería ser un error que impida continuar,
                        # dependiendo de tus reglas de negocio.

                    for req in requisitos_seleccionados:
                        detalles_a_crear.append(
                            RequisitoPorEmpresaDetalle(
                                matriz=nueva_matriz,
                                requisito=req,
                                sede=sede_predeterminada_para_detalles, # Asignar la sede predeterminada
                                # Copiar valores por defecto del RequisitoLegal si no se especifican en el detalle
                                periodicidad=req.periodicidad,
                                tiempo_validacion=req.tiempo_validacion,
                                # fecha_inicio podría ser nueva_matriz.fecha_creacion o un campo específico
                                # Si RequisitoPorEmpresaDetalle tiene un default para fecha_inicio, se usará.
                            )
                        )

                    if detalles_a_crear:
                        RequisitoPorEmpresaDetalle.objects.bulk_create(detalles_a_crear)
                        messages.success(request, f"Matriz '{nueva_matriz.nombre}' creada exitosamente con {len(detalles_a_crear)} requisitos.") # type: ignore
                        # Redirigir a la lista de matrices
                        return redirect('admin:myapp_requisitosporempresa_changelist')
                    else:
                         # Este caso es menos probable si selected_req_ids no está vacío,
                         # a menos que todos los requisitos fallen alguna condición interna.
                         messages.warning(request, "No se pudieron crear detalles de requisitos (verifique la configuración de sedes o requisitos).") # type: ignore


                except Exception as e:
                    logger.exception("Error en create_with_requirements_view POST al crear matriz o detalles")
                    messages.error(request, f"Error al crear la matriz o sus detalles: {e}") # type: ignore

        else: # Formulario no válido
            messages.error(request, "Por favor corrija los errores en el formulario.") # type: ignore

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
        import_id_fields = ('id',) # O ('plan',) si el plan es único y prefieres usarlo


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
    title = 'Requisito Legal (del Plan)' # Título actualizado
    parameter_name = 'requisito_del_plan'    # Nombre de parámetro actualizado

    def lookups(self, request, model_admin):
        # Mostrar Requisitos Legales que están asociados a Planes que tienen una EjecucionMatriz
        # y opcionalmente filtrar por la empresa seleccionada.
        plans_with_execution = Plan.objects.filter(ejecucionmatriz__isnull=False)
        if request.user.is_superuser:
            requisito_ids = plans_with_execution.values_list('requisito_empresa__requisito_id', flat=True).distinct()
        elif request.selected_company: # New change
            requisito_ids = plans_with_execution.filter(empresa=request.selected_company).values_list('requisito_empresa__requisito_id', flat=True).distinct()
        else:
            requisito_ids = []
        
        requisitos = RequisitoLegal.objects.filter(id__in=requisito_ids).order_by('tema')
        return [(r.id, f"{r.tema} - {r.Obligacion[:30]}...") for r in requisitos]

    def queryset(self, request, queryset):
        if self.value():
            # Filtrar EjecucionMatriz por el requisito legal del plan asociado
            return queryset.filter(plan__requisito_empresa__requisito__id=self.value())
        return queryset

class EmpresaRequisitosPorEmpresaListFilter(admin.SimpleListFilter):
    title = 'Matriz (del Plan)' # Título actualizado
    parameter_name = 'matriz_del_plan' # Nombre de parámetro actualizado

    def lookups(self, request, model_admin):
        # Mostrar RequisitosPorEmpresa (Matrices) que están asociados a Planes que tienen una EjecucionMatriz
        # y opcionalmente filtrar por la empresa seleccionada.
        plans_with_execution = Plan.objects.filter(ejecucionmatriz__isnull=False)
        if request.user.is_superuser:
            matriz_ids = plans_with_execution.values_list('requisito_empresa__matriz_id', flat=True).distinct()
        elif request.selected_company: # New change
            matriz_ids = plans_with_execution.filter(empresa=request.selected_company).values_list('requisito_empresa__matriz_id', flat=True).distinct()
        else:
            matriz_ids = []
        
        matrices = RequisitosPorEmpresa.objects.filter(id__in=matriz_ids).order_by('nombre')
        return [(r.id, str(r)) for r in matrices]

    def queryset(self, request, queryset):
        if self.value():
            # Filtrar EjecucionMatriz por la matriz del plan asociado
            return queryset.filter(plan__requisito_empresa__matriz__id=self.value())
        return queryset
    
class EmpresaPlanListFilter(admin.SimpleListFilter):
    title = 'Plan'
    parameter_name = 'plan'
    # Este filtro parece correcto para listar planes basados en la empresa.
    # Su uso en EjecucionMatrizAdmin.queryset es para filtrar EjecucionMatriz por el plan_id.
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
            # Esto filtra EjecucionMatriz por el ID del plan.
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
    list_display = ('codigoempresa', 'nombreempresa', 'industria', 'get_paises_operacion', 'activo')
    list_filter = ('industria', 'paises', 'activo', 'codigoempresa', 'nombreempresa')
    search_fields = ('codigoempresa', 'nombreempresa', 'industria__nombre', 'paises__nombre', 'paises__codigo')
    filter_horizontal = ('paises',) # Widget más amigable para ManyToManyField
    list_editable = ('activo',)

    def get_paises_operacion(self, obj):
        return ", ".join([p.nombre for p in obj.paises.all()])
    get_paises_operacion.short_description = 'Países de Operación'

    class Meta:
        verbose_name = " Empresa "
        model = Empresa
    
    # Opcional: Si quieres que el campo industria sea un dropdown más eficiente con muchos datos
    # def formfield_for_foreignkey(self, db_field, request, **kwargs):
    #     if db_field.name == "industria":
    #         kwargs["widget"] = Select2Widget
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)


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

    # --- NUEVA VISTA PERSONALIZADA (INICIO) ---


    # --- Sobrescribir get_urls ---
    # --- Opcional: Modificar changelist_view para añadir botón ---
    # (Alternativa a modificar la plantilla)
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            # Usar el nombre completo de la URL definida en myapp.urls (app_name:url_name)
            # para el botón "Crear Matriz con Requisitos"
            extra_context['create_matrix_with_reqs_url'] = reverse('myapp:create_matrix_with_reqs')
        except Exception: # pylint: disable=broad-except
            logger.exception("Error al generar la URL para create_matrix_with_reqs en RequisitosPorEmpresaAdmin")
            extra_context['create_matrix_with_reqs_url'] = "#" # Fallback URL
        return super().changelist_view(request, extra_context=extra_context)

    # get_urls para la acción de duplicar a plan
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'duplicate_to_plan/',
                self.admin_site.admin_view(self.duplicate_to_plan),
                # Este es el nombre para la URL de duplicar a plan,
                # que se usa en el template `admin/duplicate_to_plan.html` y el `duplicate_link`
                name='myapp_requisitosporempresa_duplicate_to_plan',
            ),
        ]
        return custom_urls + urls

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
                    messages.success(request, f'Requisitos duplicados al plan del año {target_year} exitosamente.') # type: ignore
                except ValueError:
                    messages.error(request, 'Año inválido. Debe ser un número entero.') # type: ignore
                except Exception as e:
                    messages.error(request, f'Error al duplicar: {e}') # type: ignore
            else:
                messages.error(request, 'Debe seleccionar un año de destino.') # type: ignore

            # Redirige de vuelta a la lista de RequisitosPorEmpresa después de la acción # type: ignore
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
        'get_plan_info', # Muestra info del plan
        'get_matriz_info_from_plan', # Muestra info de la matriz desde el plan
        'get_requisito_info_from_plan', # Muestra info del requisito desde el plan
        'porcentaje_cumplimiento', 'responsable', 'fecha_ejecucion', 'ejecucion',
        'get_conforme')
    list_filter = (
        EmpresaRequisitosPorEmpresaListFilter, # Filtro adaptado
        EmpresaRequisitoLegalListFilter,   # Filtro adaptado
        EmpresaPlanListFilter,
        'ejecucion',
        'conforme',
        'porcentaje_cumplimiento',
        'fecha_ejecucion',
        )
    search_fields = (
        'plan__requisito_empresa__matriz__nombre',      # Buscar por nombre de la matriz del plan
        'plan__requisito_empresa__requisito__tema',     # Buscar por tema del requisito del plan
        'plan__empresa__nombreempresa', 'plan__periodicidad', 'responsable')
    readonly_fields = ('get_matriz_info_from_plan', 'get_requisito_info_from_plan')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['razon_no_conforme'].label = "Razon"
        return form
    
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'plan':
            kwargs['label'] = "Plan"
            if not request.user.is_superuser and request.selected_company: # Change this line
                kwargs['queryset'] = Plan.objects.filter(empresa=request.selected_company) #Change this line
        # Los campos 'matriz' y 'requisito' ya no están en el modelo,
        # por lo que no se necesita lógica para ellos aquí.
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_plan_info(self, obj):
        if obj.plan:
            return str(obj.plan) # O un formato más específico si lo deseas
        return "N/A"
    get_plan_info.short_description = "Plan Asociado"
    get_plan_info.admin_order_field = 'plan'

    def get_matriz_info_from_plan(self, obj):
        if obj.plan and obj.plan.requisito_empresa and obj.plan.requisito_empresa.matriz:
            return str(obj.plan.requisito_empresa.matriz)
        return "N/A"
    get_matriz_info_from_plan.short_description = "Matriz (del Plan)"

    def get_requisito_info_from_plan(self, obj):
        if obj.plan and obj.plan.requisito_empresa and obj.plan.requisito_empresa.requisito:
            return str(obj.plan.requisito_empresa.requisito.tema) # O más info
        return "N/A"
    get_requisito_info_from_plan.short_description = "Requisito Legal (del Plan)"

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
        # La validación de 'razon_no_conforme' ya se maneja en el método clean() del modelo EjecucionMatriz,
        # y el método save() del modelo llama a full_clean().
        # Por lo tanto, la validación aquí es redundante y puede eliminarse.
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        """
        Pre-rellena el campo 'plan' si se pasa como parámetro GET.
        """
        initial = super().get_changeform_initial_data(request)
        plan_id = request.GET.get('plan')
        if plan_id:
            initial['plan'] = plan_id
        return initial

                 
    class Meta:
        verbose_name = " Ejecucion Del Plan "
        model = EjecucionMatriz

class PlanAdmin(SemanticImportExportModelAdmin):
    resource_classes = [PlanResource]
    # Escríbelo así, con cuidado:
    list_display = ('id', 'year', 'empresa', 'get_requisito_info', 'fecha_proximo_cumplimiento' , 'get_responsables_ejecucion')
    #list_display = ('id', 'empresa', 'get_requisito_info', 'periodicidad', 'fecha_proximo_cumplimiento', 'responsable_ejecucion', 'descripcion_periodicidad', 'year')

    list_filter = (
        EmpresaPlanFilter,
        'periodicidad',
        'year',
        'fecha_proximo_cumplimiento',
        ('responsables_ejecucion', admin.RelatedOnlyFieldListFilter), # Para filtrar por responsables
    )
    search_fields = (
        'empresa__nombreempresa',
        'requisito_empresa__requisito__tema',
        'requisito_empresa__requisito__Obligacion', 
        'periodicidad',
        'descripcion_periodicidad',
        'responsables_ejecucion__username', # Buscar por username de los responsables
        'responsables_ejecucion__first_name', # Buscar por nombre de los responsables
        'responsables_ejecucion__last_name'  # Buscar por apellido de los responsables
    )
    filter_horizontal = ('responsables_ejecucion',) # Widget amigable para ManyToManyField

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

    # --- NUEVO MÉTODO PARA MOSTRAR RESPONSABLES ---
    def get_responsables_ejecucion(self, obj):
        return ", ".join([user.username for user in obj.responsables_ejecucion.all()])
    get_responsables_ejecucion.short_description = 'Responsables'
    # -------------------------------------------------------

    def get_queryset(self, request):
        """
        Filtra los planes mostrados en la lista según la empresa seleccionada,
        a menos que el usuario sea superuser.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request, 'selected_company') and request.selected_company:
            return qs.filter(empresa=request.selected_company)
        # Si no es superuser y no hay empresa seleccionada, no muestra ningún plan.
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Filtra los querysets de los campos ForeignKey en el formulario de Plan
        basándose en la empresa del plan (si se edita) o la empresa seleccionada
        en la sesión (si se añade y el usuario no es superuser).
        """
        # Determinar la empresa de contexto para filtrar otros campos
        empresa_para_filtros_dependientes = None
        object_id = request.resolver_match.kwargs.get('object_id')

        if object_id: # Editando un Plan existente
            try:
                # Usamos self.model para referirnos al modelo del admin actual (Plan)
                plan_instance = self.model.objects.get(pk=object_id)
                empresa_para_filtros_dependientes = plan_instance.empresa
            except self.model.DoesNotExist:
                pass # El objeto no existe, Django lo manejará
            except Exception as e:
                logger.warning(f"PlanAdmin: No se pudo obtener la instancia del plan {object_id} para determinar la empresa: {e}")
                pass
        else: # Añadiendo un nuevo Plan
            if not request.user.is_superuser:
                if hasattr(request, 'selected_company') and request.selected_company:
                    empresa_para_filtros_dependientes = request.selected_company
            # Si es superuser añadiendo, empresa_para_filtros_dependientes permanece None.
            # Esto significa que los campos dependientes (sede, responsable, etc.)
            # mostrarán todas las opciones hasta que se seleccione una empresa para el Plan.

        # Aplicar filtros a los campos ForeignKey específicos
        if db_field.name == "empresa":
            if not request.user.is_superuser:
                # Para un no-superuser, el campo 'empresa' del Plan se limita a la selected_company
                if hasattr(request, 'selected_company') and request.selected_company:
                    qs = Empresa.objects.filter(pk=request.selected_company.pk)
                    kwargs['queryset'] = qs
                    if qs.count() == 1: # Debería ser siempre 1 si selected_company existe
                        kwargs['initial'] = qs.first()
                else:
                    # Si no hay selected_company, un no-superuser no puede elegir/crear un plan para ninguna empresa
                    kwargs['queryset'] = Empresa.objects.none()
            # Si es superuser, ve todas las empresas (comportamiento por defecto de Django)

        if db_field.name == "responsables_ejecucion": # Actualizado al nuevo nombre del campo
            if empresa_para_filtros_dependientes:
                # Asumiendo que CustomUser tiene una relación M2M 'Empresa'
                kwargs['queryset'] = CustomUser.objects.filter(Empresa=empresa_para_filtros_dependientes).distinct().order_by('username')
            elif not request.user.is_superuser: # Añadiendo, no superuser, y sin selected_company (empresa_para_filtros_dependientes es None)
                kwargs['queryset'] = CustomUser.objects.none()
            # else: Superuser añadiendo sin empresa seleccionada aún para el Plan, o error obteniendo empresa -> ve todos los usuarios

        elif db_field.name == "sede":
            if empresa_para_filtros_dependientes:
                kwargs['queryset'] = Sede.objects.filter(empresa=empresa_para_filtros_dependientes).order_by('nombre')
            elif not request.user.is_superuser:
                kwargs['queryset'] = Sede.objects.none()

        elif db_field.name == "requisito_empresa": # Este es RequisitoPorEmpresaDetalle
            if empresa_para_filtros_dependientes:
                kwargs['queryset'] = RequisitoPorEmpresaDetalle.objects.filter(matriz__empresa=empresa_para_filtros_dependientes).select_related('matriz', 'requisito', 'sede').order_by('matriz__nombre', 'requisito__tema')
            elif not request.user.is_superuser:
                kwargs['queryset'] = RequisitoPorEmpresaDetalle.objects.none()

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
