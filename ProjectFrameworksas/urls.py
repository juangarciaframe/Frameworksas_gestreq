# ProjectFrameworksas/urls.py
from django.contrib import admin
from django.urls import path, include  # make sure include is imported
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog # <-- Añade esta importación

urlpatterns = [
    path("admin/", admin.site.urls), # The admin urls are the first to be checked
    path("select2/", include("django_select2.urls")),
    path("", include("myapp.urls")),  
    path("", include("users_app.urls")),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'), # <-- Añade esta línea
   
]
# This lines are for media files, you may already have it.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
