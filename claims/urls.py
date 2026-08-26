# ==============================================================================
# ARCHIVO: claims/urls.py
# DESCRIPCIÓN: Configuración de rutas (Endpoints API) para el módulo de Siniestros.
#              Mapea los ViewSets al router rest_framework y expone la API.
# ==============================================================================

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DoctorProfileViewSet,
    InsuredProfileViewSet,
    ClinicViewSet,
    ClinicServiceViewSet,
    ClinicStaffProfileViewSet,
    MedicalServiceViewSet,
    ClinicBaremoViewSet,
    InsurancePolicyViewSet,
    PolicyPaymentViewSet,
    ClaimViewSet,
    MedicalConsultationViewSet,
    MedicalAppointmentRequestViewSet,
    FinancialDashboardView,
    ConfiguracionFinancieraView,
    UserViewSet,
    ClientPortalViewSet
)

# Inicialización del router de DRF
router = DefaultRouter()

# Enrutamiento de entidades de red médica y usuarios
router.register(r'medicos', DoctorProfileViewSet, basename='doctor')
router.register(r'asegurados', InsuredProfileViewSet, basename='insured')
router.register(r'clinicas', ClinicViewSet, basename='clinic')
router.register(r'servicios-clinica', ClinicServiceViewSet, basename='clinicservice')
router.register(r'personal-recepcion', ClinicStaffProfileViewSet, basename='clinicstaff')
router.register(r'usuarios', UserViewSet, basename='usuario')

# Gestión de Red Médica: catálogo global y tarifarios por clínica
router.register(r'servicios-medicos', MedicalServiceViewSet, basename='medicalservice')
router.register(r'baremos', ClinicBaremoViewSet, basename='baremo')

# Enrutamiento de procesos de aseguradora
router.register(r'polizas', InsurancePolicyViewSet, basename='policy')
router.register(r'pagos', PolicyPaymentViewSet, basename='policypayment')
router.register(r'siniestros', ClaimViewSet, basename='claim')
router.register(r'consultas-medicas', MedicalConsultationViewSet, basename='medicalconsultation')
router.register(r'citas', MedicalAppointmentRequestViewSet, basename='appointmentrequest')

# Enrutamiento de perfil de usuario
router.register(r'cliente', ClientPortalViewSet, basename='client-portal')

# Definición de URLs principales de la App
urlpatterns = [
    # Rutas generadas automáticamente por el Router (CRUDs y acciones personalizadas)
    path('', include(router.urls)),
    
    # Endpoint independiente para la APIView del Dashboard Financiero
    path('finanzas/dashboard/', FinancialDashboardView.as_view(), name='financial-dashboard'),
    # Parámetros del negocio (fondo de capital y % de pago a clínicas)
    path('finanzas/configuracion/', ConfiguracionFinancieraView.as_view(), name='financial-config'),
]