# ==============================================================================
# Migración 0010: Normaliza los roles legacy al esquema canónico SYSTEM_ROLES.
#
# Historia: el sistema antiguo usaba grupos con nombres distintos ('Gerencia',
# 'Analistas', 'Medicos', 'Recepcion'). Todo el código actual (permisos, mixins,
# serializers y frontend) valida contra los grupos canónicos definidos en
# claims/serializers.py (SYSTEM_ROLES). Esta migración reasigna cada usuario de
# su grupo legacy al equivalente canónico y elimina los grupos obsoletos.
# ==============================================================================
from django.db import migrations

# Mapa: nombre del grupo legacy -> nombre del grupo canónico
LEGACY_TO_CANONICAL = {
    'Gerencia': 'gerente',
    'Analistas': 'analistaseguro',
    'Medicos': 'medico',
    'Recepcion': 'recepcionclinica',
}


def migrate_legacy_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')

    for legacy_name, canonical_name in LEGACY_TO_CANONICAL.items():
        try:
            legacy_group = Group.objects.get(name=legacy_name)
        except Group.DoesNotExist:
            continue  # Ya fue migrado o nunca existió

        canonical_group, _ = Group.objects.get_or_create(name=canonical_name)

        for user in legacy_group.user_set.all():
            user.groups.add(canonical_group)
            user.groups.remove(legacy_group)

        legacy_group.delete()


def rollback(apps, schema_editor):
    # La reversión no restaura los nombres legacy: los datos canónicos son la
    # fuente de verdad a partir de esta versión.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('claims', '0009_medicalservice_claim_appointment_clinic_email_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_roles, rollback),
    ]
