# d:\AAA_Framework\ProjectFrameworksas\users_app\forms.py

from django import forms
from django.utils.translation import gettext_lazy as _ # Para etiquetas traducibles (opcional)

class LoginForm(forms.Form):
    """
    Formulario simple para el inicio de sesión.
    """
    username = forms.CharField(
        max_length=150,
        label=_("Usuario"), # Etiqueta traducible
        widget=forms.TextInput(attrs={'placeholder': _('Ingrese su usuario')}) # Placeholder opcional
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('Ingrese su contraseña')}), # Placeholder opcional
        label=_("Contraseña") # Etiqueta traducible
    )

    # Puedes añadir más validaciones si es necesario aquí
