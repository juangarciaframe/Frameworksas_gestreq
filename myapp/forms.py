# myapp/forms.py

from django import forms
from .models import RequisitoPorEmpresaDetalle, RequisitoLegal, RequisitosPorEmpresa, Empresa, EjecucionMatriz, Plan # Añadir EjecucionMatriz y Plan
from django.contrib.auth.forms import AuthenticationForm
from semantic_forms.forms import SemanticForm # Si usas semantic-forms para estilo
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)


# --- Tu formulario de login existente ---
class CustomAdminLoginForm(AuthenticationForm, SemanticForm):
    # ... (código existente) ...
    pass
# --- Fin formulario de login ---


# --- Formulario para el detalle (lo usamos en el inline) ---
class RequisitoPorEmpresaDetalleForm(forms.ModelForm):
    # ... (código existente) ...
    pass
# --- Fin formulario detalle ---


# --- NUEVO FORMULARIO PARA LA VISTA PERSONALIZADA ---
class CreateMatrixWithRequirementsForm(forms.ModelForm):
    """
    Formulario para la vista personalizada 'create_with_requirements_view'.
    Captura los datos básicos de RequisitosPorEmpresa.
    """
    class Meta:
        model = RequisitosPorEmpresa
        fields = ['empresa', 'nombre', 'descripcion']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}), # Hacer el textarea más pequeño
        }

    def __init__(self, *args, **kwargs):
        # Extraer el usuario que pasamos desde la vista en admin.py
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filtrar el campo 'empresa' basado en el usuario logueado
        if user and not user.is_superuser:
            # Intenta obtener la empresa seleccionada en la sesión (si usas el middleware)
            selected_company = getattr(user, 'selected_company', None) # Asume que el middleware la añade al user

            if selected_company:
                 # Mostrar solo la empresa seleccionada
                 self.fields['empresa'].queryset = Empresa.objects.filter(pk=selected_company.pk)
                 # Opcional: Establecerla como valor inicial y hacerla readonly si solo puede ser esa
                 # self.initial['empresa'] = selected_company
                 # self.fields['empresa'].disabled = True
            else:
                # Si no hay empresa seleccionada, intenta con las asociadas directamente al usuario
                try:
                    # Asume que CustomUser tiene una relación M2M llamada 'Empresa'
                    user_companies = user.Empresa.all()
                    if user_companies.exists():
                        self.fields['empresa'].queryset = user_companies
                    else:
                        # Si no tiene empresas asociadas, no mostrar ninguna
                        self.fields['empresa'].queryset = Empresa.objects.none()
                except AttributeError:
                     # Si el usuario no tiene la relación 'Empresa', no mostrar ninguna
                     self.fields['empresa'].queryset = Empresa.objects.none()
        elif not user:
             # Si por alguna razón no se pasó el usuario, no mostrar empresas
             self.fields['empresa'].queryset = Empresa.objects.none()
        # Para el superusuario, se muestra el queryset por defecto (todas las empresas)

# --- FIN NUEVO FORMULARIO ---


class EjecucionMatrizDirectForm(forms.ModelForm):
    class Meta:
        model = EjecucionMatriz
        fields = [
            'plan', 'notas', 'porcentaje_cumplimiento', # Cambiado 'descripcion_cumplimiento' a 'notas'
            'conforme', 'razon_no_conforme', 'evidencia_cumplimiento', 'ejecucion'
        ]
        widgets = {
            'notas': forms.Textarea(attrs={'rows': 3}), # Cambiado aquí también
            'razon_no_conforme': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

        if company:
            self.fields['plan'].queryset = Plan.objects.filter(empresa=company).select_related(
                'requisito_empresa__requisito', 'sede'
            ).order_by('-year', 'requisito_empresa__requisito__tema')
        else: # Superusuario o sin compañía seleccionada
            self.fields['plan'].queryset = Plan.objects.all().select_related(
                'requisito_empresa__requisito', 'sede'
            ).order_by('-year', 'requisito_empresa__requisito__tema')

        is_new_with_initial_plan = self.initial.get('plan') and not self.instance.pk
        is_editing = self.instance and self.instance.pk

        if is_new_with_initial_plan or is_editing:
            if 'plan' in self.fields:
                self.fields['plan'].disabled = True
        
        self.fields['porcentaje_cumplimiento'].label = "Porcentaje de Cumplimiento (%)"
        self.fields['ejecucion'].label = "Marcar como Ejecutado (Finalizado al 100%)"
        self.fields['evidencia_cumplimiento'].label = "Adjuntar Evidencia (Opcional)"

    def clean_porcentaje_cumplimiento(self):
        porcentaje = self.cleaned_data.get('porcentaje_cumplimiento')
        if porcentaje is not None and not (0 <= porcentaje <= 100):
            raise forms.ValidationError("El porcentaje debe estar entre 0 y 100.")
        return porcentaje

    def clean(self):
        cleaned_data = super().clean()
        conforme = cleaned_data.get('conforme')
        razon_no_conforme = cleaned_data.get('razon_no_conforme')
        
        if conforme == 'No' and not razon_no_conforme:
            self.add_error('razon_no_conforme', "Debe especificar la razón si la ejecución no es conforme.")
            
        return cleaned_data
# --- FIN NUEVO FORMULARIO ---
