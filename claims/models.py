# ==============================================================================
# ARCHIVO: claims/models.py
# DESCRIPCIÓN: Modelos de datos para la gestión de pólizas, asegurados, médicos,
#              clínicas, servicios/baremos, siniestros y consultas médicas.
# ==============================================================================

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver


# ------------------------------------------------------------------------------
# 1. PERFIL DE MÉDICOS
# ------------------------------------------------------------------------------
class DoctorProfile(models.Model):
    """
    Perfil profesional del médico especialista que atiende a los asegurados.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_profile",
        verbose_name="Usuario Asociado"
    )
    first_name = models.CharField(max_length=100, verbose_name="Nombres")
    last_name = models.CharField(max_length=100, verbose_name="Apellidos")
    specialty = models.CharField(max_length=100, verbose_name="Especialidad")
    license_number = models.CharField(max_length=50, unique=True, verbose_name="Nº Colegiado / Licencia")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name} ({self.specialty})"

    class Meta:
        verbose_name = "Médico"
        verbose_name_plural = "Médicos"
        ordering = ['last_name', 'first_name']  # listado alfabético estable


# ------------------------------------------------------------------------------
# 2. PERFIL DE ASEGURADOS
# ------------------------------------------------------------------------------
class InsuredProfile(models.Model):
    """
    Perfil del asegurado o titular de la póliza.
    """
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="insured_profile", 
        null=True, 
        blank=True,
        verbose_name="Usuario Asociado"
    )
    first_name = models.CharField(max_length=100, verbose_name="Nombres")
    last_name = models.CharField(max_length=100, verbose_name="Apellidos")
    national_id = models.CharField(max_length=20, unique=True, verbose_name="Cédula / DNI")
    email = models.EmailField(unique=True, verbose_name="Correo Electrónico")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    address = models.TextField(blank=True, null=True, verbose_name="Dirección")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.national_id} - {self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "Asegurado"
        verbose_name_plural = "Asegurados"
        ordering = ['last_name', 'first_name']  # listado alfabético estable


# ------------------------------------------------------------------------------
# 3. CLÍNICAS / CENTROS MÉDICOS
# ------------------------------------------------------------------------------
class Clinic(models.Model):
    """
    Clínica o centro de atención médica prestador de servicios en convenio.
    """
    name = models.CharField(max_length=150, verbose_name="Nombre del Centro Médico")
    rif = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="RIF / Identificación Fiscal"
    )
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    address = models.TextField(verbose_name="Dirección")
    phone = models.CharField(max_length=20, verbose_name="Teléfono")
    is_active = models.BooleanField(default=True, verbose_name="Activa")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_billed(self):
        """
        Calcula el consumo total/facturado por la clínica sumando los
        siniestros que han sido APROBADOS en este centro médico.
        """
        approved_claims = self.claims.filter(status='APPROVED')
        total = Decimal('0.00')
        for claim in approved_claims:
            if hasattr(claim, 'consultation'):
                total += claim.consultation.service_cost
            elif claim.clinic_service:
                total += claim.clinic_service.base_cost
            else:
                total += claim.requested_amount
        return total

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Clínica"
        verbose_name_plural = "Clínicas"
        ordering = ['name']  # catálogo alfabético (paginación consistente)


# ------------------------------------------------------------------------------
# 4. SERVICIOS Y BAREMOS DE CLÍNICAS
# ------------------------------------------------------------------------------
class ClinicService(models.Model):
    """
    Catálogo/baremo de servicios aprobados por la aseguradora para cada clínica.
    Cargados masivamente por el Analista de la Aseguradora.
    """
    clinic = models.ForeignKey(
        Clinic, 
        on_delete=models.CASCADE, 
        related_name="services", 
        verbose_name="Clínica"
    )
    name = models.CharField(max_length=100, verbose_name="Nombre del Servicio / Examen / Consulta")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    base_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))], 
        verbose_name="Costo Base / Baremo ($)"
    )
    is_available = models.BooleanField(default=True, verbose_name="Disponible")

    def __str__(self):
        return f"{self.clinic.name} - {self.name} (${self.base_cost})"

    class Meta:
        verbose_name = "Servicio de Clínica"
        verbose_name_plural = "Servicios de Clínicas"
        ordering = ['clinic', 'name']  # agrupado por clínica y alfabético


# ------------------------------------------------------------------------------
# 4B. CATÁLOGO GLOBAL DE SERVICIOS MÉDICOS
# ------------------------------------------------------------------------------
class MedicalService(models.Model):
    """
    Catálogo maestro de servicios médicos (ej. Consulta General, Laboratorio,
    Ecografía). Es la base sobre la que cada clínica define su precio en el baremo.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Servicio")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo en Catálogo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Servicio Médico (Catálogo)"
        verbose_name_plural = "Catálogo de Servicios Médicos"
        ordering = ['name']


# ------------------------------------------------------------------------------
# 4C. BAREMO: TARIFARIO DE UN SERVICIO EN UNA CLÍNICA
# ------------------------------------------------------------------------------
class ClinicBaremo(models.Model):
    """
    Precio de un servicio del catálogo global en una clínica específica.
    Es la tarifa oficial usada para calcular el consumo contra la póliza.

    CONVENCIÓN MONETARIA: todos los precios del baremo se expresan
    explícitamente en DÓLARES AMERICANOS (USD / $).
    """
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='baremos',
        verbose_name="Clínica"
    )
    service = models.ForeignKey(
        MedicalService,
        on_delete=models.CASCADE,
        related_name='baremos',
        verbose_name="Servicio del Catálogo"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Precio en esta Clínica (USD)",
        help_text="Tarifa oficial en dólares americanos (USD). Se descuenta del saldo de la póliza."
    )
    is_active = models.BooleanField(default=True, verbose_name="Disponible")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    CURRENCY = 'USD'  # Moneda única y explícita del tarifario

    def __str__(self):
        return f"{self.clinic.name} - {self.service.name}: ${self.price} USD"

    class Meta:
        verbose_name = "Baremo de Clínica"
        verbose_name_plural = "Baremos por Clínica"
        unique_together = ('clinic', 'service')
        ordering = ['clinic__name', 'service__name']  # lectura natural del tarifario


# ------------------------------------------------------------------------------
# 5. VÍNCULO DE RECEPCIÓN CON CLÍNICA
# ------------------------------------------------------------------------------
class ClinicStaffProfile(models.Model):
    """
    Asocia un usuario con rol de Recepción a una clínica específica.
    """
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="clinic_profile", 
        verbose_name="Usuario Recepción"
    )
    clinic = models.ForeignKey(
        Clinic, 
        on_delete=models.CASCADE, 
        related_name="staff_members", 
        verbose_name="Clínica Asignada"
    )

    def __str__(self):
        return f"{self.user.username} -> {self.clinic.name}"

    class Meta:
        verbose_name = "Personal de Recepción"
        verbose_name_plural = "Personal de Recepción"
        ordering = ['id']  # orden estable para paginación


# ------------------------------------------------------------------------------
# 6. PÓLIZAS DE SEGURO Y CÁLCULO DE COBERTURA
# ------------------------------------------------------------------------------
class InsurancePolicy(models.Model):
    """
    Póliza de seguro contratada por el asegurado. Mantiene el saldo de cobertura.
    """
    POLICY_TYPES = [
        ('HEALTH', 'Salud / Maternidad'),
        ('VEHICLE', 'Automóvil'),
        ('LIFE', 'Vida'),
        ('PROPERTY', 'Patrimonial'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Activa'),
        ('EXPIRED', 'Vencida'),
        ('SUSPENDED', 'Suspendida'),
    ]

    policy_number = models.CharField(max_length=50, unique=True, verbose_name="Número de Póliza")
    insured = models.ForeignKey(
        InsuredProfile, 
        on_delete=models.CASCADE, 
        related_name="policies", 
        verbose_name="Asegurado"
    )
    policy_type = models.CharField(
        max_length=20, 
        choices=POLICY_TYPES, 
        default='HEALTH', 
        verbose_name="Tipo de Cobertura"
    )
    coverage_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))], 
        verbose_name="Monto Cobertura ($)"
    )
    start_date = models.DateField(verbose_name="Fecha de Inicio")
    end_date = models.DateField(verbose_name="Fecha de Vencimiento")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='ACTIVE', 
        verbose_name="Estado"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def used_amount(self):
        """
        Monto acumulado consumido por el cliente. Considera siniestros
        APROBADOS, PENDIENTES o EN REVISIÓN para no permitir sobre-consumo.
        """
        active_claims = self.claims.filter(status__in=['APPROVED', 'IN_REVIEW', 'PENDING'])
        total = Decimal('0.00')
        for claim in active_claims:
            if hasattr(claim, 'consultation'):
                total += claim.consultation.service_cost
            elif claim.clinic_service:
                total += claim.clinic_service.base_cost
            else:
                total += claim.requested_amount
        return total

    @property
    def remaining_balance(self):
        """
        Monto disponible restante de la póliza para nuevas atenciones.
        """
        return max(Decimal('0.00'), self.coverage_amount - self.used_amount)

    def __str__(self):
        return f"{self.policy_number} - {self.insured} (Disponible: ${self.remaining_balance})"

    class Meta:
        verbose_name = "Póliza"
        verbose_name_plural = "Pólizas"
        ordering = ['-created_at']  # las más recientes primero


# ------------------------------------------------------------------------------
# 7. PAGOS DE PÓLIZAS
# ------------------------------------------------------------------------------
class PolicyPayment(models.Model):
    """
    Registro y archivo del pago emitido por el cliente para adquirir/renovar la póliza.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Verificación'),
        ('APPROVED', 'Aprobado'),
        ('REJECTED', 'Rechazado'),
    ]

    policy = models.ForeignKey(
        InsurancePolicy, 
        on_delete=models.CASCADE, 
        related_name="payments", 
        verbose_name="Póliza"
    )
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))], 
        verbose_name="Monto Pagado ($)"
    )
    payment_reference = models.CharField(max_length=100, verbose_name="Número de Referencia")
    receipt_file = models.FileField(upload_to='receipts/%Y/%m/', verbose_name="Comprobante (Imagen/PDF)")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING', 
        verbose_name="Estado Verificación"
    )
    verification_notes = models.TextField(blank=True, null=True, verbose_name="Notas de Verificación")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pago #{self.id} - Ref: {self.payment_reference} (${self.amount})"

    class Meta:
        verbose_name = "Pago de Póliza"
        verbose_name_plural = "Pagos de Pólizas"
        ordering = ['-created_at']  # los más recientes primero


# ------------------------------------------------------------------------------
# 7.5 CONFIGURACIÓN FINANCIERA DE LA ASEGURADORA (registro ÚNICO)
# ------------------------------------------------------------------------------
class ConfiguracionFinanciera(models.Model):
    """
    Parámetros del negocio que solo Gerencia/Admin pueden ajustar:

    - fondo_capital: colchón de capital con el que opera la aseguradora
      (en la vida real lo exige el ente regulador de seguros).

    - pct_pago_clinica: porcentaje de SU PROPIA tarifa (baremo) que la
      aseguradora le paga efectivamente a la clínica por cada siniestro.
      Las aseguradoras reales negocian tarifas preferenciales con su red
      médica: ej. 80% significa que si el baremo dice $100, la clínica
      recibe $80 y la aseguradora RETIENE $20.

    Es un registro ÚNICO (singleton): usar siempre ConfiguracionFinanciera.obtener().
    """
    fondo_capital = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Fondo de Capital ($)"
    )
    pct_pago_clinica = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="% de Pago a Clínicas"
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def obtener(cls):
        """Devuelve la configuración única, creándola con valores por defecto."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    @property
    def pct_retencion_aseguradora(self):
        """Lo que la aseguradora retiene de cada tarifa (100% - pago clínica)."""
        return Decimal('100.00') - self.pct_pago_clinica

    def __str__(self):
        return f"Config Financiera: fondo ${self.fondo_capital} / clínicas {self.pct_pago_clinica}%"

    class Meta:
        verbose_name = "Configuración Financiera"
        verbose_name_plural = "Configuración Financiera"


# ------------------------------------------------------------------------------
# 8. SINIESTROS / RECLAMOS
# ------------------------------------------------------------------------------
class Claim(models.Model):
    """
    Solicitud de atención o siniestro generada en recepción o por el cliente.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Atención'),
        ('IN_REVIEW', 'En Auditoría Médica'),
        ('APPROVED', 'Aprobado'),
        ('REJECTED', 'Rechazado'),
    ]

    claim_number = models.CharField(max_length=50, unique=True, verbose_name="Código de Reclamo")
    policy = models.ForeignKey(
        InsurancePolicy, 
        on_delete=models.CASCADE, 
        related_name="claims", 
        verbose_name="Póliza"
    )
    clinic = models.ForeignKey(
        Clinic, 
        on_delete=models.CASCADE, 
        related_name="claims", 
        verbose_name="Clínica Atendente"
    )
    clinic_service = models.ForeignKey(
        ClinicService, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="claims", 
        verbose_name="Servicio Requerido"
    )
    baremo = models.ForeignKey(
        ClinicBaremo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='claims',
        verbose_name="Baremo Aplicado"
    )
    appointment = models.OneToOneField(
        'MedicalAppointmentRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_claim',
        verbose_name="Cita Origen"
    )
    assigned_doctor = models.ForeignKey(
        DoctorProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="assigned_claims", 
        verbose_name="Médico Asignado"
    )
    incident_date = models.DateField(verbose_name="Fecha del Siniestro")
    description = models.TextField(verbose_name="Motivo de Atención / Descripción")
    requested_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        validators=[MinValueValidator(Decimal('0.00'))], 
        verbose_name="Monto Reclamado ($)"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING', 
        verbose_name="Estado Solicitud"
    )
    resolution_notes = models.TextField(blank=True, null=True, verbose_name="Notas de Resolución")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.clinic_service and self.requested_amount == Decimal('0.00'):
            self.requested_amount = self.clinic_service.base_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reclamo #{self.claim_number} [{self.get_status_display()}]"

    class Meta:
        verbose_name = "Siniestro / Reclamo"
        verbose_name_plural = "Siniestros / Reclamos"
        ordering = ['-created_at']  # los más recientes primero


# ------------------------------------------------------------------------------
# 9. CONSULTA MÉDICA / FICHA DE ATENCIÓN
# ------------------------------------------------------------------------------
class MedicalConsultation(models.Model):
    """
    Ficha médica llenada por el médico asignado durante la consulta.
    """
    claim = models.OneToOneField(
        Claim, 
        on_delete=models.CASCADE, 
        related_name="consultation", 
        verbose_name="Siniestro"
    )
    doctor = models.ForeignKey(
        DoctorProfile, 
        on_delete=models.CASCADE, 
        related_name="consultations", 
        verbose_name="Médico Tratante"
    )
    
    # Signos Vitales
    high_pressure = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Presión Alta (mmHg)")
    low_pressure = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Presión Baja (mmHg)")
    temperature = models.DecimalField(max_digits=4, decimal_places=1, verbose_name="Temperatura (°C)")
    weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Peso (kg)")
    height = models.DecimalField(max_digits=4, decimal_places=2, verbose_name="Altura (m)")
    
    # Informe Diagnóstico y Honorarios
    diagnosis_report = models.TextField(verbose_name="Informe Diagnóstico / Tratamiento")
    service_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))], 
        verbose_name="Costo del Servicio ($)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Consulta #{self.id} - Reclamo #{self.claim.claim_number}"

    class Meta:
        verbose_name = "Consulta Médica"
        verbose_name_plural = "Consultas Médicas"
        ordering = ['-created_at']  # las más recientes primero


# ------------------------------------------------------------------------------
# 10. SOLICITUDES DE CITAS Y SERVICIOS MÉDICOS
# ------------------------------------------------------------------------------
class MedicalAppointmentRequest(models.Model):
    """
    Solicitudes de citas o servicios médicos (Consulta, Rayos X, Laboratorio) 
    realizadas por el cliente hacia una clínica específica, gestionadas por la recepción.
    """
    SERVICE_TYPES = [
        ('CONSULTATION', 'Consulta Médica'),
        ('XRAY', 'Rayos X / Imagenología'),
        ('LAB', 'Laboratorio / Exámenes'),
        ('OTHER', 'Otro Servicio'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Autorización (Seguros)'),
        ('SCHEDULED', 'Autorizada y Agendada'),
        ('REJECTED', 'Rechazada por Seguros'),
        ('COMPLETED', 'Completada'),
        ('CANCELLED', 'Cancelada'),
    ]

    insured = models.ForeignKey(
        InsuredProfile, 
        on_delete=models.CASCADE, 
        related_name="appointment_requests",
        verbose_name="Asegurado"
    )
    policy = models.ForeignKey(
        InsurancePolicy, 
        on_delete=models.CASCADE, 
        related_name="appointment_requests",
        verbose_name="Póliza Utilizada"
    )
    clinic = models.ForeignKey(
        Clinic, 
        on_delete=models.CASCADE, 
        related_name="appointment_requests",
        verbose_name="Clínica Destino"
    )
    clinic_service = models.ForeignKey(
        ClinicService,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_requests",
        verbose_name="Servicio Específico del Baremo"
    )
    
    service_type = models.CharField(
        max_length=30, 
        choices=SERVICE_TYPES, 
        default='CONSULTATION',
        verbose_name="Tipo de Servicio"
    )
    reason_or_symptoms = models.TextField(verbose_name="Motivo o Síntomas / Descripción")
    notes_attachment = models.FileField(
        upload_to='medical_requests/%Y/%m/', 
        blank=True, 
        null=True, 
        verbose_name="Récipe u Orden Médica (Opcional)"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING',
        verbose_name="Estado de la Solicitud"
    )
    
    # Campos que llena la recepción / clínica al agendar
    scheduled_date = models.DateTimeField(blank=True, null=True, verbose_name="Fecha y Hora de la Cita")
    assigned_doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_appointments",
        verbose_name="Médico Asignado"
    )
    clinic_notes = models.TextField(blank=True, null=True, verbose_name="Observaciones de la Clínica")
    insurance_notes = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Dictamen / Observaciones del Analista de Seguros"
    )
    doctor_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descripción del Servicio / Evolución Clínica"
    )
    doctor_attachment = models.FileField(
        upload_to='medical_requests/doctor/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Récipe / Informe / Exámenes (Adjunto del Médico)"
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments_reviewed',
        verbose_name="Analista que Dictaminó"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_service_type_display()} - {self.insured} [{self.get_status_display()}]"

    class Meta:
        verbose_name = "Solicitud de Cita / Servicio"
        verbose_name_plural = "Solicitudes de Citas y Servicios"
        ordering = ['-created_at']  # las más recientes primero


# ------------------------------------------------------------------------------
# 11. SEÑAL: CREACIÓN AUTOMÁTICA DE PERFIL DE ASEGURADO AL CREAR USUARIO
# ------------------------------------------------------------------------------
@receiver(post_save, sender=User)
def create_insured_profile_automatic(sender, instance, created, **kwargs):
    """
    Crea automáticamente un InsuredProfile SOLO cuando el usuario nuevo tiene
    el grupo 'cliente' (o no tiene ningún grupo asignado). Esto evita que
    médicos, recepcionistas, analistas y gerentes tengan perfiles de asegurado
    innecesarios que ensucian las vistas de Asegurados y las citas.
    """
    if created:
        es_cliente = (
            instance.groups.filter(name='cliente').exists()
            or not instance.groups.exists()
        )
        if es_cliente and not hasattr(instance, 'insured_profile'):
            InsuredProfile.objects.create(
                user=instance,
                national_id=f"V-{instance.id:08d}",
                first_name=instance.first_name if instance.first_name else instance.username,
                last_name=instance.last_name if instance.last_name else "Por Definir",
                email=instance.email if instance.email else f"usuario_{instance.id}@gestionseguros.local",
                is_active=True
            )