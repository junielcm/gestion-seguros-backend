# ==============================================================================
# ARCHIVO: seed_test_users.py
# DESCRIPCIÓN: Script de datos de prueba (seed). Crea los grupos de roles del
#              sistema, usuarios demo para cada rol (contraseña: '123456') y un
#              asegurado con póliza activa, para poder probar la API completa
#              sin tener que registrar nada manualmente.
#
# USO:         venv\Scripts\python seed_test_users.py   (desde la carpeta backend)
#
# NOTA:        Usa los nombres de grupo CANÓNICOS definidos en SYSTEM_ROLES
#              (claims/serializers.py). Los grupos viejos ('Gerencia',
#              'Analistas', 'Medicos', 'Recepcion') fueron renombrados por la
#              migración 0010_migrate_legacy_groups, así que este script quedó
#              actualizado a los nombres nuevos.
#
# El script es idempotente: si lo ejecutas varias veces no duplica datos,
# solo completa o reutiliza lo que ya existe.
# ==============================================================================

import os
import django
from decimal import Decimal
from datetime import date, timedelta

# Este script corre por fuera del servidor de Django, así que hay que
# inicializar el entorno manualmente apuntando al settings del proyecto.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Group
from claims.models import DoctorProfile, InsuredProfile, InsurancePolicy

print("--- Creando Grupos, Usuarios y Datos Iniciales ---")

# ------------------------------------------------------------------------------
# 1. GRUPOS DE ROLES (mismo esquema canónico que usa todo el backend)
# ------------------------------------------------------------------------------
groups_list = ['gerente', 'analistaseguro', 'medico', 'recepcionclinica', 'cliente']
group_objects = {}

for group_name in groups_list:
    group, created = Group.objects.get_or_create(name=group_name)
    group_objects[group_name] = group
    print(f"Grupo configurado: {group_name}")

# ------------------------------------------------------------------------------
# 2. USUARIOS DE PRUEBA (uno por rol)
# ------------------------------------------------------------------------------
users_to_create = [
    {
        'username': 'gerente1',
        'email': 'gerente@seguro.com',
        'first_name': 'Carlos',
        'last_name': 'Mendoza',
        'group': 'gerente',
        'is_admin': True  # Superusuario: acceso total al panel admin
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
        'group': 'cliente',  # Rol CLIENT: solo ve sus propias pólizas/reclamos
        'is_admin': False
    },
]

# ------------------------------------------------------------------------------
# 3. Guardar usuarios en la base de datos y asignarles su grupo (rol)
# ------------------------------------------------------------------------------
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

    # Contraseña estándar '123456' SOLO para entorno de pruebas/demostración
    if created:
        user.set_password('123456')
        user.save()
        print(f"Usuario creado: {user.username} | Clave: 123456")

    # Asignar el grupo correspondiente (de esto dependen todos los permisos RBAC)
    user.groups.add(group_objects[u_data['group']])

# Limpiar InsuredProfile automaticos: la senal post_save los crea antes de
# asignar el grupo, asi que eliminamos los de usuarios NO clientes
from claims.models import InsuredProfile
InsuredProfile.objects.filter(
    user__groups__name__in=['gerente', 'analistaseguro', 'medico', 'recepcionclinica']
).delete()
InsuredProfile.objects.filter(
    user__is_superuser=True
).exclude(
    user__groups__name='cliente'
).delete()

# ------------------------------------------------------------------------------
# 4. Perfil de Médico vinculado al usuario 'medico1'
#    IMPORTANTE: sin este vínculo el médico no vería ninguna cita asignada,
#    porque el filtrado por rol busca a través de DoctorProfile.user.
# ------------------------------------------------------------------------------
medico_user = User.objects.get(username='medico1')

# Buscamos el perfil del médico en 3 pasos para no duplicar registros:
doctor = DoctorProfile.objects.filter(user=medico_user).first()

if doctor is None:
    # 2do paso: reutilizar algún perfil huérfano (sin usuario) con el mismo nombre
    doctor = DoctorProfile.objects.filter(
        user__isnull=True, first_name='Roberto', last_name='Perez'
    ).order_by('id').first()
    if doctor is not None:
        doctor.user = medico_user
        doctor.save(update_fields=['user'])

if doctor is None:
    # 3er paso: no existía ninguno -> se crea uno nuevo ya vinculado
    doctor = DoctorProfile.objects.create(
        user=medico_user,
        first_name='Roberto',
        last_name='Perez',
        specialty='Medicina General',
        license_number='MPPS-12345',
        phone='04121234567',
        is_active=True
    )

print("Perfil Médico de prueba creado/vinculado a 'medico1'.")

# ------------------------------------------------------------------------------
# 5. Asegurado con póliza activa, vinculado al usuario 'cliente1'
#    La señal post_save ya crea un InsuredProfile automático cuando se registra
#    el usuario (con cédula temporal V-00000XXX), así que aquí REUTILIZAMOS ese
#    perfil y solo le completamos los datos reales. Crear otro generaría un
#    duplicado huérfano y el cliente vería una póliza vacía en su dashboard.
# ------------------------------------------------------------------------------
cliente_user = User.objects.get(username='cliente1')

insured = getattr(cliente_user, 'insured_profile', None)

if insured is None:
    # Caso raro: usuario sin perfil autogenerado -> se crea uno nuevo vinculado
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
    # Caso normal: completar el perfil autogenerado con los datos del demo
    insured.national_id = "V-18765432"  # sustituye la cédula temporal V-0...
    insured.first_name = 'Juan'
    insured.last_name = 'Delgado'
    insured.email = 'cliente@seguro.com'
    insured.phone = '04247654321'
    insured.is_active = True
    insured.save()

# Póliza de salud activa por 1 año con cobertura de $2,000
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

# Si la póliza ya existía apuntando a otro asegurado (p.ej. de corridas viejas
# de la versión anterior del script), la reasignamos al perfil correcto.
if policy.insured_id != insured.id:
    policy.insured = insured
    policy.save()

print("Asegurado y Póliza POL-2026-001 de $2,000.00 configurados.")

print("\n¡Poblado de usuarios finalizado con éxito!")
