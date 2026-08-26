# ==============================================================================
# ARCHIVO: config/urls.py
# DESCRIPCIÓN: Enrutador principal del proyecto 'gestion-seguros'. Integra los 
#              endpoints de la API (v1), el panel de admin y la autenticación JWT.
# ==============================================================================

import os
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Importación de vistas de JWT (SimpleJWT)
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from claims.serializers import CustomTokenObtainPairSerializer
from claims.views import RegistroClienteView


# Vista personalizada del token para incluir información del rol de usuario
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


urlpatterns = [
    # Panel Administrativo de Django
    path('admin/', admin.site.urls),
    
    # Endpoints de la API REST v1
    path('api/v1/', include('claims.urls')),

    # Endpoints de Autenticación JWT con Serializador de Roles
    path('api/v1/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Registro público: toda cuenta creada aquí nace con rol 'cliente'
    path('api/v1/register/', RegistroClienteView.as_view(), name='register'),
]

# Servir archivos multimedia (comprobantes de pago/fotos) durante desarrollo local
if settings.DEBUG:
    # Crear el directorio MEDIA_ROOT si aún no existe en el proyecto
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)