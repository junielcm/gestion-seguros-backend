# ==============================================================================
# ARCHIVO: setup_demo.py
# DESCRIPCIÓN: Script de configuración completa de la demo. Ejecuta todo lo
#              necesario para tener el sistema funcionando en segundos:
#              migraciones, datos de prueba y superusuario del admin.
#
# USO:         python setup_demo.py   (desde la carpeta backend)
#
# Resultado:   El sistema queda listo con:
#              - 3 clínicas afiliadas con 11 servicios
#              - 5 usuarios de prueba (uno por cada rol del sistema)
#              - 1 superusuario para el panel admin (admin / admin)
#              - 1 póliza activa de $2,000 para el usuario cliente1
# ==============================================================================

import os
import sys
import django
from decimal import Decimal
from datetime import date, timedelta

print("=" * 60)
print("  CONFIGURACION DE DEMO - GESTION DE SEGUROS")
print("=" * 60)

# ------------------------------------------------------------------------------
# 1. INICIALIZAR ENTORNO DJANGO
# ------------------------------------------------------------------------------
print("\n[1/5] Verificando entorno...")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    django.setup()
except Exception as e:
    print(f"  ERROR: No se pudo inicializar Django: {e}")
    print("  Asegurate de haber instalado las dependencias:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

print("  OK")

# ------------------------------------------------------------------------------
# 2. APLICAR MIGRACIONES
# ------------------------------------------------------------------------------
print("\n[2/5] Aplicando migraciones...")

from django.core.management import call_command

try:
    call_command('migrate', verbosity=0)
    print("  OK (base de datos lista)")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# ------------------------------------------------------------------------------
# 3. POBLAR CLINICAS Y SERVICIOS
# ------------------------------------------------------------------------------
print("\n[3/5] Poblando clinicas y servicios...")

from claims.models import Clinic, ClinicService

clinics_data = [
    {
        "name": "Clinica El Avila",
        "address": "Av. San Juan Bosco, Altamira, Caracas",
        "phone": "0212-2761111",
        "services": [
            {"name": "Consulta Medicina General", "cost": Decimal("40.00")},
            {"name": "Atencion Emergencia Adultos", "cost": Decimal("120.00")},
            {"name": "Rayos X de Torax", "cost": Decimal("35.00")},
            {"name": "Perfil 20 (Laboratorio)", "cost": Decimal("50.00")},
        ]
    },
    {
        "name": "Centro Medico Docente La Trinidad",
        "address": "Av. Intercomunal La Trinidad, Baruta, Caracas",
        "phone": "0212-9496411",
        "services": [
            {"name": "Consulta Especializada (Cardiologia/Pediatria)", "cost": Decimal("60.00")},
            {"name": "Atencion Emergencia Pediatria", "cost": Decimal("130.00")},
            {"name": "Ecografia Abdominal", "cost": Decimal("75.00")},
            {"name": "Hospitalizacion Dia (Habitacion)", "cost": Decimal("250.00")},
        ]
    },
    {
        "name": "Policlinica Metropolitana",
        "address": "Calle A-1, Caurimare, Caracas",
        "phone": "0212-9851111",
        "services": [
            {"name": "Consulta Traumatologia", "cost": Decimal("50.00")},
            {"name": "Sutura de Herida Menor", "cost": Decimal("90.00")},
            {"name": "Tomografia Axial Computarizada (TAC)", "cost": Decimal("180.00")},
        ]
    }
]

clinicas_creadas = 0
servicios_creados = 0

for c_info in clinics_data:
    clinic, created = Clinic.objects.get_or_create(
        name=c_info["name"],
        defaults={
            "address": c_info["address"],
            "phone": c_info["phone"],
            "is_active": True
        }
    )
    if created:
        clinicas_creadas += 1

    for s_info in c_info["services"]:
        service, s_created = ClinicService.objects.get_or_create(
            clinic=clinic,
            name=s_info["name"],
            defaults={
                "base_cost": s_info["cost"],
                "is_available": True
            }
        )
        if s_created:
            servicios_creados += 1

print(f"  OK ({clinicas_creadas} clinicas, {servicios_creados} servicios nuevos)")

# ------------------------------------------------------------------------------
# 4. CREAR GRUPOS, USUARIOS DE PRUEBA Y POLIZA
# ------------------------------------------------------------------------------
print("\n[4/5] Creando usuarios de prueba...")

from django.contrib.auth.models import User, Group
from claims.models import DoctorProfile, InsuredProfile, InsurancePolicy

# Grupos de roles
groups_list = ['gerente', 'analistaseguro', 'medico', 'recepcionclinica', 'cliente']
group_objects = {}

for group_name in groups_list:
    group, created = Group.objects.get_or_create(name=group_name)
    group_objects[group_name] = group

# Usuarios demo
users_to_create = [
    {
        'username': 'gerente1',
        'email': 'gerente@seguro.com',
        'first_name': 'Carlos',
        'last_name': 'Mendoza',
        'group': 'gerente',
        'is_admin': True
    },
    {
        'username': 'analista1',
        'email': 'analista@seguro.com',
        'first_name': 'Ana',
        'last_name': 'Gomez',
        'group': 'analistaseguro',
        'is_admin': False
    },
    {
        'username': 'medico1',
        'email': 'medico@seguro.com',
        'first_name': 'Roberto',
        'last_name': 'Perez',
        'group': 'medico',
        'is_admin': False
    },
    {
        'username': 'recepcion1',
        'email': 'recepcion@seguro.com',
        'first_name': 'Maria',
        'last_name': 'Rojas',
        'group': 'recepcionclinica',
        'is_admin': False
    },
    {
        'username': 'cliente1',
        'email': 'cliente@seguro.com',
        'first_name': 'Juan',
        'last_name': 'Delgado',
        'group': 'cliente',
        'is_admin': False
    },
]

usuarios_creados = 0

for u_data in users_to_create:
    user, created = User.objects.get_or_create(
        username=u_data['username'],
        defaults={
            'email': u_data['email'],
            'first_name': u_data['first_name'],
            'last_name': u_data['last_name'],
            'is_staff': u_data['is_admin'],
            'is_superuser': u_data['is_admin'],
        }
    )

    if created:
        user.set_password('123456')
        user.save()
        usuarios_creados += 1

    user.groups.add(group_objects[u_data['group']])

# Limpiar InsuredProfile automaticos: la senal post_save los crea antes de
# asignar el grupo, asi que eliminamos los de usuarios NO clientes
InsuredProfile.objects.filter(
    user__groups__name__in=['gerente', 'analistaseguro', 'medico', 'recepcionclinica']
).delete()
# Tambien los de admin/superuser (no tienen grupo, pero no son clientes)
InsuredProfile.objects.filter(
    user__is_superuser=True
).exclude(
    user__groups__name='cliente'
).delete()

# Perfil de Medico vinculado a medico1
medico_user = User.objects.get(username='medico1')
doctor = DoctorProfile.objects.filter(user=medico_user).first()

if doctor is None:
    doctor = DoctorProfile.objects.filter(
        user__isnull=True, first_name='Roberto', last_name='Perez'
    ).order_by('id').first()
    if doctor is not None:
        doctor.user = medico_user
        doctor.save(update_fields=['user'])

if doctor is None:
    DoctorProfile.objects.create(
        user=medico_user,
        first_name='Roberto',
        last_name='Perez',
        specialty='Medicina General',
        license_number='MPPS-12345',
        phone='04121234567',
        is_active=True
    )

# Asegurado y Poliza vinculados a cliente1
cliente_user = User.objects.get(username='cliente1')
insured = getattr(cliente_user, 'insured_profile', None)

if insured is None:
    insured = InsuredProfile.objects.create(
        user=cliente_user,
        national_id="V-18765432",
        first_name='Juan',
        last_name='Delgado',
        email='cliente@seguro.com',
        phone='04247654321',
        is_active=True
    )
else:
    insured.national_id = "V-18765432"
    insured.first_name = 'Juan'
    insured.last_name = 'Delgado'
    insured.email = 'cliente@seguro.com'
    insured.phone = '04247654321'
    insured.is_active = True
    insured.save()

policy, _ = InsurancePolicy.objects.get_or_create(
    policy_number="POL-2026-001",
    defaults={
        'insured': insured,
        'policy_type': 'HEALTH',
        'coverage_amount': Decimal('2000.00'),
        'start_date': date.today(),
        'end_date': date.today() + timedelta(days=365),
        'status': 'ACTIVE'
    }
)

if policy.insured_id != insured.id:
    policy.insured = insured
    policy.save()

print(f"  OK ({usuarios_creados} usuarios nuevos, poliza POL-2026-001)")

# ------------------------------------------------------------------------------
# 5. CREAR SUPERUSUARIO PARA EL PANEL ADMIN (admin / admin)
# ------------------------------------------------------------------------------
print("\n[5/5] Creando superusuario del panel admin...")

admin_user, created = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@seguro.com',
        'first_name': 'Administrador',
        'last_name': 'General',
        'is_staff': True,
        'is_superuser': True,
    }
)

if created:
    admin_user.set_password('admin')
    admin_user.save()
    print("  OK (admin / admin)")
else:
    # Si ya existe, asegurar que tenga los permisos de admin
    if not admin_user.is_superuser:
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password('admin')
        admin_user.save()
        print("  OK (actualizado a superusuario)")
    else:
        print("  OK (ya existia)")

# Limpiar InsuredProfile del admin si se auto-creo (el admin no es cliente)
admin_insured = getattr(admin_user, 'insured_profile', None)
if admin_insured:
    admin_insured.delete()

# ------------------------------------------------------------------------------
# RESUMEN FINAL
# ------------------------------------------------------------------------------
total_users = User.objects.count()
total_clinics = Clinic.objects.count()
total_services = ClinicService.objects.count()

print("\n" + "=" * 60)
print("  DEMO CONFIGURADA CON EXITO")
print("=" * 60)
print(f"""
  Base de datos: SQLite (db.sqlite3)

  Datos creados:
    - {total_clinics} clinicas afiliadas
    - {total_services} servicios medicalizados
    - {total_users} usuarios en el sistema
    - 1 poliza activa (POL-2026-001 / $2,000.00)

  Panel Admin (superusuario):
    URL:      http://127.0.0.1:8000/admin/
    Usuario:  admin
    Clave:    admin

  API REST:
    URL:      http://127.0.0.1:8000/api/

  Usuarios de prueba (contraseña: 123456):
    gerente1, analista1, medico1, recepcion1, cliente1

  Para iniciar el servidor:
    python manage.py runserver
""")
