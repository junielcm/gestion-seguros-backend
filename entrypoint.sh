#!/bin/sh
# ==============================================================================
# entrypoint.sh - Arranque del backend en Docker
# ==============================================================================
# Se ejecuta en cada `docker compose up`. En orden:
#   1. Espera a que la base de datos esté disponible
#   2. Aplica las migraciones pendientes
#   3. Recolecta los archivos estáticos (los sirve nginx)
#   4. Opcionalmente carga los datos de prueba (idempotente)
#   5. Levanta gunicorn en primer plano (PID 1)
#
# Variables de entorno relevantes (ver .env.example):
#   DB_WAIT_TIMEOUT  - segundos de espera de la BD (0 = no esperar)
#   LOAD_DEMO_DATA   - "true" ejecuta setup_demo.py en cada arranque
#   GUNICORN_WORKERS - número de workers
# ==============================================================================

set -e

DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"

echo "==> [1/5] Verificando base de datos..."
if [ "${DB_WAIT_TIMEOUT}" -gt 0 ] && [ -n "${DB_HOST}" ]; then
    elapsed=0
    until python -c "
import os, socket, sys
host, port = os.environ['DB_HOST'], os.environ.get('DB_PORT', '5432')
try:
    socket.create_connection((host, int(port)), timeout=3).close()
except OSError:
    sys.exit(1)
" 2>/dev/null; do
        elapsed=$((elapsed + 1))
        if [ "${elapsed}" -ge "${DB_WAIT_TIMEOUT}" ]; then
            echo "    ERROR: '${DB_HOST}:${DB_PORT}' no respondió en ${DB_WAIT_TIMEOUT}s." >&2
            exit 1
        fi
        echo "    Esperando a ${DB_HOST}:${DB_PORT}... (${elapsed}s)"
        sleep 1
    done
    echo "    Base de datos disponible."
else
    echo "    Sin espera requerida (SQLite o DB_WAIT_TIMEOUT=0)."
fi

echo "==> [2/5] Aplicando migraciones..."
python manage.py migrate --noinput

echo "==> [3/5] Recolectando archivos estáticos..."
python manage.py collectstatic --noinput --clear

# setup_demo.py es idempotente: usa get_or_create en cada modelo, así que
# volver a ejecutarlo no duplica clínicas, usuarios ni la póliza.
if [ "${LOAD_DEMO_DATA}" = "true" ]; then
    echo "==> [4/5] Cargando datos de prueba (setup_demo.py)..."
    python setup_demo.py
else
    echo "==> [4/5] Carga de datos de prueba omitida (LOAD_DEMO_DATA!=true)."
fi

echo "==> [5/5] Iniciando gunicorn en 0.0.0.0:8000 (${GUNICORN_WORKERS} workers)..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
