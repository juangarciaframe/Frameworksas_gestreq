# myapp/models.py

from django.conf import settings
from django.db import models
from django.forms import ValidationError
# from django.contrib.auth.models import User # Comentado si usas CustomUser
from datetime import date, timedelta
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
# QUITA ESTA LÍNEA DE AQUÍ ARRIBA:
# from .utils import add_working_days
import logging

logger = logging.getLogger(__name__)

def get_default_industria_pk():
    """
    Obtiene o crea la Industria con nombre 'Todas' y devuelve su clave primaria (pk/id).
    """
    try:
        industria, created = Industria.objects.get_or_create(nombre="Todas")
        if created:
            logger.info(f"Industria por defecto 'Todas' creada con ID: {industria.pk}")
        return industria.pk
    except Exception as e:
        # Esto podría ocurrir si la base de datos no está lista o hay otros problemas.
        # Durante las migraciones iniciales, esto puede ser problemático.
        # Es crucial que la tabla 'myapp_industria' exista y sea accesible.
        logger.error(f"No se pudo obtener o crear la industria por defecto 'Todas': {e}. "
                     "Asegúrese de que la tabla Industria exista y sea accesible. "
                     "Es posible que necesite crear la industria 'Todas' manualmente "
                     "y luego proporcionar su ID si esta función falla durante las migraciones.")
        return None


# --- Modelos Base (Pais, Industria, Empresa, Sede) ---
# ... (estos modelos no cambian) ...

class Pais(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(
        max_length=2,
        unique=True,
        help_text="Código ISO 3166-1 alpha-2 del país (ej. CO, MX, US)"
    )
    def __str__(self): return f"{self.nombre} ({self.codigo})"
    class Meta: verbose_name = "Pais"; verbose_name_plural = "Paises"; ordering = ['nombre']

class Industria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    def __str__(self): return self.nombre
    class Meta: verbose_name = "Industria"; verbose_name_plural = "Industrias"; ordering = ['nombre']

class Empresa(models.Model):
    codigoempresa = models.CharField(max_length = 50, primary_key=True ,  blank=False,  null=False , default="")
    nombreempresa = models.CharField(max_length= 150 , blank=False,  null=False , default="")
    direccion = models.CharField(max_length=200, blank=False, null=False, default="")
    telefono = models.CharField(max_length=20, blank=True, null=True, default="")
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to='logos_empresa/', blank=True, null=True)
    activo = models.BooleanField(default=True)
    industria = models.ForeignKey(
        Industria,
        on_delete=models.PROTECT,
        verbose_name="Industria",
        null=False,
        blank=False,
        default=get_default_industria_pk)
    paises = models.ManyToManyField(Pais, verbose_name="Países de Operación", blank=True)
    def clean(self):
        super().clean()
        qs = Empresa.objects.filter(codigoempresa=self.codigoempresa)
        if self.pk: qs = qs.exclude(pk=self.pk)
        if qs.exists(): raise ValidationError({"codigoempresa": "El código de empresa ya está en uso por otra empresa."})
    def __str__(self): return f"{self.nombreempresa} ({self.codigoempresa})"
    class Meta: verbose_name = "Empresa"; verbose_name_plural = "Empresas"; ordering = ['nombreempresa']


class Sede(models.Model):
    id = models.AutoField(primary_key=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, to_field='codigoempresa', related_name='sedes')
    nombre = models.CharField(max_length=150, blank=False, null=False, verbose_name="Nombre de la Sede")
    direccion = models.CharField(max_length=200, blank=True, null=True, verbose_name="Dirección")
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, null=True, verbose_name="Email de Contacto")
    activo = models.BooleanField(default=True, verbose_name="Activa")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción Adicional")
    def __str__(self): return f"{self.nombre} ({self.empresa_id})"
    class Meta: verbose_name = "Sede"; verbose_name_plural = "Sedes"; unique_together = ('empresa', 'nombre'); ordering = ['empresa__nombreempresa', 'nombre']


# --- Choices y Modelos de Requisitos ---

PERIODICIDAD_CHOICES = [
    ('Diaria', 'Diaria'), ('Semanal', 'Semanal'), ('Quincenal', 'Quincenal'),
    ('Mensual', 'Mensual'), ('Bimestral', 'Bimestral'), ('Trimestral', 'Trimestral'),
    ('Semestral', 'Semestral'), ('Anual', 'Anual'), ('Unica', 'Única'), ('Otro', 'Otro')
]

class RequisitoLegal(models.Model):
    TIPO_REQUISITO_CHOICES = [('Local', 'Local'), ('Externo', 'Externo'), ('Ambos', 'Ambos')]
    id = models.AutoField(primary_key=True)
    tema = models.CharField(max_length=50)
    entidad_que_emite = models.CharField(max_length=255)
    jerarquia_de_la_norma = models.CharField(max_length=255)
    numero = models.CharField(max_length=50)
    fecha = models.DateField(verbose_name="Fecha de Vigencia")
    tiempo_validacion = models.PositiveIntegerField(null=True, blank=True, verbose_name="Tiempo de Validación (Días Hábiles)", help_text="Número de días hábiles (según país) estimados o requeridos para validar.", validators=[MinValueValidator(0)])
    articulo_aplicable = models.TextField()
    Obligacion = models.TextField()
    proceso_que_aplica = models.CharField(max_length=255)
    tipo_requisito = models.CharField(max_length=10, choices=TIPO_REQUISITO_CHOICES, default='Local')
    pais = models.ForeignKey(Pais, on_delete=models.SET_NULL, null=True, blank=True)
    industria = models.ForeignKey(Industria, on_delete=models.SET_NULL, null=True, blank=True)
    periodicidad = models.CharField(max_length=20, choices=PERIODICIDAD_CHOICES, blank=True, null=True, verbose_name="Periodicidad Sugerida/Evaluación", help_text="Periodicidad con la que se suele evaluar o revisar este requisito.")
    def __str__(self): return f"Tema:{self.tema} - Obligacion: {self.Obligacion} "
    class Meta: verbose_name = "Requisito Legal"; verbose_name_plural = "Requisitos Legales"; ordering = ['tema', 'numero']

class RequisitosPorEmpresa(models.Model):
    id = models.AutoField(primary_key=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, to_field='codigoempresa')
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateField(auto_now_add=True)
    def __str__(self): return f"{self.nombre} ({self.empresa_id})"
    class Meta: verbose_name = "Requisitos Por Empresa"; verbose_name_plural = "Requisitos Por Empresa"; ordering = ['empresa__nombreempresa', 'nombre']


class RequisitoPorEmpresaDetalle(models.Model):
    matriz = models.ForeignKey(RequisitosPorEmpresa, on_delete=models.CASCADE, related_name='detalles')
    requisito = models.ForeignKey(RequisitoLegal, on_delete=models.CASCADE)
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, verbose_name="Sede de Aplicación") # Nuevo campo
    descripcion_cumplimiento = models.TextField(blank=True, null=True)
    periodicidad = models.CharField(
        max_length=20,
        choices=PERIODICIDAD_CHOICES,
        blank=True, # Permitir que el campo esté vacío en formularios
        null=True   # Permitir que el campo sea NULL en la base de datos
    )
    fecha_inicio = models.DateField(blank=False, null=False, default=timezone.now)
    tiempo_validacion = models.PositiveIntegerField(null=True, blank=True, verbose_name="Tiempo de Validación (Días Hábiles)", help_text="Número de días hábiles (según país del requisito) para validar. Usado para calcular Fecha Final.", validators=[MinValueValidator(0)])
    fecha_final = models.DateField(null=True, blank=True, verbose_name="Fecha Final Estimada (Días Hábiles)", help_text="Calculada automáticamente basada en Fecha Inicio, Días Hábiles y País del Requisito.", editable=False)
    def __str__(self):
        return f"Detalle Matriz ID {self.matriz_id} - Req ID {self.requisito_id}"
    def save(self, *args, **kwargs):
        # --- MUEVE LA IMPORTACIÓN AQUÍ DENTRO ---
        from .utils import add_working_days

        # --- Lógica para heredar periodicidad y tiempo_validacion ---
        _loaded_requisito = None
        if hasattr(self, 'requisito') and self.requisito_id and self.requisito.pk == self.requisito_id:
            _loaded_requisito = self.requisito
        elif self.requisito_id:
            try:
                _loaded_requisito = RequisitoLegal.objects.select_related('pais').get(pk=self.requisito_id)
            except RequisitoLegal.DoesNotExist:
                logger.warning(f"RequisitoLegal ID {self.requisito_id} no encontrado para RequisitoPorEmpresaDetalle ID {self.pk}.")
        
        if _loaded_requisito:
            # Heredar periodicidad si el usuario no la especificó (es None o vacía)
            if not self.periodicidad: # Cubre None y ''
                if _loaded_requisito.periodicidad:
                    self.periodicidad = _loaded_requisito.periodicidad
            
            # Heredar tiempo_validacion si el usuario no lo especificó (es None)
            if self.tiempo_validacion is None:
                if _loaded_requisito.tiempo_validacion is not None:
                    self.tiempo_validacion = _loaded_requisito.tiempo_validacion
        # --- Fin de la lógica de herencia ---

        from .utils import add_working_days
        # -----------------------------------------
        if self.fecha_inicio and self.tiempo_validacion is not None:
            country_code = None
 
                # Intenta obtener el código de país eficientemente
            if self.requisito_id:
                    # Usar select_related en las consultas que obtienen este objeto ayuda mucho
                    # Reutilizamos _loaded_requisito si ya se cargó
                if _loaded_requisito and _loaded_requisito.pais and _loaded_requisito.pais.codigo:
                        country_code = _loaded_requisito.pais.codigo
                else:
                         logger.warning(f"No se pudo determinar el código de país para RequisitoLegal ID {self.requisito_id}. No se calculará fecha_final con festivos.")
            else:
                    logger.warning(f"Requisito no asociado a ReqDetalle ID {self.pk} al intentar calcular fecha_final.")

            if country_code:
                try:
                    current_fecha_inicio = self.fecha_inicio
                    if isinstance(current_fecha_inicio, str):
                        current_fecha_inicio = date.fromisoformat(current_fecha_inicio)

                    if isinstance(current_fecha_inicio, date) and isinstance(self.tiempo_validacion, int) and self.tiempo_validacion >= 0:
                        # Llama a la función importada localmente
                        self.fecha_final = add_working_days(current_fecha_inicio, self.tiempo_validacion, country_code)
                        logger.debug(f"Calculada fecha_final={self.fecha_final} para ReqDetalle ID {self.pk} usando {self.tiempo_validacion} días hábiles en {country_code}")
                    else:
                        logger.error(f"Tipos inválidos para calcular fecha_final en ReqDetalle ID {self.pk}: fecha_inicio={type(current_fecha_inicio)}, tiempo_validacion={type(self.tiempo_validacion)}")
                        self.fecha_final = None
                except (TypeError, ValueError) as e:
                    logger.error(f"Error calculando fecha_final con días hábiles para ReqDetalle ID {self.pk}: {e}")
                    self.fecha_final = None
            else:
                self.fecha_final = None
                logger.info(f"fecha_final establecida a None para ReqDetalle ID {self.pk} por falta de código de país.")
        else:
            self.fecha_final = None
        super().save(*args, **kwargs) # Llamar al método save original
    class Meta:
        unique_together = ('matriz', 'requisito','sede') # se agrega sede
        verbose_name = "Requisito Por Empresa Detalle"
        verbose_name_plural = "Requisitos Por Empresa Detalle"
        ordering = ['matriz', 'requisito']
        indexes = [models.Index(fields=['matriz', 'requisito'])]


# --- Modelos Plan y EjecucionMatriz ---
# ... (estos modelos no cambian, asegúrate que no importen nada de utils.py a nivel de módulo si causan problemas) ...

class Plan(models.Model):
    id = models.AutoField(primary_key=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, to_field='codigoempresa')
    requisito_empresa = models.ForeignKey(RequisitoPorEmpresaDetalle, on_delete=models.CASCADE)
    periodicidad = models.CharField(
        max_length=20,
        choices=PERIODICIDAD_CHOICES,
        blank=True, # Permitir que el campo esté vacío
        null=True   # Permitir que el campo sea NULL
    )
    fecha_inicio = models.DateField(blank=False, null=False, default=date.today) # Fecha base del requisito detalle
    # --- NUEVO CAMPO SEDE ---
    sede = models.ForeignKey(
        Sede,
        on_delete=models.CASCADE, # O SET_NULL si prefieres mantener el plan si se borra la sede
        verbose_name="Sede Aplicable",
        null=True # Permitir null temporalmente o si no se puede determinar
    )
    fecha_proximo_cumplimiento = models.DateField(blank=True, null=True, verbose_name="Fecha de Cumplimiento Programada") # Fecha específica de ESTA tarea del plan
    descripcion_periodicidad = models.TextField(blank=True, null=True, help_text="Requerido si la periodicidad es 'Otro'.")
    year = models.PositiveIntegerField(verbose_name="Año del Plan")

    # --- CAMPO MODIFICADO A MANY-TO-MANY ---
    responsables_ejecucion = models.ManyToManyField(
        settings.AUTH_USER_MODEL, # Usa la configuración de Django
        blank=True, # Puede asignarse después
        related_name='planes_asignados',
        verbose_name="Responsables de Ejecución"
    )
    # --------------------

    # El __str__ podría incluir la fecha para diferenciar instancias
    def __str__(self):
        fecha_str = self.fecha_proximo_cumplimiento.strftime('%Y-%m-%d') if self.fecha_proximo_cumplimiento else "Fecha no definida"
        sede_str = f" - Sede: {self.sede.nombre}" if self.sede else ""
        return f"Plan {self.year} - Emp ID {self.empresa_id}{sede_str} - ReqDetalle ID {self.requisito_empresa_id} - Fecha: {fecha_str}"

    def clean(self):
        super().clean()
        errors = {}
        # La validación de 'Unica' ahora no tiene sentido aquí, se maneja en la generación
        # if self.periodicidad == 'Unica' and not self.fecha_proximo_cumplimiento: errors['fecha_proximo_cumplimiento'] = ValidationError("Si la periodicidad es 'Única', debe especificar una fecha de próximo cumplimiento.", code='required')
        if self.periodicidad == 'Otro' and (not self.descripcion_periodicidad or not self.descripcion_periodicidad.strip()): errors['descripcion_periodicidad'] = ValidationError("Si la periodicidad es 'Otro', debe especificar una descripción válida.", code='required')
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Ya no calculamos fecha_proximo_cumplimiento aquí, se asigna al crear
        # self.full_clean() # Clean se puede llamar antes si es necesario
        # if self.periodicidad != 'Unica': self.fecha_proximo_cumplimiento = self.calculate_next_compliance_date()
        super().save(*args, **kwargs)

    # Eliminamos calculate_next_compliance_date ya que la lógica estará en utils
    # def calculate_next_compliance_date(self):
    #    ...

    class Meta:
        verbose_name = "Plan (Tarea)" # Cambiar nombre para reflejar que es una tarea
        verbose_name_plural = "Planes (Tareas)"
        ordering = ['empresa__nombreempresa', 'year', 'requisito_empresa', 'fecha_proximo_cumplimiento'] # Ordenar por fecha
        # Modificar unique_together para incluir sede
        unique_together = ('requisito_empresa', 'year', 'fecha_proximo_cumplimiento', 'sede')
        indexes = [
            models.Index(fields=['empresa', 'year']),
            models.Index(fields=['requisito_empresa']),
            models.Index(fields=['sede']), # Nuevo índice para sede
            models.Index(fields=['year', 'fecha_proximo_cumplimiento']), # Nuevo índice útil
            # models.Index(fields=['responsables_ejecucion']), # No se puede crear índice en ManyToManyField directamente
        ]



class EjecucionMatriz(models.Model):
    matriz = models.ForeignKey(RequisitosPorEmpresa, on_delete=models.CASCADE)
    requisito = models.ForeignKey(RequisitoLegal, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, blank=True, null=True)
    porcentaje_cumplimiento = models.IntegerField(default=0, validators=[MaxValueValidator(100), MinValueValidator(0)])
    evidencia_cumplimiento = models.FileField(upload_to='evidencia_legal/', blank=True, null=True)
    responsable = models.CharField(max_length=255, blank=True, null=True)
    notas = models.TextField(blank=True, null=True)
    fecha_ejecucion = models.DateField(blank=True, null=True)
    resultado_evaluacion = models.TextField(blank=True, null=True)
    ejecucion = models.BooleanField(default=False, verbose_name="Ejecutado")
    CONFORME_CHOICES = [('Si', 'Sí'), ('No', 'No')]
    conforme = models.CharField(max_length=2, choices=CONFORME_CHOICES, default='No')
    razon_no_conforme = models.TextField(blank=True, null=True, default=None, verbose_name="Razón No Conforme", help_text="Obligatorio si el estado es 'No conforme'.")
    def __str__(self): plan_info = f" - Plan ID {self.plan_id}" if self.plan_id else " - Sin Plan"; return f"Ejecución Matriz ID {self.matriz_id} - Req ID {self.requisito_id}{plan_info}"
    def clean(self):
        super().clean()
        errors = {}
        if self.conforme == 'No' and (not self.razon_no_conforme or not self.razon_no_conforme.strip()): errors['razon_no_conforme'] = ValidationError("Si el resultado es 'No conforme', debe especificar una razón válida.", code='required')
        if errors: raise ValidationError(errors)
    def save(self, *args, **kwargs):
        if self.conforme == 'Si': self.razon_no_conforme = None
        self.full_clean()
        if (self.porcentaje_cumplimiento > 0 or self.ejecucion) and not self.fecha_ejecucion: self.fecha_ejecucion = date.today()
        super().save(*args, **kwargs)
    class Meta: unique_together = ('matriz', 'requisito', 'plan'); verbose_name = "Ejecucion del Plan"; verbose_name_plural = "Ejecucion de los Planes"; ordering = ['matriz', 'requisito', 'plan']; indexes = [models.Index(fields=['matriz', 'requisito', 'plan'])]
