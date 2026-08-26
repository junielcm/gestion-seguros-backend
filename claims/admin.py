# ==============================================================================
# ARCHIVO: claims/admin.py
# DESCRIPCIÓN: Configuración e personalización del Panel de Administración de Django
#              para la gestión de Clínicas, Baremos, Pólizas, Pagos y Siniestros.
# ==============================================================================

from django.contrib import admin
from .models import (
    DoctorProfile, 
    InsuredProfile, 
    Clinic, 
    ClinicService, 
    ClinicStaffProfile, 
    InsurancePolicy, 
    PolicyPayment, 
    Claim, 
    MedicalConsultation
)


# ------------------------------------------------------------------------------
# 1. PERFILES DE USUARIO Y RED MÉDICA
# ------------------------------------------------------------------------------
@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'specialty', 'license_number', 'is_active')
    search_fields = ('first_name', 'last_name', 'license_number', 'specialty')
    list_filter = ('is_active', 'specialty')


@admin.register(InsuredProfile)
class InsuredProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'national_id', 'first_name', 'last_name', 'email', 'phone', 'is_active')
    search_fields = ('national_id', 'first_name', 'last_name', 'email')
    list_filter = ('is_active',)


# ------------------------------------------------------------------------------
# 2. GESTIÓN DE CLÍNICAS Y BAREMOS DE SERVICIOS
# ------------------------------------------------------------------------------
class ClinicServiceInline(admin.TabularInline):
    """
    Permite visualizar y editar los servicios/baremos directamente 
    desde la vista detallada de la Clínica.
    """
    model = ClinicService
    extra = 1
    fields = ('name', 'base_cost', 'is_available')


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'is_active', 'total_billed')
    search_fields = ('name', 'address', 'phone')
    list_filter = ('is_active',)
    inlines = [ClinicServiceInline]


@admin.register(ClinicService)
class ClinicServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinic', 'name', 'base_cost', 'is_available')
    search_fields = ('name', 'clinic__name')
    list_filter = ('is_available', 'clinic')


@admin.register(ClinicStaffProfile)
class ClinicStaffProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'clinic')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'clinic__name')
    list_filter = ('clinic',)


# ------------------------------------------------------------------------------
# 3. PÓLIZAS Y COBRANZAS
# ------------------------------------------------------------------------------
@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('policy_number', 'insured', 'policy_type', 'coverage_amount', 'used_amount', 'remaining_balance', 'status')
    search_fields = ('policy_number', 'insured__national_id', 'insured__first_name', 'insured__last_name')
    list_filter = ('status', 'policy_type')


@admin.register(PolicyPayment)
class PolicyPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'policy', 'payment_reference', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment_reference', 'policy__policy_number', 'policy__insured__national_id')


# ------------------------------------------------------------------------------
# 4. SINIESTROS Y CONSULTAS MÉDICAS
# ------------------------------------------------------------------------------
@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_number', 'policy', 'clinic', 'clinic_service', 'assigned_doctor', 'requested_amount', 'status', 'created_at')
    list_filter = ('status', 'clinic', 'created_at')
    search_fields = ('claim_number', 'policy__policy_number', 'policy__insured__national_id', 'clinic__name')


@admin.register(MedicalConsultation)
class MedicalConsultationAdmin(admin.ModelAdmin):
    list_display = ('id', 'claim', 'doctor', 'service_cost', 'created_at')
    search_fields = ('claim__claim_number', 'doctor__last_name')
    list_filter = ('created_at',)