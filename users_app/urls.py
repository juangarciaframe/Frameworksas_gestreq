# d:\AAA_Framework\ProjectFrameworksas\users_app\urls.py

from django.urls import path
# Importa solo tus vistas locales
from . import views
# QUITA la importación de LoginView si ya no la usas en otras partes
# from django.contrib.auth.views import LoginView

app_name = 'users_app'

urlpatterns = [
    # Apunta a tu vista personalizada 'views.login_view'
    # Añade una barra al final de 'login/' por convención
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view , name='logout'),
    path('select-company/', views.select_company, name='select_company'),
]



