# myapp/forms.py

from django import forms
# Asegúrate de importar los modelos necesarios
from .models import RequisitoPorEmpresaDetalle, RequisitoLegal, RequisitosPorEmpresa, Empresa
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


