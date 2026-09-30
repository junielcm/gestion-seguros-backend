# ==============================================================================
# Dockerfile - Backend Django REST Framework
# ==============================================================================
# Imagen de una sola etapa: python slim + dependencias + código.
#
# Rutas que se montan como volúmenes (ver docker-compose.yml):
#   /app/data       -> base de datos SQLite (db.sqlite3)
#   /app/media      -> archivos subidos por usuarios (comprobantes, órdenes)
#   /app/staticfiles-> estáticos de collectstatic, servidos por nginx
#
# Los permisos de esas carpetas se fijan en la imagen para que Docker las
# herede al crear los volúmenes y el proceso no-root pueda escribir.
# ==============================================================================

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ------------------------------------------------------------------------------
# Dependencias del sistema
# ------------------------------------------------------------------------------
# build-essential + libpq-dev: psycopg2 lo compila en vez de usar wheel
# (la imagen oficial de Python es "slim" y no trae toolchain).
# curl: lo usa el HEALTHCHECK para comprobar /admin/login/.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# Dependencias de Python (capa cacheada: solo se reinstala si cambia el archivo)
# ------------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
# Código de la aplicación
# ------------------------------------------------------------------------------
COPY . .

# ------------------------------------------------------------------------------
# Usuario sin privilegios + directorios de los volúmenes
# ------------------------------------------------------------------------------
RUN chmod +x /app/entrypoint.sh \
    && useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data /app/media /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/admin/login/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
