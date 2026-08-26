# ==============================================================================
# ARCHIVO: config/settings.py
# DESCRIPCIÓN: Configuración central del proyecto (base de datos, apps,
#              REST Framework, JWT y CORS).
#
# NOTA PARA PRODUCCIÓN: SECRET_KEY, DEBUG y las credenciales de la base de
# datos están fijados aquí para simplificar el desarrollo local. En un
# despliegue real deberían leerse de variables de entorno (ej. con python-dotenv).
# ==============================================================================

import os
from pathlib import Path
from datetime import timedelta

# Ruta base del proyecto: sirve para construir rutas relativas (media, static...)
BASE_DIR = Path(__file__).resolve().parent.parent

# Clave secreta usada por Django para firmar sesiones y tokens.
# En producción se lee de la variable de entorno SECRET_KEY.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-h04ba8#_wjw)-u6_*_g*w%mn#w3a%kj6_7hr+z2o&8+x%3th@f'
)

# DEBUG=True muestra errores detallados en pantalla (solo para desarrollo)
DEBUG = True

ALLOWED_HOSTS = ['*']  # Permitir solicitudes locales de prueba


# ------------------------------------------------------------------------------
# APLICACIONES INSTALADAS
# ------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Apps nativas de Django (admin, autenticación, sesiones, etc.)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Librerías de terceros:
    #   - rest_framework: construye la API REST
    #   - rest_framework_simplejwt: autenticación por tokens JWT
    #   - django_filters: filtrado de resultados en los endpoints (?clinic=1, etc.)
    #   - corsheaders: permite que el frontend (otro dominio/puerto) consuma la API
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',

    # Apps del proyecto
    'claims',
]

# Middlewares: capas que procesan toda petición HTTP antes/después de las vistas.
# CORS va primero para añadir sus cabeceras incluso a respuestas de error.
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Debe ir lo más arriba posible
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Módulo donde Django busca las rutas principales
ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ------------------------------------------------------------------------------
# BASE DE DATOS
# Por defecto usa SQLite (sin configuración, ideal para portafolio/demo).
# Para usar PostgreSQL, definir DB_ENGINE en el archivo .env:
#   DB_ENGINE=django.db.backends.postgresql
# ------------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.environ.get('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
    }
}


# ------------------------------------------------------------------------------
# VALIDACIÓN DE CONTRASEÑAS
# Al ser un proyecto DEMO/portafolio solo se exige un largo mínimo de 6
# caracteres (así claves simples como '123456' funcionan en el registro).
# En producción convendría restaurar los validadores estrictos de Django.
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 6}},
]


# ------------------------------------------------------------------------------
# INTERNACIONALIZACIÓN: español (Venezuela) y zona horaria de Caracas
# ------------------------------------------------------------------------------
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True


# ------------------------------------------------------------------------------
# ARCHIVOS ESTÁTICOS Y MULTIMEDIA
# MEDIA guarda los archivos que suben los usuarios (comprobantes de pago,
# récipes médicos). STATIC es para archivos del propio proyecto.
# ------------------------------------------------------------------------------
STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ------------------------------------------------------------------------------
# REST FRAMEWORK: configuración global de la API
# ------------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Exigir autenticación y token Bearer/JWT globalmente
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    # Por defecto TODOS los endpoints exigen estar logueado
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    # Clases por defecto para el filtrado global de los ViewSets
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # Formato por defecto de respuestas y soporte de paginación opcional
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}


# ------------------------------------------------------------------------------
# CORS: permite que el frontend (React/Vue en otro puerto) consuma esta API.
# En desarrollo se permite cualquier origen; en producción conviene limitarlo
# a los dominios reales del frontend.
# ------------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# ------------------------------------------------------------------------------
# SIMPLE JWT: duración de los tokens de autenticación
# El access token (que viaja en cada petición) dura 24h y el refresh token
# (para renovarlo sin volver a loguearse) dura 7 días.
# ------------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),  # Dura 24 horas completas
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}