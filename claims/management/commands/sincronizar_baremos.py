# ==============================================================================
# ARCHIVO: claims/management/commands/sincronizar_baremos.py
# DESCRIPCIÓN: Utilidad de mantenimiento del catálogo de servicios y precios.
#
#              1) MIGRA los precios del modelo legacy (ClinicService con
#                 base_cost por clínica) hacia el sistema oficial:
#                 MedicalService (catálogo global) + ClinicBaremo (precio
#                 por clínica). Es el modelo correcto del negocio: el
#                 servicio se define una vez y CADA CLÍNICA fija su tarifa.
#
#              2) REPARA citas COMPLETADAS que quedaron sin reclamo (pasó
#                 antes de que el médico pudiera elegir el baremo): genera
#                 su consumo retroactivo buscando el ítem del baremo que
#                 corresponda al tipo de servicio de la cita.
#
#              Es IDEMPOTENTE: puede ejecutarse varias veces sin duplicar
#              datos (usa get_or_create / respeta reclamos ya generados).
#
# USO:         venv\Scripts\python manage.py sincronizar_baremos
# ==============================================================================

from django.core.management.base import BaseCommand
from django.utils import timezone

from claims.models import (
    Claim,
    ClinicBaremo,
    ClinicService,
    MedicalAppointmentRequest,
    MedicalService,
)


class Command(BaseCommand):
    help = ('Sincroniza catálogo/baremos desde los servicios legacy y '
            'genera el consumo retroactivo de citas completadas sin reclamo.')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('1) Migración de servicios legacy al baremo'))
        self._migrar_baremos()

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('2) Reparación de citas completadas sin consumo'))
        self._reparar_citas_huerfanas()

    # ------------------------------------------------------------------
    def _migrar_baremos(self):
        """
        Por cada ClinicService legacy asegura que exista el MedicalService
        global y su ClinicBaremo con ese mismo precio en esa clínica.
        """
        creados_servicio = 0
        creados_baremo = 0

        for cs in ClinicService.objects.select_related('clinic').all():
            servicio, nuevo = MedicalService.objects.get_or_create(
                name__iexact=cs.name.strip(),
                defaults={'name': cs.name.strip(), 'description': ''}
            )
            if nuevo:
                creados_servicio += 1
                self.stdout.write(f'  [+] Servicio global creado: {servicio.name}')

            baremo, nuevo_baremo = ClinicBaremo.objects.get_or_create(
                clinic=cs.clinic,
                service=servicio,
                defaults={'price': cs.base_cost, 'is_active': True}
            )
            if nuevo_baremo:
                creados_baremo += 1
                self.stdout.write(
                    f'  [+] Baremo {cs.clinic.name}: {servicio.name} -> ${baremo.price}'
                )

        resumen = f'Servicios globales creados: {creados_servicio} | Baremos creados: {creados_baremo}'
        self.stdout.write(self.style.SUCCESS(resumen))

    # ------------------------------------------------------------------
    def _buscar_item_baremo(self, cita):
        """
        Busca el ítem activo del baremo de la clínica que corresponde al
        service_type de la cita, por palabras clave del nombre.
        Devuelve (baremo, precio) o (None, None) si no hay coincidencia.
        """
        candidatos = ClinicBaremo.objects.filter(
            clinic=cita.clinic, is_active=True
        ).select_related('service')

        PALABRAS = {
            'CONSULTATION': ['consulta'],
            'XRAY': ['rayos', 'rx', 'ecografia', 'imagen'],
            'LAB': ['laboratorio', 'perfil', 'examen'],
        }
        claves = PALABRAS.get(cita.service_type, [])

        # Primero intenta match por palabras clave del tipo de servicio...
        for baremo in candidatos:
            nombre = baremo.service.name.lower()
            if any(palabra in nombre for palabra in claves):
                return baremo

        # ...y si el tipo es OTHER (o no hubo match), usa el primer activo
        if cita.service_type == 'OTHER':
            return candidatos.first()
        return None

    # ------------------------------------------------------------------
    def _reparar_citas_huerfanas(self):
        """
        Genera el Claim APPROVED (consumo) de las citas COMPLETADAS que no
        lo tienen. Misma lógica que _registrar_consumo del ViewSet, pero
        resolviendo el precio desde el baremo migrado.
        """
        huerfanas = MedicalAppointmentRequest.objects.filter(
            status='COMPLETED'
        ).exclude(generated_claim__isnull=False)

        reparadas = sin_precio = 0

        for cita in huerfanas:
            baremo = self._buscar_item_baremo(cita)
            if not baremo:
                sin_precio += 1
                self.stdout.write(self.style.WARNING(
                    f'  [!] Cita #{cita.id} ({cita.clinic.name}): sin ítem de baremo '
                    f'compatible con "{cita.service_type}". Revísala manualmente.'
                ))
                continue

            fecha_incidente = (
                cita.scheduled_date.date()
                if cita.scheduled_date else timezone.now().date()
            )
            claim, creado = Claim.objects.get_or_create(
                claim_number=f'CITA-{cita.id}',
                defaults={
                    'policy': cita.policy,
                    'clinic': cita.clinic,
                    'clinic_service': cita.clinic_service,
                    'baremo': baremo,
                    'appointment': cita,
                    'assigned_doctor': cita.assigned_doctor,
                    'incident_date': fecha_incidente,
                    'description': (
                        f'Atención médica de la cita #{cita.id}. '
                        f'Motivo: {(cita.reason_or_symptoms or "")[:180]}'
                    ),
                    'requested_amount': baremo.price,
                    'status': 'APPROVED',
                    'resolution_notes': (cita.doctor_notes or '')[:500],
                }
            )
            if creado:
                reparadas += 1
                self.stdout.write(
                    f'  [+] Cita #{cita.id} reparada: reclamo {claim.claim_number} '
                    f'por ${claim.requested_amount} ({baremo.service.name})'
                )

        self.stdout.write(self.style.SUCCESS(
            f'Reclamos retroactivos generados: {reparadas} | Sin precio posible: {sin_precio}'
        ))
