# ==============================================================================
# ARCHIVO: seed_clinics.py
# DESCRIPCIÓN: Script de datos de prueba (seed). Crea clínicas afiliadas con sus
#              servicios y costos base, para tener una red médica de ejemplo al
#              instalar el proyecto.
#
# USO:         venv\Scripts\python seed_clinics.py   (desde la carpeta backend)
#
# Es idempotente: usa get_or_create, así que se puede ejecutar varias veces
# sin generar duplicados.
# ==============================================================================

import os
import django
from decimal import Decimal

# Este script corre por fuera del servidor de Django, así que hay que
# inicializar el entorno manualmente apuntando al settings del proyecto.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from claims.models import Clinic, ClinicService

print("--- Poblando Clínicas y Servicios Baremados ---")

# Datos demo: 3 clínicas de Caracas, cada una con su catálogo de servicios y precio base
# (el costo base es lo que la clínica cobra; es la referencia para los reclamos)

clinics_data = [
    {
        "name": "Clínica El Ávila",
        "address": "Av. San Juan Bosco, Altamira, Caracas",
        "phone": "0212-2761111",
        "services": [
            {"name": "Consulta Medicina General", "cost": Decimal("40.00")},
            {"name": "Atención Emergencia Adultos", "cost": Decimal("120.00")},
            {"name": "Rayos X de Tórax", "cost": Decimal("35.00")},
            {"name": "Perfil 20 (Laboratorio)", "cost": Decimal("50.00")},
        ]
    },
    {
        "name": "Centro Médico Docente La Trinidad",
        "address": "Av. Intercomunal La Trinidad, Baruta, Caracas",
        "phone": "0212-9496411",
        "services": [
            {"name": "Consulta Especializada (Cardiología/Pediatría)", "cost": Decimal("60.00")},
            {"name": "Atención Emergencia Pediatría", "cost": Decimal("130.00")},
            {"name": "Ecografía Abdominal", "cost": Decimal("75.00")},
            {"name": "Hospitalización Día (Habitación)", "cost": Decimal("250.00")},
        ]
    },
    {
        "name": "Policlínica Metropolitana",
        "address": "Calle A-1, Caurimare, Caracas",
        "phone": "0212-9851111",
        "services": [
            {"name": "Consulta Traumatología", "cost": Decimal("50.00")},
            {"name": "Sutura de Herida Menor", "cost": Decimal("90.00")},
            {"name": "Tomografía Axial Computarizada (TAC)", "cost": Decimal("180.00")},
        ]
    }
]

# Recorremos los datos y creamos cada clínica con sus servicios (si no existen)
for c_info in clinics_data:
    clinic, created = Clinic.objects.get_or_create(
        name=c_info["name"],
        defaults={
            "address": c_info["address"],
            "phone": c_info["phone"],
            "is_active": True
        }
    )
    status_str = "Creada" if created else "Ya existía"
    print(f"\n[Clínica] {clinic.name} ({status_str})")

    for s_info in c_info["services"]:
        service, s_created = ClinicService.objects.get_or_create(
            clinic=clinic,
            name=s_info["name"],
            defaults={
                "base_cost": s_info["cost"],
                "is_available": True
            }
        )
        s_status = "Creado" if s_created else "Existente"
        # Caracteres ASCII en los prints: los símbolos Unicode como '└─'
        # rompen la consola de Windows (codificación cp1252)
        print(f"  - Servicio: {service.name} | Costo Base: ${service.base_cost} ({s_status})")

print("\n¡Poblado de clínicas finalizado con éxito!")