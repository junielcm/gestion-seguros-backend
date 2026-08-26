# ==============================================================================
# ARCHIVO: claims/management/commands/vincular_medicos.py
# DESCRIPCIÓN: Crea y vincula un DoctorProfile a cada usuario con rol 'medico'
#              que aún no tenga uno (para usuarios creados antes del autolink).
# USO:         python manage.py vincular_medicos
# ==============================================================================

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from claims.models import DoctorProfile


class Command(BaseCommand):
    help = "Vincula un DoctorProfile a cada usuario con rol 'medico' que no tenga uno."

    def handle(self, *args, **options):
        medicos = User.objects.filter(groups__name='medico')
        creados = 0
        vinculados_existentes = 0
        reutilizados = 0

        for user in medicos:
            if hasattr(user, 'doctor_profile'):
                vinculados_existentes += 1
                continue

            nombre = user.first_name or user.username
            apellido = user.last_name or 'Por Definir'

            # Si existe un perfil huérfano (sin usuario) con el mismo nombre,
            # lo REUTILIZamos en lugar de crear un duplicado.
            orphan = DoctorProfile.objects.filter(
                user__isnull=True, first_name=nombre, last_name=apellido
            ).order_by('id').first()

            if orphan:
                orphan.user = user
                orphan.save(update_fields=['user'])
                reutilizados += 1
                self.stdout.write(self.style.SUCCESS(
                    f"~ Perfil existente #{orphan.id} ({orphan.first_name} {orphan.last_name}) vinculado a '{user.username}'"
                ))
                continue

            DoctorProfile.objects.create(
                user=user,
                first_name=nombre,
                last_name=apellido,
                specialty='Medicina General',
                license_number=f'TEMP-{user.id}',
            )
            creados += 1
            self.stdout.write(self.style.SUCCESS(f"+ Perfil creado para '{user.username}'"))

        self.stdout.write(self.style.SUCCESS(
            f"\nProceso finalizado. Creados: {creados} | "
            f"Reutilizados (huérfanos): {reutilizados} | Ya vinculados: {vinculados_existentes}"
        ))
