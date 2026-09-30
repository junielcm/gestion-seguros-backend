# ==============================================================================
# ARCHIVO: config/settings.py
# DESCRIPCIÓN: Configuración central del proyecto (base de datos, apps,
#              REST Framework, JWT y CORS).
#
# Todas las variables leen su valor de `os.environ` con un valor por defecto
# pensado para el desarrollo local, de modo que el proyecto arranca sin
# configurar nada. En DockerCompose esos valores llegan desde el `environment:`
# del servicio (ver ../docker-compose.yml).
# ==============================================================================

import os
from pathlib import Path
from datetime import timedelta

# Ruta base del proyecto: sirve para construir rutas relativas (media, static...)
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga opcional del archivo .env (desarrollo local).
#
# Django no lee archivos .env por sí solo. Si 'python-dotenv' está instalado,
# este bloque lo carga; si no lo está, el proyecto sigue funcionando con los
# valores por defecto de más abajo. En Docker no hace falta: Compose inyecta
# las variables directamente en el entorno del contenedor.
#
# Para usarlo en local:  pip install python-dotenv
# Las variables ya presentes en el entorno real tienen prioridad sobre el
# archivo, así que un contenedor nunca se ve afectado por un .env local.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass


def env_bool(name, default=False):
    """Convierte 'true'/'1'/'yes' en booleano. Cualquier otro valor es False."""
    return os.environ.get(name, str(default)).strip().lower() in (
        'true', '1', 'yes', 'on',
    )


def env_list(name, default=None):
    """Convierte 'a,b,c' en ['a', 'b', 'c']."""
    raw = os.environ.get(name)
    if not raw:
        return list(default) if default else []
    return [item.strip() for item in raw.split(',') if item.strip()]


# Clave secreta usada por Django para firmar sesiones y tokens.
# En producción se lee de la variable de entorno SECRET_KEY.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-h04ba8#_wjw)-u6_*_g*w%mn#w3a%kj6_7hr+z2o&8+x%3th@f'
)

# DEBUG=True muestra errores detallados en pantalla (solo para desarrollo).
# Docker lo arranca en False; el desarrollo local mantiene el True por defecto.
DEBUG = env_bool('DEBUG', True)

# '*' es útil en desarrollo, pero en producción hay que fijar los dominios:
#   ALLOWED_HOSTS=api.midominio.com,app.midominio.com
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['*'])

# Detrás de un proxy inverso (nginx en Docker) Django debe confiar en los
# headers X-Forwarded-* para saber el esquema y la IP real del cliente.
if env_bool('USE_X_FORWARDED_HOST', False):
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ------------------------------------------------------------------------------
# HTTPS
# ------------------------------------------------------------------------------
# Todo desactivado por defecto porque el stack sirve HTTP plano en el puerto
# 8080. Cuando lo pongas detrás de un terminador TLS (Traefik, Caddy, un
# balanceador...), activa estas variables en el .env:
#
#   SECURE_SSL_REDIRECT=True
#   SECURE_HSTS_SECONDS=31536000
#   SESSION_COOKIE_SECURE=True
#   CSRF_COOKIE_SECURE=True
#
# Ojo: activar HSTS sin HTTPS real deja el dominio inaccesible durante el
# periodo configurado. Léete la documentación de Django antes de hacerlo.
# ------------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', False)


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
# STATIC_ROOT es el destino de `collectstatic`; en Docker esa carpeta es un
# volumen que nginx monta en modo lectura para servir /static/.
# ------------------------------------------------------------------------------
# Debe empezar por '/': el admin de Django genera las URLs de sus CSS/JS a
# partir de este valor, y una ruta relativa ('static/') se resolvería contra
# la página actual (/admin/static/...) y devolvería 404.
STATIC_URL = os.environ.get('STATIC_URL', '/static/')

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / 'media'))

STATIC_ROOT = Path(os.environ.get('STATIC_ROOT', BASE_DIR / 'staticfiles'))


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
# En Docker el frontend llama a /api/v1/ del mismo origen (nginx hace de proxy),
# así que CORS no es necesario; se mantiene abierto por compatibilidad con el
# desarrollo local, donde Vite corre en el 5173 y Django en el 8000.
# Para producción, define:
#   CORS_ALLOWED_ORIGINS=https://app.midominio.com
# ------------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL_ORIGINS', True)

CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')
if CORS_ALLOWED_ORIGINS:
    # Si se define una lista explícita, tiene prioridad sobre el modo abierto.
    CORS_ALLOW_ALL_ORIGINS = False

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