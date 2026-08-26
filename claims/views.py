# ==============================================================================
# ARCHIVO: claims/views.py
# DESCRIPCIÓN: Controlador de vistas y endpoints de API con control de roles (RBAC)
# ==============================================================================

import csv
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, filters, status, permissions, generics
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend


# Importación de Modelos
from .models import (
    DoctorProfile, 
    InsuredProfile, 
    Clinic, 
    ClinicService, 
    ClinicStaffProfile, 
    MedicalService,
    ClinicBaremo,
    InsurancePolicy, 
    PolicyPayment, 
    Claim, 
    MedicalConsultation,
    MedicalAppointmentRequest,
    ConfiguracionFinanciera
)

# Importación de Serializadores
from .serializers import (
    DoctorProfileSerializer, 
    InsuredProfileSerializer, 
    ClinicSerializer, 
    ClinicServiceSerializer, 
    ClinicStaffProfileSerializer, 
    MedicalServiceSerializer,
    ClinicBaremoSerializer,
    InsurancePolicySerializer, 
    PolicyPaymentSerializer, 
    ClaimSerializer,
    MedicalConsultationSerializer,
    MedicalAppointmentRequestSerializer,
    RegistroClienteSerializer,
    ConfiguracionFinancieraSerializer,
    UserSerializer
)

# Importación de Mixins y Permisos de Roles
from .mixins import RoleBasedQuerysetMixin
from .permissions import RoleBasedPermission, IsAdminOrManager, IsInsuranceAnalyst, IsDoctor, IsAdminOrManagerOrReadOnly, IsReceptionOrAdminManager


# ------------------------------------------------------------------------------
# 1. PERFIL DE MÉDICOS
# ------------------------------------------------------------------------------
class DoctorProfileViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = DoctorProfile.objects.select_related('user').order_by('id').all()
    serializer_class = DoctorProfileSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'license_number', 'specialty']


# ------------------------------------------------------------------------------
# 2. PERFIL DE ASEGURADOS
# ------------------------------------------------------------------------------
class InsuredProfileViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    """
    CRUD de asegurados. Admin/Gerente/Analista ven SOLO los perfiles de
    usuarios con grupo 'cliente' (evita mostrar médicos, recepcionistas, etc.).
    """
    serializer_class = InsuredProfileSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [filters.SearchFilter]
    search_fields = ['national_id', 'first_name', 'last_name', 'email']

    def get_queryset(self):
        qs = InsuredProfile.objects.all()
        user = self.request.user
        if user.is_superuser or user.groups.filter(
            name__in=['admin', 'gerente', 'analistaseguro', 'corredorseguro']
        ).exists():
            return qs.filter(user__groups__name='cliente')
        return qs


# ------------------------------------------------------------------------------
# 3. GESTIÓN DE CLÍNICAS Y CARGA MASIVA DE BAREMOS
# ------------------------------------------------------------------------------
class ClinicViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    """
    CRUD de clínicas. Escritura exclusiva Admin/Gerencia; lectura para
    cualquier usuario autenticado (clientes, recepciones y médicos).
    """
    queryset = Clinic.objects.prefetch_related('services', 'baremos__service').all()
    serializer_class = ClinicSerializer
    permission_classes = [IsAdminOrManagerOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'address', 'rif']

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser], url_path='importar-servicios')
    def importar_servicios(self, request, pk=None):
        clinic = self.get_object()
        file_obj = request.FILES.get('file')

        if not file_obj:
            return Response(
                {"error": "No se adjuntó ningún archivo en la solicitud."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            decoded_file = file_obj.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            
            created_count = 0
            for row in reader:
                ClinicService.objects.update_or_create(
                    clinic=clinic,
                    name=row['nombre_servicio'].strip(),
                    defaults={
                        'description': row.get('descripcion', ''),
                        'base_cost': Decimal(row['costo_base'].strip()),
                        'is_available': True
                    }
                )
                created_count += 1

            return Response({
                "message": f"Se procesaron e importaron {created_count} servicios para {clinic.name} exitosamente."
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"Error al procesar el archivo CSV: {str(e)}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )


# ------------------------------------------------------------------------------
# 4. SERVICIOS Y BAREMOS DE CLÍNICAS
# ------------------------------------------------------------------------------
class ClinicServiceViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ClinicService.objects.select_related('clinic').filter(is_available=True)
    serializer_class = ClinicServiceSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['clinic']
    search_fields = ['name', 'description']


# ------------------------------------------------------------------------------
# 4B. GESTIÓN DE RED MÉDICA: CATÁLOGO Y BAREMOS (Admin / Gerencia)
# ------------------------------------------------------------------------------
class MedicalServiceViewSet(viewsets.ModelViewSet):
    """
    Catálogo maestro de servicios médicos.
    Escritura exclusiva Admin/Gerencia; lectura para cualquier autenticado.
    """
    queryset = MedicalService.objects.all()
    serializer_class = MedicalServiceSerializer
    permission_classes = [IsAdminOrManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']

    @action(detail=False, methods=['post'], url_path='carga-masiva')
    def carga_masiva(self, request):
        """
        Importa/actualiza muchos servicios del catálogo maestro en una sola llamada.

        Body JSON:
            {
              "items": [
                {"service_name": "Consulta General", "description": "...", "is_active": true},
                ...
              ]
            }

        Reglas:
            - Si el servicio ya existe (nombre case-insensitive) se ACTUALIZA (upsert).
            - Devuelve un desglose: creados/actualizados/errores.
        """
        items = request.data.get('items')
        if not isinstance(items, list) or not items:
            return Response(
                {"error": "'items' debe ser una lista con al menos un servicio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        creados, actualizados, errores = 0, 0, []

        for index, item in enumerate(items, start=1):
            name = str(item.get('service_name') or '').strip()
            if not name:
                errores.append(f"Fila {index}: falta el nombre del servicio.")
                continue

            description = str(item.get('description') or '').strip()
            is_active = item.get('is_active', True)
            if isinstance(is_active, str):
                is_active = is_active.strip().lower() not in ('no', 'false', '0', 'inactivo')

            service, created = MedicalService.objects.update_or_create(
                name__iexact=name,
                defaults={'name': name, 'description': description, 'is_active': bool(is_active)}
            )
            if created:
                creados += 1
            else:
                actualizados += 1

        return Response({
            'creados': creados,
            'actualizados': actualizados,
            'errores': errores,
        }, status=status.HTTP_200_OK)


class ClinicBaremoViewSet(viewsets.ModelViewSet):
    """
    Tarifario por clínica (precio de cada servicio del catálogo).
    Escritura exclusiva Admin/Gerencia; lectura operativa para recepción/médicos,
    filtrable por clínica: /api/v1/baremos/?clinic={id}
    """
    queryset = ClinicBaremo.objects.select_related('clinic', 'service').order_by('id').all()
    serializer_class = ClinicBaremoSerializer
    permission_classes = [IsAdminOrManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['clinic', 'service', 'is_active']
    search_fields = ['service__name', 'clinic__name']

    @action(detail=False, methods=['post'], url_path='carga-masiva')
    def carga_masiva(self, request):
        """
        Importa/actualiza muchos precios del baremo de una clínica en una sola
        llamada. Pensada para la carga masiva desde Excel/CSV o pegado.

        Body JSON:
            {
              "clinic": <id>,
              "items": [
                {"service_name": "Consulta General", "price": "50.00", "is_active": true},
                ...
              ]
            }

        Reglas:
            - El servicio se busca por nombre (case-insensitive); si no existe en
              el catálogo maestro se crea automáticamente y se reporta.
            - Si el baremo ya existe para esa clínica+servicio se ACTUALIZA
              (upsert), nunca se duplica.
            - Devuelve un desglose fila por fila: creados/actualizados/errores.
        """
        clinic = Clinic.objects.filter(id=request.data.get('clinic')).first()
        if not clinic:
            return Response(
                {"error": "Debes indicar una clínica válida."},
                status=status.HTTP_400_BAD_REQUEST
            )

        items = request.data.get('items')
        if not isinstance(items, list) or not items:
            return Response(
                {"error": "'items' debe ser una lista con al menos un servicio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        creados, actualizados = 0, 0
        servicios_creados = []
        errores = []

        for index, item in enumerate(items, start=1):
            name = str(item.get('service_name') or '').strip()
            raw_price = item.get('price')

            if not name:
                errores.append(f"Fila {index}: falta el nombre del servicio.")
                continue

            price = self._parse_price(raw_price)
            if price is None or price <= 0:
                errores.append(f"Fila {index}: precio inválido ({raw_price!r}) para '{name}'.")
                continue

            # Resuelve el servicio en el catálogo maestro (crea si no existe)
            service = MedicalService.objects.filter(name__iexact=name).first()
            if not service:
                service = MedicalService.objects.create(name=name)
                servicios_creados.append(name)

            is_active = item.get('is_active', True)
            if isinstance(is_active, str):
                is_active = is_active.strip().lower() not in ('no', 'false', '0', 'inactivo')

            baremo, created = ClinicBaremo.objects.update_or_create(
                clinic=clinic,
                service=service,
                defaults={'price': price, 'is_active': bool(is_active)}
            )
            if created:
                creados += 1
            else:
                actualizados += 1

        return Response({
            'clinic': clinic.name,
            'creados': creados,
            'actualizados': actualizados,
            'servicios_nuevos_en_catalogo': servicios_creados,
            'errores': errores,
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _parse_price(raw):
        """
        Convierte precios escritos a mano o exportados de Excel: acepta
        '1234.56', '1.234,56' y '1234,56'. Devuelve Decimal o None.
        """
        if raw is None:
            return None
        text = str(raw).strip().replace(' ', '').replace('Bs.', '').replace('$', '')
        if not text:
            return None
        try:
            if ',' in text and '.' in text:
                # Punto de miles + coma decimal -> '1.234,56'
                text = text.replace('.', '').replace(',', '.')
            elif ',' in text:
                text = text.replace(',', '.')
            from decimal import InvalidOperation
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None


# ------------------------------------------------------------------------------
# 5. ASIGNACIÓN DE PERSONAL DE RECEPCIÓN
# ------------------------------------------------------------------------------
class ClinicStaffProfileViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ClinicStaffProfile.objects.select_related('user', 'clinic').all()
    serializer_class = ClinicStaffProfileSerializer
    permission_classes = [RoleBasedPermission]


# ------------------------------------------------------------------------------
# 6. PÓLIZAS DE SEGURO
# ------------------------------------------------------------------------------
class InsurancePolicyViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = InsurancePolicy.objects.select_related('insured').all()
    serializer_class = InsurancePolicySerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'policy_type', 'insured']
    search_fields = ['policy_number', 'insured__national_id', 'insured__first_name']


# ------------------------------------------------------------------------------
# 7. PAGOS DE PÓLIZAS
# ------------------------------------------------------------------------------
class PolicyPaymentViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PolicyPayment.objects.select_related(
        'policy', 'policy__insured'
    ).all()
    serializer_class = PolicyPaymentSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'policy']
    search_fields = ['payment_reference', 'policy__policy_number', 'policy__insured__national_id']

    @action(detail=True, methods=['post'], url_path='verificar',
            permission_classes=[IsInsuranceAnalyst])
    def verificar(self, request, pk=None):
        """
        Dictamina un comprobante de pago PENDING. Exclusivo de
        Analista de Seguros / Gerencia / Admin (IsInsuranceAnalyst;
        la recepción de clínica queda excluida a propósito).

        Body esperado:
          {"status": "APPROVED" | "REJECTED", "verification_notes": "..."}
        El rechazo EXIGE nota con el motivo.
        """
        pago = self.get_object()

        if pago.status != 'PENDING':
            return Response(
                {'detail': f'Este pago ya fue verificado ({pago.status}); '
                           'no puede dictaminarse nuevamente.'},
                status=status.HTTP_400_BAD_REQUEST)

        nuevo_estado = request.data.get('status')
        notas = (request.data.get('verification_notes') or '').strip()
        if nuevo_estado not in ('APPROVED', 'REJECTED'):
            return Response({'status': ['Debe ser APPROVED o REJECTED.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if nuevo_estado == 'REJECTED' and not notas:
            return Response({'verification_notes': ['Indica el motivo del rechazo.']},
                            status=status.HTTP_400_BAD_REQUEST)

        pago.status = nuevo_estado
        pago.verification_notes = notas or None
        pago.save(update_fields=['status', 'verification_notes', 'updated_at'])
        return Response(self.get_serializer(pago).data)


# ------------------------------------------------------------------------------
# 8. SINIESTROS / RECLAMOS
# ------------------------------------------------------------------------------
class ClaimViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Claim.objects.select_related(
        'policy', 'policy__insured', 'clinic', 'clinic_service', 'assigned_doctor'
    ).prefetch_related('consultation').all()
    
    serializer_class = ClaimSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'assigned_doctor', 'policy', 'clinic']
    search_fields = ['claim_number', 'policy__policy_number', 'policy__insured__national_id']

    @action(detail=True, methods=['post'], url_path='dictaminar')
    def dictaminar(self, request, pk=None):
        claim = self.get_object()
        new_status = request.data.get('status')
        resolution_notes = request.data.get('resolution_notes', '')

        if new_status not in ['APPROVED', 'REJECTED']:
            return Response(
                {"error": "El estado debe ser estrictamente 'APPROVED' o 'REJECTED'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        claim.status = new_status
        claim.resolution_notes = resolution_notes
        claim.save()

        return Response(ClaimSerializer(claim).data, status=status.HTTP_200_OK)


# ------------------------------------------------------------------------------
# 9. CONSULTAS MÉDICAS Y SIGNOS VITALES
# ------------------------------------------------------------------------------
class MedicalConsultationViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    queryset = MedicalConsultation.objects.select_related('claim', 'doctor').all()
    serializer_class = MedicalConsultationSerializer
    permission_classes = [RoleBasedPermission]

    def perform_create(self, serializer):
        consultation = serializer.save()
        claim = consultation.claim
        claim.status = 'IN_REVIEW'
        claim.requested_amount = consultation.service_cost
        claim.save()


# ------------------------------------------------------------------------------
# 10. GESTIÓN DE SOLICITUDES DE CITAS Y SERVICIOS
# ------------------------------------------------------------------------------
class MedicalAppointmentRequestViewSet(RoleBasedQuerysetMixin, viewsets.ModelViewSet):
    """
    Controlador para la gestión de solicitudes de citas y servicios médicos.

    Flujo operativo:
        1. Recepción de Clínica registra la cita  -> nace 'PENDING' (enviada a Seguros).
        2. Recepción propone agenda (fecha/médico) -> sigue 'PENDING' (agendar-propuesta).
        3. Analista de Seguros dictamina cobertura -> 'SCHEDULED' / 'REJECTED' (dictaminar-cita).
    """
    queryset = MedicalAppointmentRequest.objects.select_related(
        'insured', 'policy', 'clinic', 'clinic_service', 'assigned_doctor', 'reviewed_by'
    ).order_by('-created_at').all()
    serializer_class = MedicalAppointmentRequestSerializer
    permission_classes = [RoleBasedPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'service_type', 'clinic', 'insured']
    search_fields = ['insured__national_id', 'insured__first_name', 'insured__last_name', 'reason_or_symptoms']

    def perform_create(self, serializer):
        user = self.request.user

        # Cliente: la solicitud se registra SIEMPRE a su propio perfil de asegurado.
        # (Se valida por grupo porque la señal post_save crea insured_profile para
        #  todos los usuarios, no solo clientes.)
        if user.groups.filter(name='cliente').exists():
            serializer.validated_data['insured'] = user.insured_profile

        # Recepción: forzar la clínica asignada a su perfil, ignorando lo que envíe el cliente
        clinic = serializer.validated_data.get('clinic')
        if not clinic and hasattr(user, 'clinic_profile') and user.clinic_profile.clinic:
            serializer.validated_data['clinic'] = user.clinic_profile.clinic

        # La cita SIEMPRE nace pendiente de autorización por el Analista de Seguros
        serializer.save(status='PENDING')

    @action(detail=True, methods=['post'], url_path='agendar-propuesta')
    def agendar_propuesta(self, request, pk=None):
        """
        Acción EXCLUSIVA de la Recepción de Clínica:
        propone fecha/hora y médico tratante para la solicitud.
        NO modifica el estado: la aprobación de cobertura es del Analista de Seguros.

        Válida en ambos órdenes del flujo:
          - PENDING:  agenda propuesta previa al dictamen de Seguros.
          - SCHEDULED: la cita ya fue autorizada y la recepción la agenda
                       (o reagenda) con el médico disponible.
        """
        appointment = self.get_object()

        if appointment.status not in ('PENDING', 'SCHEDULED'):
            return Response(
                {"error": "Solo se pueden agendar solicitudes pendientes o ya autorizadas por Seguros."},
                status=status.HTTP_400_BAD_REQUEST
            )

        scheduled_date = request.data.get('scheduled_date')
        assigned_doctor_id = request.data.get('assigned_doctor')
        clinic_notes = request.data.get('clinic_notes')

        if not scheduled_date or not assigned_doctor_id:
            return Response(
                {"error": "La fecha y el médico son obligatorios para proponer la agenda."},
                status=status.HTTP_400_BAD_REQUEST
            )

        doctor = DoctorProfile.objects.filter(id=assigned_doctor_id, is_active=True).first()
        if not doctor:
            return Response(
                {"error": "El médico indicado no existe o no está activo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment.scheduled_date = scheduled_date
        appointment.assigned_doctor = doctor
        if clinic_notes is not None:
            appointment.clinic_notes = clinic_notes
        appointment.save()

        return Response(MedicalAppointmentRequestSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsInsuranceAnalyst], url_path='dictaminar-cita')
    def dictaminar_cita(self, request, pk=None):
        """
        Acción EXCLUSIVA del Analista de Seguros (o Admin/Gerencia):
        autoriza ('SCHEDULED') o rechaza ('REJECTED') la cobertura del servicio,
        validando previamente la vigencia de la póliza del asegurado.
        """
        appointment = self.get_object()
        new_status = request.data.get('status')
        insurance_notes = request.data.get('insurance_notes', '')

        if new_status not in ['SCHEDULED', 'REJECTED']:
            return Response(
                {"error": "El estado debe ser estrictamente 'SCHEDULED' (autorizar) o 'REJECTED' (rechazar)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if appointment.status != 'PENDING':
            return Response(
                {"error": "Solo se pueden dictaminar solicitudes en estado PENDING."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validación de vigencia de póliza
        policy = appointment.policy
        today = timezone.now().date()
        if policy is None or policy.status != 'ACTIVE':
            return Response(
                {"error": f"La póliza asociada no está activa (estado: {policy.status if policy else 'sin póliza'})."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if policy.end_date < today:
            return Response(
                {"error": f"La póliza {policy.policy_number} está vencida desde {policy.end_date}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment.status = new_status
        appointment.insurance_notes = insurance_notes
        appointment.reviewed_by = request.user
        appointment.save()

        return Response(MedicalAppointmentRequestSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post', 'patch'],
        permission_classes=[IsDoctor],
        parser_classes=[MultiPartParser, FormParser],
        url_path='registrar-atencion'
    )
    def registrar_atencion(self, request, pk=None):
        """
        Acción EXCLUSIVA del Médico asignado (o superusuario):
        registra la descripción del servicio / evolución clínica y adjunta
        récipe, informes o exámenes. Opcionalmente finaliza la cita ('COMPLETED').

        Acepta multipart/form-data:
            - doctor_notes: texto clínico
            - doctor_attachment: archivo (PDF/imagen)
            - status: 'COMPLETED' para finalizar la atención
        """
        appointment = self.get_object()

        # El médico solo interactúa con citas autorizadas y agendadas por Seguros
        if appointment.status not in ['SCHEDULED', 'COMPLETED']:
            return Response(
                {"error": "Solo se puede registrar atención en citas autorizadas y agendadas (SCHEDULED)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = request.data.get('status')
        if new_status and new_status != 'COMPLETED':
            return Response(
                {"error": "El único cambio de estado permitido es 'COMPLETED'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        doctor_notes = request.data.get('doctor_notes')
        if doctor_notes is not None:
            appointment.doctor_notes = doctor_notes

        uploaded_file = request.FILES.get('doctor_attachment')
        if uploaded_file:
            appointment.doctor_attachment = uploaded_file

        if new_status == 'COMPLETED':
            effective_notes = doctor_notes if doctor_notes is not None else appointment.doctor_notes
            if not effective_notes:
                return Response(
                    {"error": "Debe registrar la descripción del servicio o evolución clínica antes de completar la cita."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                self._registrar_consumo(appointment, request.data.get('baremo'))
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            appointment.status = 'COMPLETED'

        appointment.save()

        return Response(MedicalAppointmentRequestSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='consumir-servicio',
            permission_classes=[IsReceptionOrAdminManager])
    def consumir_servicio(self, request, pk=None):
        """
        Acción de la RECEPCIÓN DE CLÍNICA (o Admin/Gerencia): cierra el
        proceso de servicios que NO requieren consulta médica (laboratorio,
        rayos X, ecografías...). Es la segunda vía de cierre paralela a la
        del médico: la recepción indica qué ítem del baremo se consumió y
        el motivo; el consumo financiero se genera igual que en el cierre
        del médico (_registrar_consumo).

        Body JSON:
            { "baremo": <id del ClinicBaremo>, "clinic_notes": "<motivo>" }
        """
        appointment = self.get_object()

        if appointment.status != 'SCHEDULED':
            return Response(
                {"error": "Solo los servicios autorizados y agendados (SCHEDULED) pueden consumirse."},
                status=status.HTTP_400_BAD_REQUEST
            )

        baremo_id = request.data.get('baremo')
        motivo = (request.data.get('clinic_notes') or '').strip()

        if not baremo_id:
            return Response({"baremo": ["Selecciona el servicio del baremo que se consumió."]},
                            status=status.HTTP_400_BAD_REQUEST)
        if not motivo:
            return Response({"clinic_notes": ["Indica el motivo o descripción del servicio prestado."]},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            self._registrar_consumo(appointment, baremo_id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        appointment.clinic_notes = motivo
        appointment.status = 'COMPLETED'
        appointment.save()

        return Response(MedicalAppointmentRequestSerializer(appointment).data, status=status.HTTP_200_OK)

    def _registrar_consumo(self, appointment, baremo_id=None):
        """
        Registra el consumo financiero de la atención COMPLETADA:
        1. Resuelve el precio oficial desde el BAREMO de la clínica
           (o el legacy clinic_service si no se indica baremo).
        2. Genera un Claim APPROVED vinculado a la cita (idempotente:
           una sola vez por cita) para que se descuente automáticamente
           del saldo de la póliza vía InsurancePolicy.used_amount.
        """
        # Idempotencia: si ya existe el reclamo de esta cita, no duplicar consumo
        if hasattr(appointment, 'generated_claim') and appointment.generated_claim:
            return appointment.generated_claim

        baremo = None
        amount = None

        if baremo_id:
            baremo = ClinicBaremo.objects.select_related('clinic', 'service').filter(
                id=baremo_id, is_active=True
            ).first()
            if not baremo:
                raise ValueError('El baremo indicado no existe o no está activo.')
            if baremo.clinic_id != appointment.clinic_id:
                raise ValueError('El baremo indicado no pertenece a la clínica de la cita.')

        if baremo:
            amount = baremo.price
        elif appointment.clinic_service:
            amount = appointment.clinic_service.base_cost

        if amount is None or amount <= Decimal('0'):
            # Antes este caso pasaba en silencio: la cita quedaba COMPLETADA
            # pero SIN reclamo ni consumo en la póliza. Ahora es un error
            # explícito para que el médico indique el servicio del baremo.
            raise ValueError(
                'No se pudo determinar el precio oficial de la atención: '
                'indica el servicio realizado según el baremo de la clínica.'
            )

        claim = Claim.objects.create(
            claim_number=f"CITA-{appointment.id}",
            policy=appointment.policy,
            clinic=appointment.clinic,
            clinic_service=appointment.clinic_service,
            baremo=baremo,
            appointment=appointment,
            assigned_doctor=appointment.assigned_doctor,
            incident_date=timezone.now().date(),
            description=(
                f"Atención médica de la cita #{appointment.id}. "
                f"Motivo: {appointment.reason_or_symptoms[:180]}"
            ),
            requested_amount=amount,
            status='APPROVED',  # La cobertura ya fue autorizada por el Analista al pasar a SCHEDULED
            resolution_notes=(appointment.doctor_notes or '')[:500]
        )
        return claim


# ------------------------------------------------------------------------------
# 11. GESTIÓN DE USUARIOS Y ROLES (solo Admin / Gerencia)
# ------------------------------------------------------------------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.prefetch_related('groups').order_by('id')
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrManager]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='me')
    def me(self, request):
        """
        Devuelve los datos del usuario autenticado vía JWT, incluido su rol
        canónico (nombre del grupo). Accesible para CUALQUIER usuario logueado.
        """
        data = UserSerializer(request.user).data
        data['role'] = data.pop('role_display')
        return Response(data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='medicos')
    def medicos(self, request):
        """
        Lista ligera de médicos activos para asignación de citas.
        Accesible para cualquier usuario autenticado (ej. Recepción de Clínica).
        """
        medicos = self.get_queryset().filter(groups__name='medico', is_active=True)
        return Response(UserSerializer(medicos, many=True).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='clientes')
    def clientes(self, request):
        """
        Lista ligera de clientes activos para solicitud de citas.
        Accesible para cualquier usuario autenticado (ej. Recepción de Clínica).
        """
        clientes = self.get_queryset().filter(groups__name='cliente', is_active=True)
        return Response(UserSerializer(clientes, many=True).data)


# ------------------------------------------------------------------------------
# 12. DASHBOARD FINANCIERO GERENCIAL
# ------------------------------------------------------------------------------
def _monto_efectivo_siniestro(claim):
    """
    Monto REAL de un siniestro usando la misma lógica que InsurancePolicy.
    used_amount: si tiene ficha médica manda el costo real de la consulta;
    si no, el precio del servicio contratado; y como último recurso el
    monto reclamado. Así los egresos del reporte cuadran con lo que la
    póliza realmente descontó.
    """
    if hasattr(claim, 'consultation'):
        return claim.consultation.service_cost
    if claim.clinic_service_id:
        return claim.clinic_service.base_cost
    return claim.requested_amount


class FinancialDashboardView(APIView):
    """
    Dashboard financiero EXCLUSIVO para Gerencia / Admin de la aseguradora.

    Responde la pregunta del negocio: ¿cuánto entró, cuánto salió,
    cuánto queda, qué clínica se llevó más dinero y qué clientes
    consumen más/menos su cobertura?
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    def get(self, request):
        # ------------------------------------------------------------------
        # 1) INGRESOS: pagos de pólizas ya verificados por la aseguradora
        # ------------------------------------------------------------------
        ingresos = PolicyPayment.objects.filter(status='APPROVED').aggregate(
            t=Sum('amount'))['t'] or Decimal('0.00')

        # Pagos aún sin verificar: ingreso POTENCIAL que falta confirmar
        pagos_pendientes_qs = PolicyPayment.objects.filter(status='PENDING')
        pagos_pendientes_monto = pagos_pendientes_qs.aggregate(
            t=Sum('amount'))['t'] or Decimal('0.00')

        # ------------------------------------------------------------------
        # 2) EGRESOS: siniestros aprobados con su MONTO EFECTIVO
        # ------------------------------------------------------------------
        aprobados = Claim.objects.filter(status='APPROVED').select_related(
            'clinic', 'clinic_service', 'policy__insured'
        ).prefetch_related('consultation')
        en_proceso = Claim.objects.filter(
            status__in=['PENDING', 'IN_REVIEW']
        ).select_related('clinic_service').prefetch_related('consultation')

        gastos = Decimal('0.00')
        compromiso_pendiente = Decimal('0.00')  # responsabilidad futura

        # Acumuladores por clínica y por cliente (para los rankings)
        gasto_por_clinica = {}
        consumo_por_cliente = {}

        for claim in list(aprobados) + list(en_proceso):
            monto = _monto_efectivo_siniestro(claim)

            if claim.status == 'APPROVED':
                gastos += monto
                fila_clinica = gasto_por_clinica.setdefault(claim.clinic_id, {
                    'id': claim.clinic_id,
                    'nombre': claim.clinic.name,
                    'siniestros': 0,
                    'total_consumido': Decimal('0.00'),
                })
                fila_clinica['siniestros'] += 1
                fila_clinica['total_consumido'] += monto

                asegurado = claim.policy.insured
                fila_cliente = consumo_por_cliente.setdefault(asegurado_id := asegurado.id, {
                    'id': asegurado_id,
                    'nombre': f"{asegurado.first_name} {asegurado.last_name}".strip() or asegurado.national_id,
                    'cedula': asegurado.national_id,
                    'polizas': set(),
                    'cobertura_total': Decimal('0.00'),
                    'consumido': Decimal('0.00'),
                })
                fila_cliente['polizas'].add(claim.policy_id)
                fila_cliente['consumido'] += monto
            else:
                # Pendientes/en revisión: aún no se pagan pero comprometen saldo
                compromiso_pendiente += monto

        # Capital total asegurado en pólizas activas (exposición máxima)
        capital_asegado = InsurancePolicy.objects.filter(status='ACTIVE').aggregate(
            t=Sum('coverage_amount'))['t'] or Decimal('0.00')

        fondo_utilidad = ingresos - gastos
        margen_pct = round(float(fondo_utilidad / ingresos * 100), 1) if ingresos > 0 else None

        # ------------------------------------------------------------------
        # 3.5) REPARTO CON LA RED MÉDICA según ConfiguracionFinanciera
        #
        # La aseguradora paga a cada clínica un % negociado de su propia
        # tarifa (baremo). El resto lo RETIENE la aseguradora. El consumo
        # del asegurado sigue siendo el monto completo: el reparto solo
        # afecta el flujo de caja aseguradora <-> clínica.
        # ------------------------------------------------------------------
        config = ConfiguracionFinanciera.obtener()
        pct_clinica = config.pct_pago_clinica / Decimal('100')
        desembolso_clinicas = (gastos * pct_clinica).quantize(Decimal('0.01'))
        retencion_aseguradora = gastos - desembolso_clinicas

        # Fondo real en caja: capital inicial + primas cobradas - desembolsos
        fondo_disponible = config.fondo_capital + ingresos - desembolso_clinicas

        # Ganancia NETA real de la aseguradora: primas menos lo que
        # efectivamente desembolsa (ya beneficiada por la retención).
        utilidad_neta = ingresos - desembolso_clinicas
        margen_neto_pct = (
            round(float(utilidad_neta / ingresos * 100), 1) if ingresos > 0 else None
        )

        # ------------------------------------------------------------------
        # 3) DESGLOSE POR CLÍNICA ordenado por consumo (mayor primero)
        # ------------------------------------------------------------------
        por_clinica = sorted(gasto_por_clinica.values(),
                             key=lambda c: c['total_consumido'], reverse=True)
        for fila in por_clinica:
            fila['pct_del_gasto'] = round(
                float(fila['total_consumido'] / gastos * 100), 1) if gastos > 0 else 0.0
            # Lo que la clínica realmente cobra según el % negociado
            fila['pago_a_clinica'] = (
                fila['total_consumido'] * pct_clinica
            ).quantize(Decimal('0.01'))

        # ------------------------------------------------------------------
        # 4) RANKING DE CLIENTES: completamos cobertura de sus pólizas
        # ------------------------------------------------------------------
        cobertura_por_cliente = {}
        for poliza in InsurancePolicy.objects.select_related('insured'):
            fila = cobertura_por_cliente.setdefault(poliza.insured_id, Decimal('0.00'))
            cobertura_por_cliente[poliza.insured_id] = fila + poliza.coverage_amount

        def serializar_cliente(datos):
            cobertura = cobertura_por_cliente.get(datos['id'], Decimal('0.00'))
            return {
                'id': datos['id'],
                'nombre': datos['nombre'],
                'cedula': datos['cedula'],
                'polizas': len(datos['polizas']),
                'cobertura_total': cobertura,
                'consumido': datos['consumido'],
                'pct_uso': round(float(datos['consumido'] / cobertura * 100), 1) if cobertura > 0 else 0.0,
            }

        ranking_clientes = sorted(
            [serializar_cliente(c) for c in consumo_por_cliente.values()],
            key=lambda c: c['consumido'], reverse=True)

        return Response({
            "resumen": {
                "ingresos_cobrados": ingresos,
                "pagos_por_verificar_monto": pagos_pendientes_monto,
                "pagos_pendientes_count": pagos_pendientes_qs.count(),
                "gastos_siniestros": gastos,
                "compromiso_pendiente": compromiso_pendiente,
                "siniestros_aprobados_count": len(aprobados),
                "fondo_utilidad": fondo_utilidad,
                "margen_ganancia_pct": margen_pct,
                "capital_asegado": capital_asegado,
                # Reparto con la red médica
                "desembolso_clinicas": desembolso_clinicas,
                "retencion_aseguradora": retencion_aseguradora,
                "fondo_disponible": fondo_disponible,
                "utilidad_neta": utilidad_neta,
                "margen_neto_pct": margen_neto_pct,
            },
            "configuracion": ConfiguracionFinancieraSerializer(config).data,
            "por_clinica": por_clinica,
            "ranking_clientes": ranking_clientes[:10],           # top 10 consumidores
            "clientes_menor_consumo": list(reversed(ranking_clientes[-5:])),  # últimos 5
        })


# ------------------------------------------------------------------------------
# 12.1 CONFIGURACIÓN FINANCIERA (solo Admin/Gerencia)
# ------------------------------------------------------------------------------
class ConfiguracionFinancieraView(APIView):
    """
    Lectura y edición de los parámetros del negocio: fondo de capital y
    % que se le paga a las clínicas de su tarifa. El resto es la retención
    de la aseguradora. Solo Gerencia/Administración.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    def get(self, request):
        return Response(ConfiguracionFinancieraSerializer(
            ConfiguracionFinanciera.obtener()).data)

    def patch(self, request):
        config = ConfiguracionFinanciera.obtener()
        serializer = ConfiguracionFinancieraSerializer(
            config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------------------
# PORTAL DE CLIENTES (Endpoint personalizado)
# ------------------------------------------------------------------------------
class ClientPortalViewSet(viewsets.ViewSet):
    """
    Endpoint exclusivo para que el cliente autenticado consulte y actualice su propio perfil,
    pólizas y siniestros vinculados a su usuario del sistema.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get', 'put', 'patch'])
    def dashboard(self, request):
        user = request.user
        
        if not hasattr(user, 'insured_profile') or not user.insured_profile:
            return Response(
                {"detail": "El usuario actual no tiene un perfil de asegurado asociado."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        insured_profile = user.insured_profile

        # Si la petición es para actualizar datos (PUT o PATCH)
        if request.method in ['PUT', 'PATCH']:
            serializer = InsuredProfileSerializer(
                insured_profile, 
                data=request.data, 
                partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response({
                    "message": "Perfil actualizado exitosamente.",
                    "profile": serializer.data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Si es GET, devolvemos el dashboard completo
        policies = InsurancePolicy.objects.filter(insured=insured_profile)
        claims = Claim.objects.filter(policy__in=policies)

        profile_data = InsuredProfileSerializer(insured_profile).data
        policies_data = InsurancePolicySerializer(policies, many=True).data
        claims_data = ClaimSerializer(claims, many=True).data

        return Response({
            "profile": profile_data,
            "policies": policies_data,
            "claims": claims_data
        })


# ------------------------------------------------------------------------------
# REGISTRO PÚBLICO DE CLIENTES (pantalla de login del frontend)
# ------------------------------------------------------------------------------
class RegistroClienteView(generics.CreateAPIView):
    """
    Endpoint PÚBLICO de auto-registro: POST /api/v1/register/

    Crea cuentas exclusivamente con rol 'cliente' (el serializador fuerza el
    grupo y la señal post_save genera su perfil de asegurado). Cualquier
    intento de enviar otro rol desde el formulario se ignora: los demás roles
    solo los asigna un Admin/Gerente desde el módulo de usuarios.
    """
    queryset = User.objects.all()
    serializer_class = RegistroClienteSerializer
    permission_classes = [permissions.AllowAny]