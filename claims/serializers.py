# ==============================================================================
# ARCHIVO: claims/serializers.py
# DESCRIPCIÓN: Serializadores para transformación de datos JSON / ORM Django REST,
#             incluyendo JWT personalizado, Clínicas, Baremos, Siniestros y Citas.
# ==============================================================================

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from decimal import Decimal

# Importación de todos los modelos del módulo de seguros y clínicas
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
    MedicalAppointmentRequest,  # <--- NUEVO MODELO IMPORTADO
    ConfiguracionFinanciera
)


# ------------------------------------------------------------------------------
# 1. SERIALIZADOR DE AUTENTICACIÓN JWT PERSONALIZADO
# ------------------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Personaliza la respuesta del Login JWT inyectando el rol del usuario
    y el ID/nombre de la clínica si el usuario pertenece al personal de recepción.
    """
    @classmethod
    def get_token(cls, user):
        # Genera el token JWT base
        token = super().get_token(user)

        # Determinar rol según superusuario o grupos canónicos (SYSTEM_ROLES)
        token['username'] = user.username
        token['email'] = user.email
        token['role'] = cls._resolve_role(user)

        return token

    @staticmethod
    def _resolve_role(user):
        """
        Resuelve el rol del usuario a partir de sus grupos canónicos.
        Devuelve una etiqueta legible para claims del token.
        """
        ROLE_CLAIMS = {
            'admin': 'ADMIN',
            'gerente': 'MANAGER',
            'analistaseguro': 'ANALYST',
            'medico': 'DOCTOR',
            'recepcionclinica': 'CLINIC_STAFF',
            'corredorseguro': 'BROKER',
            'cliente': 'CLIENT',
        }
        if user.is_superuser:
            return 'ADMIN'
        for group_name in user.groups.values_list('name', flat=True):
            if group_name in ROLE_CLAIMS:
                return ROLE_CLAIMS[group_name]
        return 'CLIENT'

    def validate(self, attrs):
        # Valida credenciales estándar (username y password)
        data = super().validate(attrs)

        # Identificar rol del usuario (grupos canónicos SYSTEM_ROLES)
        role = self._resolve_role(self.user)

        # Datos básicos del usuario en la respuesta JSON
        user_data = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'role': role,
            'clinic_id': None,
            'clinic_name': None
        }

        # Si el usuario es de recepción, adjuntar la clínica a la que está asignado
        if role == 'CLINIC_STAFF' and hasattr(self.user, 'clinic_profile'):
            user_data['clinic_id'] = self.user.clinic_profile.clinic.id
            user_data['clinic_name'] = self.user.clinic_profile.clinic.name

        data['user'] = user_data
        return data


# ------------------------------------------------------------------------------
# 2. SERIALIZADOR DE PERFILES MÉDICOS
# ------------------------------------------------------------------------------
class DoctorProfileSerializer(serializers.ModelSerializer):
    """
    Serializa la información de los médicos especialistas.
    """
    class Meta:
        model = DoctorProfile
        fields = '__all__'


# ------------------------------------------------------------------------------
# 3. SERIALIZADOR DE ASEGURADOS (Actualizado con indicadores)
# ------------------------------------------------------------------------------
class InsuredProfileSerializer(serializers.ModelSerializer):
    """
    Serializa la información personal de los titulares de pólizas.
    Incluye propiedades calculadas para verificar pólizas activas y cédulas temporales.
    """
    has_active_policy = serializers.SerializerMethodField()
    is_temporary_id = serializers.SerializerMethodField()

    class Meta:
        model = InsuredProfile
        fields = [
            'id',
            'national_id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'is_active',
            'created_at',
            'has_active_policy',
            'is_temporary_id'
        ]

    def get_has_active_policy(self, obj):
        return InsurancePolicy.objects.filter(insured=obj, status='ACTIVE').exists()

    def get_is_temporary_id(self, obj):
        return obj.national_id.startswith("V-0")


# ------------------------------------------------------------------------------
# 4. SERIALIZADOR DE SERVICIOS / BAREMOS DE CLÍNICAS
# ------------------------------------------------------------------------------
class ClinicServiceSerializer(serializers.ModelSerializer):
    """
    Serializa los servicios/exámenes aprobados con sus costos base por clínica.
    """
    clinic_name = serializers.ReadOnlyField(source='clinic.name')

    class Meta:
        model = ClinicService
        fields = ['id', 'clinic', 'clinic_name', 'name', 'description', 'base_cost', 'is_available']


# ------------------------------------------------------------------------------
# 5. SERIALIZADOR DE CLÍNICAS Y CENTROS MÉDICOS
# ------------------------------------------------------------------------------
class ClinicSerializer(serializers.ModelSerializer):
    """
    Serializa las clínicas afiliadas. Incluye la propiedad calculada 'total_billed'
    para reportes de consumo y la lista de sus servicios disponibles.
    """
    total_billed = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    services = ClinicServiceSerializer(many=True, read_only=True)

    class Meta:
        model = Clinic
        fields = ['id', 'name', 'rif', 'email', 'address', 'phone', 'is_active', 'total_billed', 'services', 'created_at']


# ------------------------------------------------------------------------------
# 5B. SERIALIZADORES DE RED MÉDICA (Catálogo y Baremos)
# ------------------------------------------------------------------------------
class MedicalServiceSerializer(serializers.ModelSerializer):
    """
    Serializa el catálogo maestro de servicios médicos.
    """
    class Meta:
        model = MedicalService
        fields = ['id', 'name', 'description', 'is_active', 'created_at']


class ClinicBaremoSerializer(serializers.ModelSerializer):
    """
    Serializa el tarifario de un servicio del catálogo en una clínica específica.
    Los precios se expresan SIEMPRE en dólares (USD): el campo 'currency'
    lo hace explícito para cualquier consumidor de la API.
    """
    service_name = serializers.ReadOnlyField(source='service.name')
    service_description = serializers.ReadOnlyField(source='service.description')
    clinic_name = serializers.ReadOnlyField(source='clinic.name')
    currency = serializers.SerializerMethodField()

    class Meta:
        model = ClinicBaremo
        fields = [
            'id',
            'clinic',
            'clinic_name',
            'service',
            'service_name',
            'service_description',
            'price',
            'currency',
            'is_active',
            'created_at',
            'updated_at'
        ]

    def get_currency(self, obj):
        return ClinicBaremo.CURRENCY  # 'USD'

    def validate(self, attrs):
        """
        Reglas del baremo:
        1. Precio estrictamente positivo.
        2. Unicidad de servicio por clínica con mensaje claro.
        """
        price = attrs.get('price')
        if price is not None and price <= Decimal('0'):
            raise serializers.ValidationError({'price': 'El precio debe ser mayor a cero.'})

        clinic = attrs.get('clinic') or getattr(self.instance, 'clinic', None)
        service = attrs.get('service') or getattr(self.instance, 'service', None)

        if clinic and service:
            qs = ClinicBaremo.objects.filter(clinic=clinic, service=service)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'service': 'Este servicio ya tiene precio asignado en el baremo de esta clínica.'}
                )

        return attrs


# ------------------------------------------------------------------------------
# 6. SERIALIZADOR DE PERSONAL DE RECEPCIÓN
# ------------------------------------------------------------------------------
class ClinicStaffProfileSerializer(serializers.ModelSerializer):
    """
    Serializa la vinculación entre un usuario de sistema y su centro médico asignado.
    """
    clinic_name = serializers.ReadOnlyField(source='clinic.name')
    username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = ClinicStaffProfile
        fields = ['id', 'user', 'username', 'clinic', 'clinic_name']


# ------------------------------------------------------------------------------
# 7. SERIALIZADOR DE PÓLIZAS DE SEGURO
# ------------------------------------------------------------------------------
class InsurancePolicySerializer(serializers.ModelSerializer):
    """
    Serializa las pólizas activas. Expone 'used_amount' y 'remaining_balance'
    calculados dinámicamente desde el modelo en tiempo real.
    """
    insured_detail = InsuredProfileSerializer(source='insured', read_only=True)
    used_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InsurancePolicy
        fields = [
            'id', 
            'policy_number', 
            'insured', 
            'insured_detail', 
            'policy_type', 
            'coverage_amount', 
            'used_amount', 
            'remaining_balance', 
            'start_date', 
            'end_date', 
            'status', 
            'created_at'
        ]


# ------------------------------------------------------------------------------
# 8. SERIALIZADOR DE PAGOS DE PÓLIZA
# ------------------------------------------------------------------------------
class PolicyPaymentSerializer(serializers.ModelSerializer):
    """
    Serializa los pagos de primas e ingresos registrados por los asegurados.

    BLINDAJE:
    - 'status' y 'verification_notes' son SOLO LECTURA: ningún cliente puede
      colarse un pago directamente como APPROVED. Todo pago nace PENDING y
      solo el endpoint POST /pagos/{id}/verificar/ (Analista/Gerencia) lo
      dictamina.
    - validate_policy impide que un cliente registre pagos sobre pólizas ajenas.
    """
    policy_number = serializers.ReadOnlyField(source='policy.policy_number')
    # Nombre legible del titular para las bandejas de verificación
    asegurado = serializers.SerializerMethodField()

    class Meta:
        model = PolicyPayment
        fields = [
            'id',
            'policy',
            'policy_number',
            'asegurado',
            'amount',
            'payment_reference',
            'receipt_file',
            'status',
            'verification_notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['status', 'verification_notes']

    def get_asegurado(self, obj):
        perfil = obj.policy.insured
        return f'{perfil.first_name} {perfil.last_name}'.strip() or perfil.national_id

    def validate_policy(self, value):
        """Un cliente solo puede registrar comprobantes sobre SUS pólizas."""
        user = self.context['request'].user
        es_cliente = (
            user.groups.filter(name='cliente').exists()
            or (not user.groups.exists() and hasattr(user, 'insured_profile'))
        )
        if es_cliente:
            if not hasattr(user, 'insured_profile'):
                raise serializers.ValidationError(
                    'No tienes un perfil de asegurado asociado.')
            if value.insured_id != user.insured_profile.id:
                raise serializers.ValidationError(
                    'Solo puedes registrar pagos sobre tus propias pólizas.')
        return value


# ------------------------------------------------------------------------------
# 9. SERIALIZADOR DE SINIESTROS / RECLAMOS
# ------------------------------------------------------------------------------
class ClaimSerializer(serializers.ModelSerializer):
    """
    Serializa la apertura y seguimiento de reclamos. Incluye relaciones anidadas
    de lectura para la UI de Recepción, Médicos y Analistas.
    """
    clinic_name = serializers.ReadOnlyField(source='clinic.name')
    service_name = serializers.ReadOnlyField(source='clinic_service.name')
    doctor_name = serializers.SerializerMethodField()
    insured_name = serializers.SerializerMethodField()
    policy_number = serializers.ReadOnlyField(source='policy.policy_number')

    class Meta:
        model = Claim
        fields = [
            'id', 
            'claim_number', 
            'policy', 
            'policy_number', 
            'insured_name', 
            'clinic', 
            'clinic_name', 
            'clinic_service', 
            'service_name', 
            'assigned_doctor', 
            'doctor_name',
            # Cita origen: presente cuando el siniestro fue auto-generado al
            # completarse una cita médica (None en reclamos creados a mano).
            'appointment', 
            'incident_date', 
            'description', 
            'requested_amount', 
            'status', 
            'resolution_notes', 
            'created_at', 
            'updated_at'
        ]

    def get_doctor_name(self, obj):
        if obj.assigned_doctor:
            return f"Dr. {obj.assigned_doctor.first_name} {obj.assigned_doctor.last_name}"
        return "Sin asignar"

    def get_insured_name(self, obj):
        if obj.policy and obj.policy.insured:
            return f"{obj.policy.insured.first_name} {obj.policy.insured.last_name}"
        return "N/A"


# ------------------------------------------------------------------------------
# 10. SERIALIZADOR DE CONSULTAS MÉDICAS
# ------------------------------------------------------------------------------
class MedicalConsultationSerializer(serializers.ModelSerializer):
    """
    Serializa las fichas de atención e informes diagnósticos del médico tratante.
    """
    claim_number = serializers.ReadOnlyField(source='claim.claim_number')
    doctor_name = serializers.SerializerMethodField()

    class Meta:
        model = MedicalConsultation
        fields = [
            'id', 
            'claim', 
            'claim_number', 
            'doctor', 
            'doctor_name', 
            'high_pressure', 
            'low_pressure', 
            'temperature', 
            'weight', 
            'height', 
            'diagnosis_report', 
            'service_cost', 
            'created_at', 
            'updated_at'
        ]

    def get_doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}"


# ------------------------------------------------------------------------------
# 11. SERIALIZADOR DE SOLICITUDES DE CITAS Y SERVICIOS
# ------------------------------------------------------------------------------
class MedicalAppointmentRequestSerializer(serializers.ModelSerializer):
    """
    Serializa las solicitudes de citas y servicios médicos generadas por los clientes
    y gestionadas por el personal de la clínica.
    """
    insured_name = serializers.SerializerMethodField()
    insured_national_id = serializers.ReadOnlyField(source='insured.national_id')
    policy_number = serializers.ReadOnlyField(source='policy.policy_number')
    clinic_name = serializers.ReadOnlyField(source='clinic.name')
    service_name = serializers.SerializerMethodField()
    doctor_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Datos del reclamo auto-generado cuando la cita fue COMPLETADA por el médico
    # (None si la cita aún no finaliza o no generó consumo). Se usan SerializerMethodField
    # porque 'generated_claim' es la relación inversa OneToOne y puede no existir.
    generated_claim_number = serializers.SerializerMethodField()
    generated_claim_amount = serializers.SerializerMethodField()
    # Opcionales en la entrada: el backend los resuelve/valida según el rol
    # (el cliente NUNCA debe enviarlos; se fuerzan con su propio perfil).
    insured = serializers.PrimaryKeyRelatedField(
        queryset=InsuredProfile.objects.all(), required=False, allow_null=True
    )
    policy = serializers.PrimaryKeyRelatedField(
        queryset=InsurancePolicy.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = MedicalAppointmentRequest
        fields = [
            'id',
            'insured',
            'insured_name',
            'insured_national_id',
            'policy',
            'policy_number',
            'clinic',
            'clinic_name',
            'clinic_service',
            'service_name',
            'service_type',
            'service_type_display',
            'reason_or_symptoms',
            'notes_attachment',
            'status',
            'status_display',
            'scheduled_date',
            'assigned_doctor',
            'doctor_name',
            'clinic_notes',
            'insurance_notes',
            'reviewed_by',
            'reviewed_by_name',
            'doctor_notes',
            'doctor_attachment',
            'generated_claim_number',
            'generated_claim_amount',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['status', 'insurance_notes', 'reviewed_by', 'doctor_notes', 'doctor_attachment']

    def get_generated_claim_number(self, obj):
        # OJO: en una relación OneToOne inversa, acceder a 'generated_claim'
        # cuando NO existe lanza RelatedObjectDoesNotExist (no devuelve None).
        try:
            return obj.generated_claim.claim_number
        except ObjectDoesNotExist:
            return None

    def get_generated_claim_amount(self, obj):
        try:
            return obj.generated_claim.requested_amount
        except ObjectDoesNotExist:
            return None

    def get_insured_name(self, obj):
        if obj.insured:
            return f"{obj.insured.first_name} {obj.insured.last_name}"
        return "N/A"

    def get_service_name(self, obj):
        if obj.clinic_service:
            return obj.clinic_service.name
        return "Consulta / Servicio General"

    def get_doctor_name(self, obj):
        if obj.assigned_doctor:
            return f"Dr. {obj.assigned_doctor.first_name} {obj.assigned_doctor.last_name}"
        return "Sin asignar"

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}".strip() or obj.reviewed_by.username
        return None

    def validate(self, attrs):
        """
        Reglas de negocio para la creación/edición de solicitudes:
        1. Cliente autenticado: se fuerza SU perfil de asegurado y SU póliza
           activa, ignorando cualquier 'insured'/'policy' enviado (anti-IDOR).
           Esto ocurre AQUÍ y no en perform_create porque la resolución de la
           póliza debe basarse en el asegurado definitivo.
        2. Recepción/otros roles: la póliza debe pertenecer al asegurado
           indicado; si falta, se resuelve la póliza ACTIVA y vigente.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # Solo en creación (no al editar parcialmente)
        if self.instance is None:
            is_cliente = (
                user is not None
                and user.is_authenticated
                and user.groups.filter(name='cliente').exists()
            )

            if is_cliente:
                if not hasattr(user, 'insured_profile'):
                    raise serializers.ValidationError(
                        {'insured': 'Tu usuario no tiene un perfil de asegurado asociado.'}
                    )

                attrs['insured'] = user.insured_profile
                attrs.pop('policy', None)  # ignora cualquier póliza enviada

                today = timezone.now().date()
                active_policy = InsurancePolicy.objects.filter(
                    insured=user.insured_profile,
                    status='ACTIVE',
                    start_date__lte=today,
                    end_date__gte=today
                ).order_by('-end_date').first()

                if not active_policy:
                    raise serializers.ValidationError(
                        {'policy': 'No tienes una póliza activa y vigente para solicitar este servicio.'}
                    )
                attrs['policy'] = active_policy
            else:
                insured = attrs.get('insured')
                policy = attrs.get('policy')

                if policy and insured and policy.insured_id != insured.id:
                    raise serializers.ValidationError(
                        {'policy': 'La póliza indicada no pertenece al asegurado seleccionado.'}
                    )

                if not policy and insured:
                    today = timezone.now().date()
                    active_policy = InsurancePolicy.objects.filter(
                        insured=insured,
                        status='ACTIVE',
                        start_date__lte=today,
                        end_date__gte=today
                    ).order_by('-end_date').first()

                    if not active_policy:
                        raise serializers.ValidationError(
                            {'policy': 'El asegurado no tiene una póliza activa y vigente. No se puede registrar la cita.'}
                        )
                    attrs['policy'] = active_policy

        return attrs


# ------------------------------------------------------------------------------
# 12. SERIALIZADOR DE GESTIÓN DE USUARIOS Y ROLES (Actualizado con Clínica)
# ------------------------------------------------------------------------------
SYSTEM_ROLES = [
    'admin',
    'gerente',
    'analistaseguro',
    'medico',
    'recepcionclinica',
    'corredorseguro',
    'cliente'
]


class UserSerializer(serializers.ModelSerializer):
    """
    Serializa los usuarios del sistema para el módulo de administración.
    Expone 'role_display', 'clinic_id' y 'assigned_clinic' para gestionar la 
    asignación de personal de recepción a una clínica directamente.
    """
    role_display = serializers.SerializerMethodField()
    role = serializers.CharField(required=False, write_only=True)
    password = serializers.CharField(write_only=True, required=False)
    
    # Nuevos campos para asociar y consultar la clínica si es recepcionista
    clinic_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    assigned_clinic = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'role_display',
            'clinic_id',
            'assigned_clinic',
            'is_staff',
            'is_superuser',
            'password'
        ]
        read_only_fields = ['is_staff', 'is_superuser']

    def get_role_display(self, obj):
        user_groups = list(obj.groups.values_list('name', flat=True))
        for role in SYSTEM_ROLES:
            if role in user_groups:
                return role
        if obj.is_superuser:
            return 'admin'
        return 'Sin rol'

    def get_assigned_clinic(self, obj):
        if hasattr(obj, 'clinic_profile') and obj.clinic_profile.clinic:
            return {
                'id': obj.clinic_profile.clinic.id,
                'name': obj.clinic_profile.clinic.name
            }
        return None

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError(
                {'password': 'La contraseña es obligatoria para nuevos usuarios.'}
            )
        return attrs

    def _apply_role(self, user, role_name):
        if role_name not in SYSTEM_ROLES:
            user.groups.clear()
            return
        group, _ = Group.objects.get_or_create(name=role_name)
        user.groups.set([group])
        staff_flag = (role_name == 'admin')
        if user.is_staff != staff_flag:
            user.is_staff = staff_flag
            user.save(update_fields=['is_staff'])

        # Al asignar el rol 'medico', crear y vincular automáticamente su DoctorProfile
        if role_name == 'medico' and not hasattr(user, 'doctor_profile'):
            DoctorProfile.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': user.first_name or user.username,
                    'last_name': user.last_name or 'Por Definir',
                    'specialty': 'Medicina General',
                    'license_number': f'TEMP-{user.id}',
                }
            )

    def _apply_clinic_profile(self, user, role_name, clinic_id):
        """
        Gestiona la creación o actualización del perfil de recepción si el rol es recepcionclinica.
        """
        if role_name == 'recepcionclinica' and clinic_id:
            try:
                clinic = Clinic.objects.get(id=clinic_id)
                ClinicStaffProfile.objects.update_or_create(
                    user=user,
                    defaults={'clinic': clinic}
                )
            except Clinic.DoesNotExist:
                raise serializers.ValidationError({'clinic_id': 'La clínica especificada no existe.'})
        else:
            if role_name and role_name != 'recepcionclinica':
                ClinicStaffProfile.objects.filter(user=user).delete()

    def create(self, validated_data):
        role_name = validated_data.pop('role', None)
        clinic_id = validated_data.pop('clinic_id', None)
        password = validated_data.pop('password')
        
        user = User.objects.create_user(password=password, **validated_data)
        
        if role_name:
            self._apply_role(user, role_name)
        
        self._apply_clinic_profile(user, role_name, clinic_id)
        return user

    def update(self, instance, validated_data):
        role_name = validated_data.pop('role', None)
        clinic_id = validated_data.pop('clinic_id', None)
        password = validated_data.pop('password', '')
        
        user = super().update(instance, validated_data)
        
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
            
        if role_name is not None:
            self._apply_role(user, role_name)
        
        current_role = role_name if role_name is not None else self.get_role_display(user)
        self._apply_clinic_profile(user, current_role, clinic_id)
        
        return user

# ------------------------------------------------------------------------------
# 13. SERIALIZADOR DE AUTO-REGISTRO PÚBLICO (pantalla de login)
# ------------------------------------------------------------------------------
class RegistroClienteSerializer(serializers.ModelSerializer):
    """
    Serializador del registro público desde la pantalla de login.

    REGLA DE SEGURIDAD: toda cuenta creada aquí es SIEMPRE rol 'cliente'.
    El endpoint es anónimo, así que aunque alguien enviara un campo 'role'
    en el formulario, se ignora: los demás roles solo los puede asignar un
    Admin/Gerente desde el módulo de usuarios.
    """
    password = serializers.CharField(
        write_only=True,
        min_length=6,  # demo: misma regla que AUTH_PASSWORD_VALIDATORS
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']
        extra_kwargs = {
            # El formulario solo envía username/email/password; nombres opcionales
            'first_name': {'required': False, 'allow_blank': True},
            'last_name': {'required': False, 'allow_blank': True},
        }

    def validate_email(self, value):
        """Evita cuentas duplicadas por correo (User.email no es único a nivel BD)."""
        if not value:
            raise serializers.ValidationError('El correo electrónico es obligatorio.')
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe una cuenta con este correo.')
        return value

    def validate_password(self, value):
        """Aplica las reglas de contraseñas configuradas en settings.py."""
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)

        # Rol fijo: todo auto-registro nace como cliente.
        # (La señal post_save además crea su InsuredProfile automáticamente.)
        grupo_cliente, _ = Group.objects.get_or_create(name='cliente')
        user.groups.add(grupo_cliente)
        return user


# ------------------------------------------------------------------------------
# 14. SERIALIZADOR DE CONFIGURACIÓN FINANCIERA (solo Admin/Gerencia)
# ------------------------------------------------------------------------------
class ConfiguracionFinancieraSerializer(serializers.ModelSerializer):
    """
    Serializa los parámetros del negocio editables por Gerencia:
    fondo de capital y % de pago a clínicas. La retención de la
    aseguradora se expone calculada (100% - pago clínica).
    """
    pct_retencion_aseguradora = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )

    class Meta:
        model = ConfiguracionFinanciera
        fields = [
            'fondo_capital',
            'pct_pago_clinica',
            'pct_retencion_aseguradora',
            'updated_at'
        ]
        read_only_fields = ['updated_at']

    def validate_pct_pago_clinica(self, value):
        """El % de pago a clínicas debe estar entre 0 y 100."""
        if value < 0 or value > 100:
            raise serializers.ValidationError(
                'El porcentaje de pago a clínicas debe estar entre 0 y 100.'
            )
        return value

    def validate_fondo_capital(self, value):
        """El fondo no puede ser negativo."""
        if value < 0:
            raise serializers.ValidationError('El fondo de capital no puede ser negativo.')
        return value
