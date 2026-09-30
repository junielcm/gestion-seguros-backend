# Gestión de Seguros - API Backend

Sistema completo de gestión de seguros médicos construido con Django REST Framework. Administra pólizas, reclamos, clínicas afiliadas, médicos, y todo el flujo operativo de una aseguradora.

---

## Descripción General

Esta API REST permite gestionar el ciclo de vida completo de una póliza de seguro médico: desde la emisión y pagos, pasando por la solicitud de servicios médicos en clínicas afiliadas, hasta el reclamo (siniestro) y su resolución. El sistema controla el saldo de cobertura, verifica pagos, audita solicitudes y registra la atención médica realizada.

### Flujo Principal del Negocio

```
Cliente solicita servicio → Recepción registra cita → Analista autoriza/rechaza
→ Médico atiende y registra consulta → Se genera siniestro → Se descuenta saldo de póliza
```

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Framework | Django 6.1 + Django REST Framework 3.18 |
| Base de datos | PostgreSQL |
| Autenticación | JWT (SimpleJWT) |
| Filtrado | django-filter |
| CORS | django-cors-headers |
| Moneda | USD (Dólares Americanos) |
| Zona horaria | America/Caracas (UTC-4) |
| Licencia | MIT |

---

## Decisiones de Diseño

### ¿Por qué Django?

Django fue elegido por su madurez ecosistema completo para desarrollo web. El ORM potente y el panel de administración integrado aceleran el desarrollo. Django REST Framework es el estándar de la industria para APIs REST en Python, con serializadores, viewsets, filtrado y paginación listos para usar.

### ¿Por qué JWT (JSON Web Tokens)?

JWT es stateless: el servidor no almacena sesiones, cada petición se valida por sí misma. Esto lo hace escalable (puedes agregar servidores sin compartir sesiones) y ideal para APIs que consumen múltiples clientes (web, móvil, terceros). SimpleJWT maneja automáticamente la renovación de tokens.

### ¿Por qué PostgreSQL?

PostgreSQL es el estándar en entornos productivos por su integridad referencial, soporte avanzado de tipos de datos y robustez en transacciones. A diferencia de SQLite, maneja concurrencia real y es lo que se usa en producción con Django.

### ¿Por qué RBAC con Grupos de Django?

En lugar de instalar una librería externa de permisos, se aprovechó el sistema de grupos nativo de Django. Cada grupo representa un rol, y los permisos personalizados en `permissions.py` validan el acceso. Esto mantiene el proyecto sin dependencias innecesarias y facilita el mantenimiento.

### ¿Por qué el saldo de póliza incluye siniestros pendientes?

En el mundo real, las aseguradoras bloquean el saldo mientras un reclamo está en proceso. Si un cliente tiene $1000 de cobertura y un siniestro por $500 en revisión, no debería poder gastar los $1000 completos en otra atención. Por eso `used_amount` suma siniestros en estados `APPROVED`, `IN_REVIEW` y `PENDING`.

### Patrón Singleton para ConfiguracionFinanciera

Solo existe una configuración financiera en el sistema (fondo de capital y porcentaje de pago a clínicas). El método `obtener()` garantiza que siempre se trabaja con el mismo registro, creándolo con valores por defecto si no existe.

### Señal post_save para InsuredProfile

Al registrar un usuario nuevo, se crea automáticamente su perfil de asegurado. Esto evita inconsistencias: no puede existir un usuario sin perfil asociado, y el script de seed reutiliza el perfil creado por la señal en lugar de crear uno duplicado.

### Variables de Entorno

Las credenciales sensibles (base de datos, secret key) se leen de variables de entorno con valores por defecto para desarrollo local. Esto permite ejecutar el proyecto sin configuración adicional en desarrollo, mientras mantiene las credenciales fuera del código en producción.

---

## Estructura del Proyecto

```
backend/
├── config/                    # Configuración central de Django
│   ├── settings.py            # Base de datos, apps, JWT, CORS
│   ├── urls.py                # Rutas raíz del proyecto
│   ├── asgi.py / wsgi.py      # Puntos de entrada del servidor
│
├── claims/                    # App principal (toda la lógica de negocio)
│   ├── models.py              # 11 modelos de datos
│   ├── views.py               # ViewSets y endpoints
│   ├── serializers.py         # Serializadores DRF
│   ├── permissions.py         # Control de acceso por rol (RBAC)
│   ├── mixins.py              # Mixins reutilizables (filtrado por rol)
│   ├── urls.py                # Rutas de la API (Router DRF)
│   ├── admin.py               # Registro en panel de administración
│   └── migrations/            # Migraciones de base de datos
│
├── seed_test_users.py         # Script: crea usuarios de prueba
├── seed_clinics.py            # Script: crea clínicas de ejemplo
├── setup_demo.py              # Script: prepara todo (migraciones + datos demo)
├── media/                     # Archivos subidos (comprobantes, récipes)
├── manage.py                  # Comando de gestión de Django
├── Dockerfile                 # Imagen del backend (gunicorn, usuario no-root)
├── .dockerignore              # Exclusiones del contexto de build
├── entrypoint.sh              # Arranque: migrate + collectstatic + demo + gunicorn
├── requirements.txt           # Dependencias (incluye gunicorn)
└── .env.example               # Plantilla de variables de entorno
```

---

## Modelos de Datos

### 1. DoctorProfile (Perfil de Médico)
Almacena la información profesional de cada médico especialista. Se vincula opcionalmente a un usuario del sistema para autenticación.

| Campo | Tipo | Descripción |
|---|---|---|
| user | OneToOne → User | Usuario asociado (para login) |
| first_name / last_name | CharField | Nombre completo |
| specialty | CharField | Especialidad médica |
| license_number | CharField (unique) | Nº de colegiado o licencia MPPS |
| is_active | BooleanField | Médico activo en el sistema |

### 2. InsuredProfile (Perfil de Asegurado)
Datos del titular de la póliza. Se crea automáticamente cuando se registra un usuario nuevo (señal `post_save`).

| Campo | Tipo | Descripción |
|---|---|---|
| user | OneToOne → User | Usuario asociado |
| national_id | CharField (unique) | Cédula o DNI |
| email | EmailField | Correo electrónico |
| is_active | BooleanField | Asegurado activo |

### 3. Clinic (Clínica / Centro Médico)
Centros de atención médica afiliados a la aseguradora.

| Campo | Tipo | Descripción |
|---|---|---|
| name | CharField | Nombre del centro médico |
| rif | CharField (unique) | RIF o identificación fiscal |
| address / phone | TextField / CharField | Datos de contacto |
| total_billed | Property | Suma de siniestros aprobados en esta clínica |

### 4. MedicalService (Catálogo Global de Servicios)
Catálogo maestro de servicios médicos (Consulta General, Laboratorio, Rayos X, etc.). Es la base sobre la que cada clínica define su precio.

### 5. ClinicBaremo (Tarifario por Clínica)
Precio de un servicio del catálogo global en una clínica específica. **Todos los precios están en USD.**

| Campo | Tipo | Descripción |
|---|---|---|
| clinic | FK → Clinic | Clínica |
| service | FK → MedicalService | Servicio del catálogo |
| price | DecimalField | Precio en USD para esta clínica |

### 6. ClinicService (Servicio Legacy de Clínica)
Catálogo de servicios con precio propio por clínica (modelo anterior al baremo unificado). Se mantiene por compatibilidad.

### 7. ClinicStaffProfile (Personal de Recepción)
Vincula un usuario con rol de recepción a una clínica específica. Garantiza que cada recepción solo vea los datos de su clínica.

### 8. InsurancePolicy (Póliza de Seguro)
Contrato de cobertura del asegurado. Calcula automáticamente el saldo consumido y el disponible.

| Campo | Tipo | Descripción |
|---|---|---|
| policy_number | CharField (unique) | Número de póliza (ej: POL-2026-001) |
| insured | FK → InsuredProfile | Asegurado titular |
| policy_type | Choice | HEALTH, VEHICLE, LIFE, PROPERTY |
| coverage_amount | DecimalField | Monto total de cobertura ($) |
| start_date / end_date | DateField | Vigencia de la póliza |
| status | Choice | ACTIVE, EXPIRED, SUSPENDED |
| **used_amount** | **Property** | **Suma de siniestros APROBADOS + EN REVISIÓN + PENDIENTES** |
| **remaining_balance** | **Property** | **coverage_amount - used_amount** |

**Regla clave:** El cálculo de `used_amount` incluye siniestros en estados `APPROVED`, `IN_REVIEW` y `PENDING` para evitar sobre-consumo mientras un reclamo está en proceso.

### 9. PolicyPayment (Pago de Póliza)
Registro de pagos realizados por el cliente para adquirir o renovar su póliza. Incluye verificación con comprobante adjunto.

| Campo | Tipo | Descripción |
|---|---|---|
| policy | FK → InsurancePolicy | Póliza asociada |
| amount | DecimalField | Monto pagado ($) |
| payment_reference | CharField | Número de referencia del pago |
| receipt_file | FileField | Comprobante (imagen o PDF) |
| status | Choice | PENDING, APPROVED, REJECTED |

### 10. ConfiguracionFinanciera (Configuración Financiera)
Registro único (singleton) con los parámetros financieros de la aseguradora.

| Campo | Tipo | Descripción |
|---|---|---|
| fondo_capital | DecimalField | Capital con el que opera la aseguradora |
| pct_pago_clinica | DecimalField | Porcentaje que la aseguradora paga a la clínica (ej: 80%) |
| **pct_retencion_aseguradora** | **Property** | **100% - pct_pago_clinica** |

**Ejemplo:** Si el baremo dice $100 y `pct_pago_clinica` = 80%, la clínica recibe $80 y la aseguradora retiene $20.

### 11. Claim (Siniestro / Reclamo)
Solicitud de atención generada por recepción o el cliente. Vincula la póliza, la clínica, el servicio requerido y el médico asignado.

| Campo | Tipo | Descripción |
|---|---|---|
| claim_number | CharField (unique) | Código único del reclamo |
| policy | FK → InsurancePolicy | Póliza que cubre el siniestro |
| clinic | FK → Clinic | Clínica que atiende |
| baremo | FK → ClinicBaremo | Baremo aplicado (tarifa) |
| assigned_doctor | FK → DoctorProfile | Médico asignado |
| requested_amount | DecimalField | Monto reclamado ($) |
| status | Choice | PENDING, IN_REVIEW, APPROVED, REJECTED |

### 12. MedicalConsultation (Consulta Médica)
Ficha médica completada por el médico asignado. Registra signos vitales, diagnóstico y costo del servicio.

| Campo | Tipo | Descripción |
|---|---|---|
| claim | OneToOne → Claim | Siniestro asociado |
| doctor | FK → DoctorProfile | Médico tratante |
| high_pressure / low_pressure | DecimalField | Presión arterial (mmHg) |
| temperature | DecimalField | Temperatura (°C) |
| weight / height | DecimalField | Peso (kg) / Altura (m) |
| diagnosis_report | TextField | Informe diagnóstico y tratamiento |
| service_cost | DecimalField | Costo del servicio ($) |

### 13. MedicalAppointmentRequest (Solicitud de Cita / Servicio)
Solicitudes de citas o servicios médicos gestionadas por la recepción y auditadas por el analista de seguros.

| Campo | Tipo | Descripción |
|---|---|---|
| insured | FK → InsuredProfile | Asegurado que solicita |
| policy | FK → InsurancePolicy | Póliza a utilizar |
| clinic | FK → Clinic | Clínica destino |
| service_type | Choice | CONSULTATION, XRAY, LAB, OTHER |
| status | Choice | PENDING, SCHEDULED, REJECTED, COMPLETED, CANCELLED |
| scheduled_date | DateTimeField | Fecha/hora de la cita |
| assigned_doctor | FK → DoctorProfile | Médico asignado por recepción |

---

## Sistema de Permisos (RBAC)

El sistema implementa Control de Acceso Basado en Roles con 7 roles definidos:

| Grupo (rol) | Permisos Principales |
|---|---|
| `admin` | Acceso total a todo el sistema y panel de administración |
| `gerente` | Supervisión global, configuración financiera, gestión de red médica |
| `analistaseguro` | Autoriza/rechaza solicitudes de citas, revisa siniestros |
| `corredorseguro` | Supervisión del flujo completo (solo lectura operativa) |
| `medico` | Registra consultas médicas, ve sus citas asignadas |
| `recepcionclinica` | Registra citas, gestiona pacientes de SU clínica únicamente |
| `cliente` | Ve sus propias pólizas, pagos, reclamos y solicitudes |

### Flujo de Autorización de una Solicitud de Cita

```
1. Cliente solicita cita → Estado: PENDING
2. Recepción agenda la cita → Estado: SCHEDULED
3. Analista audita y autoriza/rechaza → Estado: COMPLETED o REJECTED
4. Médico registra consulta → Se genera siniestro automáticamente
5. Se descuenta el saldo de la póliza
```

---

## Endpoints de la API

| Endpoint | Método | Descripción | Rol Requerido |
|---|---|---|---|
| `/api/medicos/` | GET/POST | CRUD de médicos | Admin/Gerente (escritura) |
| `/api/asegurados/` | GET/POST | CRUD de asegurados | Admin/Gerente (escritura) |
| `/api/clinicas/` | GET/POST | CRUD de clínicas | Admin/Gerente (escritura) |
| `/api/servicios-medicos/` | GET/POST | Catálogo global de servicios | Admin/Gerente (escritura) |
| `/api/baremos/` | GET/POST | Tarifarios por clínica | Admin/Gerente (escritura) |
| `/api/polizas/` | GET/POST | CRUD de pólizas | Según rol |
| `/api/pagos/` | GET/POST | Registro de pagos | Según rol |
| `/api/siniestros/` | GET/POST | Gestión de siniestros | Según rol |
| `/api/consultas-medicas/` | GET/POST | Fichas médicas | Médico (escritura) |
| `/api/citas/` | GET/POST | Solicitudes de citas | Según rol |
| `/api/cliente/` | GET | Portal del cliente | Cliente |
| `/api/finanzas/dashboard/` | GET | Dashboard financiero | Admin/Gerente |
| `/api/finanzas/configuracion/` | GET/PUT | Configuración financiera | Admin/Gerente |

---

## Ejecución con Docker (recomendado)

El backend se empaqueta en un `Dockerfile` y se orquesta con el frontend
mediante un `docker-compose.yml` en la carpeta del proyecto. Guía completa en
**[DOCKER.md](../DOCKER.md)**.

```bash
# Levanta backend + frontend + base de datos con un solo comando
docker compose up -d --build

# App:      http://localhost:8080
# Admin:    http://localhost:8080/admin/
# API:      http://localhost:8080/api/v1/
```

La imagen usa `python:3.13-slim` y corre como usuario sin privilegios
(`appuser`), no como root. El proceso es **gunicorn**, no el servidor de
desarrollo de Django.

### Qué pasa al arrancar

`entrypoint.sh` se ejecuta en cada `docker compose up`, en este orden:

1. Espera a la base de datos (solo si hay `DB_HOST`; con SQLite no espera).
2. `python manage.py migrate` — aplica las migraciones pendientes.
3. `python manage.py collectstatic` — deja los estáticos del admin en el
   volumen que nginx lee.
4. `python setup_demo.py` — carga clínicas, servicios, usuarios y la póliza de
   prueba. Se activa con `LOAD_DEMO_DATA=true` (por defecto). Es idempotente,
   así que no duplica nada en reinicios posteriores.
5. `gunicorn` en `0.0.0.0:8000` con varios workers.

Los datos persisten en volúmenes con nombre, así que sobreviven a
`docker compose down` y a los reinicios de Docker.

### Variables de entorno

`config/settings.py` lee todo de `os.environ` con valores por defecto pensados
para el desarrollo local, así que el proyecto arranca sin configurar nada y
Docker solo sobrescribe lo que necesita:

| Variable | Por defecto | Para qué |
|---|---|---|
| `DEBUG` | `False` en Docker | Modo depuración. No lo actives en producción |
| `SECRET_KEY` | clave insegura | **Cámbiala antes de desplegar** |
| `ALLOWED_HOSTS` | `*` | Dominios permitidos, separados por comas |
| `DB_ENGINE` | `django.db.backends.sqlite3` | Motor de base de datos |
| `DB_NAME` | `/app/data/db.sqlite3` | Ruta de la base de datos |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` | vacíos | Solo para PostgreSQL |
| `MEDIA_ROOT` | `BASE_DIR/media` | Carpeta de archivos subidos |
| `STATIC_ROOT` | `BASE_DIR/staticfiles` | Salida de `collectstatic` |
| `CORS_ALLOWED_ORIGINS` | vacío | Orígenes permitidos si separas dominios |
| `GUNICORN_WORKERS` | `3` | Nº de workers de gunicorn |

---

## Instalación y Configuración (sin Docker)

### Prerrequisitos

- Python 3.12+ (Django 6.1 lo requiere)
- pip (gestor de paquetes)

> **Nota:** PostgreSQL NO es obligatorio. El proyecto usa SQLite por defecto (sin configuración). Si deseas usar PostgreSQL, descomenta las líneas en el archivo `.env`.

### Pasos (mínimos)

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/gestion-seguros.git
cd gestion-seguros/backend

# 2. Crear entorno virtual
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar la demo (migraciones + datos de prueba + admin)
python setup_demo.py

# 5. Iniciar el servidor
python manage.py runserver
```

El script `setup_demo.py` crea automáticamente:
- Base de datos SQLite con todas las migraciones
- 3 clínicas afiliadas con 11 servicios médicos
- 5 usuarios de prueba (uno por cada rol del sistema)
- 1 póliza activa de $2,000 para el usuario `cliente1`
- 1 superusuario para el panel admin

La API estará disponible en: `http://127.0.0.1:8000/api/`
El panel de administración en: `http://127.0.0.1:8000/admin/`

### Credenciales

| Servicio | Usuario | Contraseña |
|---|---|---|
| Panel Admin | `admin` | `admin` |
| Gerente | `gerente1` | `123456` |
| Analista de Seguros | `analista1` | `123456` |
| Médico | `medico1` | `123456` |
| Recepción de Clínica | `recepcion1` | `123456` |
| Cliente | `cliente1` | `123456` |

### Configuración con PostgreSQL (opcional)

Si prefieres PostgreSQL en lugar de SQLite:

```bash
# 1. Crear el archivo .env
cp .env.example .env

# 2. Editar .env y descomentar las líneas de PostgreSQL:
#    DB_ENGINE=django.db.backends.postgresql
#    DB_NAME=gestion_seguros_db
#    DB_USER=postgres
#    DB_PASSWORD=tu_password
#    DB_HOST=localhost
#    DB_PORT=5432

# 3. Crear la base de datos en PostgreSQL
psql -U postgres -c "CREATE DATABASE gestion_seguros_db;"

# 4. Aplicar migraciones
python manage.py migrate
```

> **Sobre el archivo `.env`:** Django no lee archivos `.env` por sí solo. El
> proyecto lo carga si instalas la librería correspondiente:
>
> ```bash
> pip install python-dotenv
> ```
>
> Sin ella, el `.env` se ignora y el proyecto arranca con los valores por
> defecto. Para poner las variables sin instalar nada, defínelas en la terminal:
>
> ```bash
> export DB_ENGINE=django.db.backends.postgresql
> export DB_NAME=gestion_seguros_db
> export DB_USER=postgres
> export DB_PASSWORD=tu_password
> python manage.py migrate
> ```
>
> En Windows PowerShell se usan `$env:NOMBRE = "valor"`.

La API estará disponible en: `http://127.0.0.1:8000/api/`
El panel de administración en: `http://127.0.0.1:8000/admin/`

### Usuarios de Prueba

Ver archivo [USUARIOS.md](USUARIOS.md) para credenciales de los usuarios demo y sus permisos.

---

## Configuración de Base de Datos

El proyecto está configurado para usar **SQLite por defecto** (sin configuración adicional). Si no creas un archivo `.env`, la base de datos se crea automáticamente como `db.sqlite3` al ejecutar las migraciones.

Para usar **PostgreSQL**, define la variable `DB_ENGINE` en tu archivo `.env`:

```python
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
```

| Modo | Base de datos | Configuración necesaria |
|---|---|---|
| **Por defecto** | SQLite | Ninguna |
| **PostgreSQL** | PostgreSQL 14+ | Crear `.env` con `DB_ENGINE` y credenciales |

---

## Autenticación

La API usa **JWT (JSON Web Tokens)** para autenticación:

- **Access Token:** válida 24 horas
- **Refresh Token:** válido 7 días

Para autenticarse, enviar POST a `/api/token/` con `username` y `password`. El token devuelto se envía en el header:

```
Authorization: Bearer <tu_token_aqui>
```

---

## Notas para el Revisor

- **Señal `post_save`:** Al crear un usuario nuevo, se genera automáticamente su `InsuredProfile` con cédula temporal (`V-00000XXX`). El script `seed_test_users.py` reutiliza este perfil en lugar de crear otro duplicado.

- **Cálculo de saldo:** `InsurancePolicy.used_amount` suma los montos de siniestros en estados `APPROVED`, `IN_REVIEW` y `PENDING`. Esto evita que un cliente supere su cobertura mientras tiene reclamos en proceso.

- **Filtrado por rol:** El mixin `RoleBasedQuerysetMixin` en `mixins.py` filtra automáticamente los querysets según el rol del usuario autenticado. La recepción solo ve datos de su clínica; el médico solo ve sus consultas; el cliente solo ve sus pólizas.

- **Moneda:** Todos los montos están en **Dólares Americanos (USD)**. El campo `CURRENCY = 'USD'` está definido como constante en el modelo `ClinicBaremo`.

- **Configuración financiera:** El modelo `ConfiguracionFinanciera` es un singleton (un solo registro en la tabla). El método `obtener()` siempre devuelve la instancia única, creándola con valores por defecto si no existe.

---

## Licencia

Este proyecto está bajo la licencia MIT. Ver [LICENSE.md](LICENSE.md) para más detalles.

Autor: **Juniel Cabrices** - 2026
