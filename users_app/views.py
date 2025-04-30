# d:\AAA_Framework\ProjectFrameworksas\users_app\views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import UserCompany
# Asegúrate de que LoginForm esté definido en users_app/forms.py
from .forms import LoginForm
import logging

logger = logging.getLogger(__name__)

# Define el namespace de la app para usar en redirecciones y URLs
app_name = 'users_app'

def login_view(request):
    """
    Vista de login personalizada que maneja la autenticación y la lógica
    de selección de empresa basada en las asignaciones del usuario.
    """
    error_message = None
    # Si el usuario ya está autenticado y accede a /login/, redirigir a home
    if request.user.is_authenticated:
        # --- CORRECCIÓN AQUÍ ---
        return redirect('myapp:home')
        # -----------------------

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                logger.info(f"Usuario {user.username} autenticado exitosamente.")

                # --- LÓGICA PERSONALIZADA PARA EMPRESAS ---
                user_companies = UserCompany.objects.filter(user=user)
                company_count = user_companies.count()

                # --- DEBUGGING ---
                print(f"DEBUG (login_view): Usuario '{user.username}' tiene {company_count} empresas asociadas.")
                # -----------------

                if company_count == 1:
                    # Si tiene solo una empresa, la seleccionamos automáticamente
                    selected_company = user_companies.first().company
                    request.session['selected_company_id'] = selected_company.codigoempresa
                    logger.info(f"Login: Auto-seleccionada empresa {selected_company.codigoempresa} para {user.username}")
                    print(f"DEBUG (login_view): Auto-seleccionada empresa {selected_company.codigoempresa}. Redirigiendo a home.") # DEBUG
                    # --- CORRECCIÓN AQUÍ ---
                    return redirect('myapp:home')
                    # -----------------------
                elif company_count > 1:
                    # Si tiene más de una, redirigimos a la selección
                    logger.info(f"Login: Usuario {user.username} tiene {company_count} empresas. Redirigiendo a selección.")
                    print(f"DEBUG (login_view): Redirigiendo a select_company para '{user.username}'...") # DEBUG
                    # Limpiamos cualquier selección previa por si acaso
                    if 'selected_company_id' in request.session:
                        del request.session['selected_company_id']
                    return redirect('users_app:select_company') # Redirige a la vista de selección
                else: # company_count == 0
                    # Si no tiene empresas asignadas
                    logger.info(f"Login: Usuario {user.username} no tiene empresas asignadas.")
                    print(f"DEBUG (login_view): Usuario sin empresas. Redirigiendo a home.") # DEBUG
                    if 'selected_company_id' in request.session:
                        del request.session['selected_company_id']
                    # --- CORRECCIÓN AQUÍ ---
                    return redirect('myapp:home')
                    # -----------------------
                # --- FIN LÓGICA PERSONALIZADA ---
            else:
                # Autenticación fallida
                error_message = "Usuario o contraseña incorrectos."
                logger.warning(f"Login: Falló autenticación para {username}")
                print(f"DEBUG (login_view): Falló autenticación para {username}") # DEBUG
        else:
            # Formulario inválido
            error_message = "Por favor, corrija los errores en el formulario."
            logger.warning(f"Login: Formulario inválido recibido.")
            print(f"DEBUG (login_view): Formulario inválido.") # DEBUG

    else: # Método GET
        form = LoginForm()

    # Renderizar la plantilla de login
    # Asegúrate que la ruta 'users_app/login.html' sea correcta
    return render(request, 'users_app/login.html', {'form': form, 'error_message': error_message})

@login_required
def select_company(request):
    """
    Vista para que los usuarios con múltiples empresas seleccionen
    con cuál desean trabajar.
    """
    user = request.user
    user_companies = UserCompany.objects.filter(user=user)
    # Prepara la lista de diccionarios para la plantilla
    companies = [{'id': uc.company.codigoempresa, 'name': uc.company.nombreempresa}
                 for uc in user_companies]
    error = None

    if request.method == 'POST':
        company_id = request.POST.get('company') # 'company' es el name del input radio/select
        if company_id:
            # Validación extra (seguridad): Asegurarse que el ID enviado pertenece al usuario
            if any(c['id'] == company_id for c in companies):
                request.session['selected_company_id'] = company_id
                logger.info(f"Select Company: Empresa {company_id} seleccionada para {user.username}")
                print(f"DEBUG (select_company): Empresa {company_id} seleccionada. Redirigiendo a home.") # DEBUG
                # --- CORRECCIÓN AQUÍ ---
                return redirect('myapp:home')
                # -----------------------
            else:
                error = "Empresa inválida seleccionada."
                logger.warning(f"Select Company: Intento de seleccionar empresa inválida {company_id} por {user.username}")
                print(f"DEBUG (select_company): Intento de seleccionar empresa inválida {company_id}.") # DEBUG
        else:
            error = 'Debe seleccionar una empresa.'
            print(f"DEBUG (select_company): No se seleccionó empresa en POST.") # DEBUG

    # Contexto para la plantilla (GET o POST con error)
    context = {
        'companies': companies,
        'selected_company_id': request.session.get('selected_company_id'), # Para marcar la opción actual
        'error': error
    }
    # Asegúrate que la ruta del template 'users_app/select_company.html' sea correcta
    return render(request, 'users_app/select_company.html', context)

def logout_view(request):
    """
    Vista para cerrar la sesión del usuario, limpiando la empresa seleccionada.
    """
    user_display = str(request.user) if request.user.is_authenticated else "Usuario anónimo"
    # Limpiar la sesión antes de desloguear
    if 'selected_company_id' in request.session:
        logger.info(f"Logout: Limpiando selected_company_id para {user_display}")
        print(f"DEBUG (logout_view): Limpiando selected_company_id.") # DEBUG
        del request.session['selected_company_id']
    logout(request)
    logger.info(f"Logout: Sesión cerrada para {user_display}")
    print(f"DEBUG (logout_view): Sesión cerrada. Redirigiendo a login.") # DEBUG
    # Redirigir a la página de login después de cerrar sesión
    return redirect('users_app:login')
