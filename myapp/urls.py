# myapp/urls.py
from django.urls import include, path
from . import views
from django.conf.urls import handler403 , handler404 , handler500 ,handler400
from .views import RequisitoLegalSelect2View
# Importar create_with_requirements_view desde admin.py (si sigue allí)
from .admin import create_with_requirements_view



app_name = 'myapp'  # This is the crucial line we're adding!

urlpatterns = [
    path('', views.home, name='home'),
    path('error/', views.mi_pagina_de_error, name='mi_pagina_de_error'),
    path(
        'select2/requisito_legal/', # La ruta que manejará las peticiones AJAX
        RequisitoLegalSelect2View.as_view(), # La vista que creamos
        name='select2_requisito_legal' # El nombre que busca reverse_lazy
    ),
    path(
        'admin-create-matrix/', # Una ruta clara fuera del admin estándar
        create_with_requirements_view,
        name='create_matrix_with_reqs' # Nombre simple dentro del namespace 'myapp'
    ), 
    path(
        'plan-gantt/', # Ruta para la vista Gantt
        views.plan_gantt_view, # Ahora se importa desde views
        name='plan_gantt_chart' # Nombre para usar en {% url %}
    ),
    path(
        'dashboard/',
        views.dashboard_view,
        name='dashboard'
    ),
    path( # Nueva URL para el formulario directo de ejecución
        'ejecucion-matriz/form/', 
        views.ejecucion_matriz_direct_form_view, 
        name='ejecucion_matriz_direct_form'
    ),
]
