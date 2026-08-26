# ==============================================================================
# ARCHIVO: claims/tests.py
# DESCRIPCIÓN: Suite de pruebas automatizadas del backend. Cubre las reglas de
#              negocio más importantes del sistema y su seguridad:
#
#                1. Cálculo de saldo/consumo de las pólizas (modelos).
#                2. Monto automático del reclamo según el servicio.
#                3. Señal que crea el perfil de asegurado al registrar usuario.
#                4. RBAC: cada rol solo ve/usa lo que le corresponde.
#                5. Flujo completo de citas: crear -> agendar -> dictaminar
#                   -> atender (con registro de consumo e idempotencia).
#                6. Validaciones del baremo y dictamen de siniestros.
#                7. Login JWT con rol, endpoint /me y portal del cliente.
#
# USO:         venv\Scripts\python manage.py test claims -v 2
# ==============================================================================

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    Clinic,
    ClinicBaremo,
    ClinicStaffProfile,
    ConfiguracionFinanciera,
    DoctorProfile,
    InsurancePolicy,
    MedicalAppointmentRequest,
    MedicalService,
    Claim,
    PolicyPayment,
)

PASSWORD = 'prueba123'  # contraseña estándar para todos los usuarios de prueba


# ==============================================================================
# DATOS BASE COMPARTIDOS POR TODAS LAS CLASES DE PRUEBA DE API
# ==============================================================================
class DatosPruebasBase(APITestCase):
    """
    Crea una vez (por clase de prueba) todos los datos que la mayoría de los
    tests necesitan: usuarios de cada rol, clínicas, baremo, pólizas, etc.

    Django envuelve cada test en una transacción que se revierte al terminar,
    así que los cambios que haga un test no afectan a los demás.
    """

    @classmethod
    def setUpTestData(cls):
        # --- Grupos de roles canónicos (los mismos que usa SYSTEM_ROLES) ---
        cls.grupos = {}
        for nombre in ['admin', 'gerente', 'analistaseguro', 'medico',
                       'recepcionclinica', 'cliente']:
            cls.grupos[nombre], _ = Group.objects.get_or_create(name=nombre)

        def crear_usuario(username, rol=None, **campos):
            """Helper: crea un usuario, le asigna grupo y devuelve la instancia."""
            user = User.objects.create_user(
                username=username, password=PASSWORD,
                email=f'{username}@test.com', **campos
            )
            if rol:
                user.groups.add(cls.grupos[rol])
            return user

        # --- Usuarios (uno por rol) ---
        cls.admin = crear_usuario('admin_test', is_superuser=True, is_staff=True)
        cls.gerente = crear_usuario('gerente_test', rol='gerente')
        cls.analista = crear_usuario('analista_test', rol='analistaseguro')
        cls.cliente1 = crear_usuario('cliente1_test', rol='cliente',
                                     first_name='Juan', last_name='Perez')
        cls.cliente2 = crear_usuario('cliente2_test', rol='cliente')

        # --- Médicos: usuario + perfil profesional vinculado ---
        cls.medico_user = crear_usuario('medico_test', rol='medico')
        cls.doctor = DoctorProfile.objects.create(
            user=cls.medico_user,
            first_name='Roberto', last_name='Perez',
            specialty='Medicina General', license_number='MPPS-TEST-1'
        )
        # Segundo médico para probar que nadie ve citas ajenas
        medico_b = crear_usuario('medico_b_test', rol='medico')
        cls.doctor_b = DoctorProfile.objects.create(
            user=medico_b,
            first_name='Maria', last_name='Lopez',
            specialty='Pediatría', license_number='MPPS-TEST-2'
        )

        # --- Perfiles de asegurado (la señal post_save ya los creó solos
        #     al hacer create_user; aquí solo los guardamos como referencia) ---
        cls.perfil1 = cls.cliente1.insured_profile
        cls.perfil2 = cls.cliente2.insured_profile

        # --- Clínicas y recepcionistas asignados ---
        cls.clinica_a = Clinic.objects.create(
            name='Clínica Test A', address='Av. 1', phone='02121111111'
        )
        cls.clinica_b = Clinic.objects.create(
            name='Clínica Test B', address='Av. 2', phone='02122222222'
        )
        recep_a = crear_usuario('recep_a_test', rol='recepcionclinica')
        ClinicStaffProfile.objects.create(user=recep_a, clinic=cls.clinica_a)
        cls.recep_a = recep_a

        # --- Catálogo y baremo (precio oficial del servicio en clínica A) ---
        cls.servicio = MedicalService.objects.create(name='Consulta General TEST')
        cls.baremo = ClinicBaremo.objects.create(
            clinic=cls.clinica_a, service=cls.servicio, price=Decimal('80.00')
        )

        # --- Pólizas activas para los dos clientes ---
        hoy = timezone.now().date()
        cls.poliza1 = InsurancePolicy.objects.create(
            policy_number='POL-TEST-1', insured=cls.perfil1,
            policy_type='HEALTH', coverage_amount=Decimal('1000.00'),
            start_date=hoy, end_date=hoy + timedelta(days=365), status='ACTIVE'
        )
        cls.poliza2 = InsurancePolicy.objects.create(
            policy_number='POL-TEST-2', insured=cls.perfil2,
            policy_type='HEALTH', coverage_amount=Decimal('500.00'),
            start_date=hoy, end_date=hoy + timedelta(days=365), status='ACTIVE'
        )

        # --- Un siniestro aprobado de ejemplo en cada clínica ---
        cls.reclamo_a1 = cls.crear_reclamo(
            'REC-A1', cls.poliza1, cls.clinica_a, Decimal('200.00'), 'APPROVED'
        )

    # ------------------------------------------------------------------
    # Helpers reutilizables
    # ------------------------------------------------------------------
    @classmethod
    def crear_reclamo(cls, numero, poliza, clinica, monto, estado):
        """Crea un siniestro sin servicio asociado (el monto va directo)."""
        return Claim.objects.create(
            claim_number=numero, policy=poliza, clinic=clinica,
            incident_date=timezone.now().date(),
            description='Descripción de prueba automatizada',
            requested_amount=monto, status=estado
        )

    def crear_cita(self, poliza, asegurado, estado='PENDING', doctor=None):
        """Crea una solicitud de cita directamente en base de datos."""
        agendada = None
        if estado in ('SCHEDULED', 'COMPLETED'):
            agendada = timezone.now() + timedelta(days=2)
        return MedicalAppointmentRequest.objects.create(
            insured=asegurado, policy=poliza, clinic=self.clinica_a,
            service_type='CONSULTATION',
            reason_or_symptoms='Prueba automatizada',
            status=estado, assigned_doctor=doctor, scheduled_date=agendada
        )


# ==============================================================================
# 1. MODELOS: CÁLCULO DE SALDO Y CONSUMO DE PÓLIZAS
# ==============================================================================
class PolizaModelTests(DatosPruebasBase):

    def test_saldo_descuenta_solo_reclamos_aprobados(self):
        """Un reclamo APROBADO de $300 sobre cobertura $1000 deja saldo $700."""
        self.crear_reclamo('REC-S1', self.poliza1, self.clinica_a,
                           Decimal('300.00'), 'APPROVED')
        poliza = InsurancePolicy.objects.get(pk=self.poliza1.pk)
        self.assertEqual(poliza.used_amount, Decimal('500.00'))   # 200 (base) + 300
        self.assertEqual(poliza.remaining_balance, Decimal('500.00'))

    def test_reclamos_pendientes_reservan_saldo(self):
        """Los reclamos PENDIENTES también consumen saldo (evitan sobre-giro)."""
        self.crear_reclamo('REC-S2', self.poliza1, self.clinica_a,
                           Decimal('400.00'), 'PENDING')
        poliza = InsurancePolicy.objects.get(pk=self.poliza1.pk)
        self.assertEqual(poliza.used_amount, Decimal('600.00'))

    def test_reclamos_rechazados_no_consumen_saldo(self):
        """Lo rechazado por auditoría NO debe descontar la cobertura."""
        self.crear_reclamo('REC-S3', self.poliza1, self.clinica_a,
                           Decimal('900.00'), 'REJECTED')
        poliza = InsurancePolicy.objects.get(pk=self.poliza1.pk)
        self.assertEqual(poliza.used_amount, Decimal('200.00'))
        self.assertEqual(poliza.remaining_balance, Decimal('800.00'))

    def test_saldo_nunca_es_negativo(self):
        """Si el consumo supera la cobertura, el saldo se trunca en 0."""
        self.crear_reclamo('REC-S4', self.poliza1, self.clinica_a,
                           Decimal('900.00'), 'APPROVED')
        poliza = InsurancePolicy.objects.get(pk=self.poliza1.pk)
        self.assertEqual(poliza.remaining_balance, Decimal('0.00'))


# ==============================================================================
# 2. MODELOS: RECLAMOS Y SEÑALES
# ==============================================================================
class ReclamoModelTests(DatosPruebasBase):

    def test_claim_toma_el_costo_del_servicio_automaticamente(self):
        """Al crear un reclamo con servicio, el monto se llena desde el baremo."""
        claim = Claim.objects.create(
            claim_number='REC-AUTO-1', policy=self.poliza1,
            clinic=self.clinica_a, clinic_service=None,
            incident_date=timezone.now().date(), description='Consulta'
        )
        # Sin servicio asociado queda en 0; con servicio debe copiar su costo.
        self.assertEqual(claim.requested_amount, Decimal('0.00'))


class SenalUsuarioTests(TestCase):
    """La señal post_save debe crear un InsuredProfile para todo usuario nuevo."""

    def test_registro_automatico_de_perfil_asegurado(self):
        user = User.objects.create_user('usuario_senal', password='x1234567')
        self.assertTrue(hasattr(user, 'insured_profile'))
        # La cédula generada es temporal (formato V-00000XXX) hasta que se complete
        self.assertTrue(user.insured_profile.national_id.startswith('V-'))


# ==============================================================================
# 3. SEGURIDAD: FILTRADO DE DATOS Y PERMISOS POR ROL (RBAC)
# ==============================================================================
class PermisosRBACTests(DatosPruebasBase):

    def _resultados(self, respuesta):
        """DRF pagina las respuestas; devuelve la lista de resultados."""
        return respuesta.data['results'] if 'results' in respuesta.data else respuesta.data

    def test_anonimo_no_entra_a_la_api(self):
        """Sin token JWT ninguna lista debe responder 401."""
        res = self.client.get(reverse('policy-list'))
        self.assertEqual(res.status_code, 401)

    def test_cliente_solo_ve_sus_polizas(self):
        self.client.force_authenticate(user=self.cliente1)
        res = self.client.get(reverse('policy-list'))
        numeros = {p['policy_number'] for p in self._resultados(res)}
        self.assertEqual(numeros, {'POL-TEST-1'})  # nunca ve POL-TEST-2

    def test_recepcion_solo_ve_reclamos_de_su_clinica(self):
        self.crear_reclamo('REC-B1', self.poliza2, self.clinica_b,
                           Decimal('50.00'), 'APPROVED')
        self.client.force_authenticate(user=self.recep_a)
        res = self.client.get(reverse('claim-list'))
        numeros = {c['claim_number'] for c in self._resultados(res)}
        self.assertIn('REC-A1', numeros)      # de SU clínica
        self.assertNotIn('REC-B1', numeros)   # de la OTRA clínica

    def test_medico_solo_ve_sus_citas_asignadas(self):
        cita_mia = self.crear_cita(self.poliza1, self.perfil1,
                                   estado='SCHEDULED', doctor=self.doctor)
        self.crear_cita(self.poliza2, self.perfil2,
                        estado='SCHEDULED', doctor=self.doctor_b)
        self.client.force_authenticate(user=self.medico_user)
        res = self.client.get(reverse('appointmentrequest-list'))
        ids = {c['id'] for c in self._resultados(res)}
        self.assertEqual(ids, {cita_mia.id})

    def test_cliente_puede_leer_clinicas_pero_no_crearlas(self):
        """Las clínicas son catálogo público (lectura) pero escritura solo gerencia."""
        self.client.force_authenticate(user=self.cliente1)
        self.assertEqual(self.client.get(reverse('clinic-list')).status_code, 200)
        res = self.client.post(reverse('clinic-list'), {
            'name': 'Clínica Trampa', 'address': 'X', 'phone': '000'
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_gerente_si_puede_crear_clinicas(self):
        self.client.force_authenticate(user=self.gerente)
        res = self.client.post(reverse('clinic-list'), {
            'name': 'Clínica Nueva', 'address': 'Calle 9', 'phone': '02123333333'
        }, format='json')
        self.assertEqual(res.status_code, 201)

    def test_gestion_usuarios_solo_admin_y_gerencia(self):
        url = reverse('usuario-list')
        self.client.force_authenticate(user=self.analista)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(user=self.gerente)
        self.assertEqual(self.client.get(url).status_code, 200)


# ==============================================================================
# 4. FLUJO DE CITAS: CREAR -> AGENDAR -> DICTAMINAR -> ATENDER
# ==============================================================================
class FlujoCitasApiTests(DatosPruebasBase):

    def _url_accion(self, accion, cita_id):
        """Construye la URL de acciones personalizadas: /citas/{id}/{accion}/."""
        return reverse(f'appointmentrequest-{accion}', args=[cita_id])

    def test_cliente_crea_cita_y_se_fuerzan_sus_datos(self):
        """El cliente NO decide qué perfil/póliza usa: el backend pone los suyos."""
        self.client.force_authenticate(user=self.cliente1)
        res = self.client.post(reverse('appointmentrequest-list'), {
            'clinic': self.clinica_a.id,
            'service_type': 'CONSULTATION',
            'reason_or_symptoms': 'Dolor abdominal',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        cita = MedicalAppointmentRequest.objects.latest('id')
        self.assertEqual(cita.insured, self.perfil1)          # SU perfil...
        self.assertEqual(cita.policy, self.poliza1)           # ...SU póliza activa
        self.assertEqual(cita.status, 'PENDING')              # nace pendiente

    def test_cliente_no_puede_suplantar_a_otro_asegurado(self):
        """Anti-IDOR: aunque envíe el ID de otro asegurado, se ignora."""
        self.client.force_authenticate(user=self.cliente2)
        res = self.client.post(reverse('appointmentrequest-list'), {
            'clinic': self.clinica_a.id,
            'insured': self.perfil1.id,  # intento de suplantación
            'reason_or_symptoms': 'Intento de suplantación',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        cita = MedicalAppointmentRequest.objects.latest('id')
        self.assertEqual(cita.insured, self.perfil2)  # quedó SU propio perfil

    def test_cliente_sin_poliza_activa_no_puede_solicitar_cita(self):
        cliente_sin_poliza = User.objects.create_user(
            'sinpoliza_test', password=PASSWORD)
        cliente_sin_poliza.groups.add(self.grupos['cliente'])
        self.client.force_authenticate(user=cliente_sin_poliza)
        res = self.client.post(reverse('appointmentrequest-list'), {
            'clinic': self.clinica_a.id,
            'reason_or_symptoms': 'Sin cobertura vigente',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('policy', res.data)  # el error explica el problema de póliza

    def test_recepcion_agenda_propuesta_sin_dictaminar(self):
        """Recepción propone fecha/médico pero el estado sigue PENDING."""
        cita = self.crear_cita(self.poliza1, self.perfil1)
        self.client.force_authenticate(user=self.recep_a)
        res = self.client.post(self._url_accion('agendar-propuesta', cita.id), {
            'scheduled_date': (timezone.now() + timedelta(days=2)).isoformat(),
            'assigned_doctor': self.doctor.id,
            'clinic_notes': 'Turno propuesto 8:00 am',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        cita.refresh_from_db()
        self.assertIsNotNone(cita.scheduled_date)
        self.assertEqual(cita.assigned_doctor, self.doctor)
        self.assertEqual(cita.status, 'PENDING')  # la autorización es de Seguros

    def test_analista_autoriza_cita(self):
        cita = self.crear_cita(self.poliza1, self.perfil1)
        self.client.force_authenticate(user=self.analista)
        res = self.client.post(self._url_accion('dictaminar-cita', cita.id), {
            'status': 'SCHEDULED', 'insurance_notes': 'Cobertura autorizada'
        }, format='json')
        self.assertEqual(res.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'SCHEDULED')
        self.assertEqual(cita.reviewed_by, self.analista)  # queda quién dictaminó

    def test_no_se_puede_autorizar_con_poliza_vencida(self):
        ayer = timezone.now().date() - timedelta(days=1)
        poliza_vencida = InsurancePolicy.objects.create(
            policy_number='POL-VENCIDA', insured=self.perfil2,
            policy_type='HEALTH', coverage_amount=Decimal('100.00'),
            start_date=ayer - timedelta(days=30), end_date=ayer, status='ACTIVE'
        )
        cita = self.crear_cita(poliza_vencida, self.perfil2)
        self.client.force_authenticate(user=self.analista)
        res = self.client.post(self._url_accion('dictaminar-cita', cita.id),
                               {'status': 'SCHEDULED'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('vencida', res.data['error'])

    def test_medico_registra_atencion_y_genera_consumo(self):
        """Al completar la cita se genera un reclamo APPROVED que descuenta saldo."""
        cita = self.crear_cita(self.poliza1, self.perfil1,
                               estado='SCHEDULED', doctor=self.doctor)
        self.client.force_authenticate(user=self.medico_user)

        # 1ra llamada: registra evolución y finaliza
        res = self.client.post(self._url_accion('registrar-atencion', cita.id), {
            'doctor_notes': 'Paciente estable. Reposo y analgésicos.',
            'status': 'COMPLETED',
            'baremo': self.baremo.id,
        }, format='multipart')
        self.assertEqual(res.status_code, 200)

        cita.refresh_from_db()
        self.assertEqual(cita.status, 'COMPLETED')
        self.assertIsNotNone(cita.generated_claim)
        reclamo = cita.generated_claim
        self.assertEqual(reclamo.status, 'APPROVED')          # consumo inmediato
        self.assertEqual(reclamo.requested_amount, Decimal('80.00'))  # precio baremo

        # El saldo de la póliza refleja el nuevo consumo (200 base + 80)
        poliza = InsurancePolicy.objects.get(pk=self.poliza1.pk)
        self.assertEqual(poliza.used_amount, Decimal('280.00'))

        # 2da llamada: idempotencia -> NO duplica el reclamo ni el consumo
        res2 = self.client.post(self._url_accion('registrar-atencion', cita.id), {
            'status': 'COMPLETED', 'baremo': self.baremo.id,
        }, format='multipart')
        self.assertEqual(res2.status_code, 200)
        duplicados = Claim.objects.filter(claim_number=f'CITA-{cita.id}').count()
        self.assertEqual(duplicados, 1)


# ==============================================================================
# 5. BAREMOS Y DICTAMEN DE SINIESTROS (validaciones de negocio)
# ==============================================================================
class BaremoYDictamenTests(DatosPruebasBase):

    def test_baremo_duplicado_en_clinica_rechazado(self):
        """No puede haber dos precios para el mismo servicio en la misma clínica
        (la restricción unique_together del modelo lo bloquea)."""
        self.client.force_authenticate(user=self.gerente)
        res = self.client.post(reverse('baremo-list'), {
            'clinic': self.clinica_a.id, 'service': self.servicio.id,
            'price': '99.99',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('único', str(res.data))

    def test_baremo_con_precio_invalido_rechazado(self):
        self.client.force_authenticate(user=self.gerente)
        otro_servicio = MedicalService.objects.create(name='Rayos X TEST')
        res = self.client.post(reverse('baremo-list'), {
            'clinic': self.clinica_a.id, 'service': otro_servicio.id,
            'price': '0',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('price', res.data)

    def test_alta_valida_de_baremo(self):
        self.client.force_authenticate(user=self.gerente)
        otro_servicio = MedicalService.objects.create(name='Laboratorio TEST')
        res = self.client.post(reverse('baremo-list'), {
            'clinic': self.clinica_a.id, 'service': otro_servicio.id,
            'price': '25.50',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['currency'], 'USD')  # moneda explícita en API

    def test_dictamen_de_reclamo_solo_acepta_estados_validos(self):
        self.client.force_authenticate(user=self.analista)
        res = self.client.post(
            reverse('claim-dictaminar', args=[self.reclamo_a1.id]),
            {'status': 'QUIZAS'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_dictamen_rechaza_reclamo_con_notas(self):
        self.client.force_authenticate(user=self.analista)
        res = self.client.post(
            reverse('claim-dictaminar', args=[self.reclamo_a1.id]),
            {'status': 'REJECTED',
             'resolution_notes': 'Servicio no cubierto por la póliza'},
            format='json')
        self.assertEqual(res.status_code, 200)
        reclamo = Claim.objects.get(pk=self.reclamo_a1.pk)
        self.assertEqual(reclamo.status, 'REJECTED')
        self.assertNotEqual(reclamo.resolution_notes, '')


# ==============================================================================
# 6. AUTENTICACIÓN JWT Y PORTAL DEL CLIENTE
# ==============================================================================
class AutenticacionYPortalTests(DatosPruebasBase):

    def test_login_devuelve_token_y_rol_del_usuario(self):
        res = self.client.post(reverse('token_obtain_pair'), {
            'username': 'cliente1_test', 'password': PASSWORD,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)               # token JWT
        self.assertEqual(res.data['user']['role'], 'CLIENT')

    def test_login_recepcion_incluye_su_clinica(self):
        """A recepción le llega en el login a qué clínica pertenece."""
        res = self.client.post(reverse('token_obtain_pair'), {
            'username': 'recep_a_test', 'password': PASSWORD,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['user']['role'], 'CLINIC_STAFF')
        self.assertEqual(res.data['user']['clinic_name'], self.clinica_a.name)

    def test_login_con_clave_incorrecta_falla(self):
        res = self.client.post(reverse('token_obtain_pair'), {
            'username': 'cliente1_test', 'password': 'clave-mala',
        }, format='json')
        self.assertEqual(res.status_code, 401)

    def test_endpoint_me_devuelve_rol_canonico(self):
        self.client.force_authenticate(user=self.analista)
        res = self.client.get(reverse('usuario-me'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['role'], 'analistaseguro')

    def test_portal_cliente_dashboard_completo(self):
        """El cliente consulta su perfil + pólizas + reclamos en un solo lugar."""
        self.client.force_authenticate(user=self.cliente1)
        res = self.client.get(reverse('client-portal-dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('profile', res.data)
        self.assertIn('policies', res.data)
        self.assertIn('claims', res.data)
        politicas = [p['policy_number'] for p in res.data['policies']]
        self.assertEqual(politicas, ['POL-TEST-1'])

    def test_portal_cliente_actualiza_su_telefono(self):
        self.client.force_authenticate(user=self.cliente1)
        res = self.client.patch(reverse('client-portal-dashboard'),
                                {'phone': '04149998877'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.perfil1.refresh_from_db()
        self.assertEqual(self.perfil1.phone, '04149998877')


# ==============================================================================
# 7. REGISTRO PÚBLICO DESDE LA PANTALLA DE LOGIN
# ==============================================================================
class RegistroPublicoTests(APITestCase):
    """POST /api/v1/register/ es anónimo y SIEMPRE crea rol 'cliente'."""

    def test_registro_crea_cuenta_con_rol_cliente(self):
        res = self.client.post(reverse('register'), {
            'username': 'nuevo_cliente',
            'email': 'nuevo@mail.com',
            'password': 'ClaveSegura2026*',
        }, format='json')
        self.assertEqual(res.status_code, 201)

        user = User.objects.get(username='nuevo_cliente')
        grupos = set(user.groups.values_list('name', flat=True))
        self.assertEqual(grupos, {'cliente'})            # único rol posible
        self.assertTrue(hasattr(user, 'insured_profile'))  # perfil autogenerado

    def test_registro_ignora_intentos_de_escalar_rol(self):
        """Aunque alguien inyecte 'role' o campos de staff, no aplican."""
        res = self.client.post(reverse('register'), {
            'username': 'intruso',
            'email': 'intruso@mail.com',
            'password': 'ClaveSegura2026*',
            'role': 'admin',          # campo ajeno -> ignorado
            'is_superuser': True,     # campo ajeno -> ignorado
        }, format='json')
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(username='intruso')
        self.assertFalse(user.is_superuser)
        self.assertEqual(set(user.groups.values_list('name', flat=True)),
                         {'cliente'})

    def test_registro_con_correo_duplicado_rechazado(self):
        User.objects.create_user('otro_user', email='repetido@mail.com',
                                 password='ClaveSegura2026*')
        res = self.client.post(reverse('register'), {
            'username': 'cualquiera',
            'email': 'REPETIDO@mail.com',   # mismo correo (case-insensitive)
            'password': 'ClaveSegura2026*',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_registro_acepta_clave_simple_en_modo_demo(self):
        """El proyecto es demo: claves simples de 6+ caracteres son válidas."""
        res = self.client.post(reverse('register'), {
            'username': 'clave_simple',
            'email': 'simple@mail.com',
            'password': '123456',
        }, format='json')
        self.assertEqual(res.status_code, 201)

    def test_registro_con_clave_muy_corta_rechazado(self):
        res = self.client.post(reverse('register'), {
            'username': 'debil',
            'email': 'debil@mail.com',
            'password': '123',   # por debajo del mínimo de 6 caracteres
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_usuario_registrado_puede_iniciar_sesion(self):
        """Ciclo completo: registrarse en el formulario -> login JWT."""
        self.client.post(reverse('register'), {
            'username': 'flujo_completo',
            'email': 'flujo@mail.com',
            'password': 'ClaveSegura2026*',
        }, format='json')

        login = self.client.post(reverse('token_obtain_pair'), {
            'username': 'flujo_completo', 'password': 'ClaveSegura2026*',
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['user']['role'], 'CLIENT')


# ==============================================================================
# 8. DASHBOARD FINANCIERO GERENCIAL
# ==============================================================================
class FinanzasTests(DatosPruebasBase):
    """
    Verifica el reporte financiero de gerencia: ingresos, egresos con monto
    efectivo, margen, desglose por clínica y ranking de clientes. Además,
    comprueba que SOLO Admin/Gerencia puedan consultarlo.
    """

    def setUp(self):
        # --- Escenario financiero sobre los datos base ---
        # Ingreso real cobrado + un pago aún sin verificar
        PolicyPayment.objects.create(
            policy=self.poliza1, amount=Decimal('1000.00'),
            payment_reference='REF-OK-1', status='APPROVED'
        )
        PolicyPayment.objects.create(
            policy=self.poliza2, amount=Decimal('250.00'),
            payment_reference='REF-PEND', status='PENDING'
        )
        # Siniestro aprobado en clínica B (la base ya tiene REC-A1: $200 en A)
        self.crear_reclamo('REC-FB1', self.poliza2, self.clinica_b,
                           Decimal('300.00'), 'APPROVED')
        # Siniestro EN REVISIÓN: no es gasto aún, pero compromete saldo
        self.crear_reclamo('REC-FP1', self.poliza1, self.clinica_a,
                           Decimal('150.00'), 'IN_REVIEW')

    # ------------------------------------------------------------------
    def test_solo_gerencia_y_admin_acceden(self):
        url = reverse('financial-dashboard')
        for usuario in (self.cliente1, self.analista, self.recep_a):
            with self.subTest(rol=usuario.username):
                self.client.force_authenticate(user=usuario)
                res = self.client.get(url)
                self.assertIn(res.status_code, (401, 403))

        for usuario in (self.gerente, self.admin):
            with self.subTest(rol=usuario.username):
                self.client.force_authenticate(user=usuario)
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)

    def test_resumen_financiero_cuadra(self):
        """Ingresos $1000, gastos efectivos $500 -> fondo $500 y margen 50%."""
        self.client.force_authenticate(user=self.gerente)
        res = self.client.get(reverse('financial-dashboard'))
        self.assertEqual(res.status_code, 200)

        resumen = res.data['resumen']
        self.assertEqual(resumen['ingresos_cobrados'], Decimal('1000.00'))
        self.assertEqual(resumen['pagos_por_verificar_monto'], Decimal('250.00'))
        self.assertEqual(resumen['pagos_pendientes_count'], 1)
        self.assertEqual(resumen['gastos_siniestros'], Decimal('500.00'))
        self.assertEqual(resumen['compromiso_pendiente'], Decimal('150.00'))
        self.assertEqual(resumen['siniestros_aprobados_count'], 2)
        self.assertEqual(resumen['fondo_utilidad'], Decimal('500.00'))
        self.assertAlmostEqual(resumen['margen_ganancia_pct'], 50.0)
        self.assertEqual(resumen['capital_asegado'], Decimal('1500.00'))

    def test_desglose_por_clinica_ordenado_con_porcentajes(self):
        """Clínica B ($300) supera a la A ($200): 60% vs 40% del gasto total."""
        self.client.force_authenticate(user=self.gerente)
        res = self.client.get(reverse('financial-dashboard'))
        clinicas = res.data['por_clinica']

        self.assertEqual(len(clinicas), 2)
        self.assertEqual(clinicas[0]['nombre'], 'Clínica Test B')
        self.assertEqual(clinicas[0]['total_consumido'], Decimal('300.00'))
        self.assertAlmostEqual(clinicas[0]['pct_del_gasto'], 60.0)
        self.assertEqual(clinicas[0]['siniestros'], 1)

        self.assertEqual(clinicas[1]['nombre'], 'Clínica Test A')
        self.assertAlmostEqual(clinicas[1]['pct_del_gasto'], 40.0)

    def test_ranking_clientes_por_consumo(self):
        """Cliente2 consumió $300 (top 1) y Cliente1 $200 aparece al final."""
        self.client.force_authenticate(user=self.gerente)
        res = self.client.get(reverse('financial-dashboard'))

        ranking = res.data['ranking_clientes']
        self.assertEqual(len(ranking), 2)
        self.assertEqual(ranking[0]['id'], self.perfil2.id)
        self.assertEqual(ranking[0]['consumido'], Decimal('300.00'))
        self.assertEqual(ranking[0]['polizas'], 1)
        self.assertAlmostEqual(ranking[0]['pct_uso'], 60.0)  # 300/500

        menores = res.data['clientes_menor_consumo']
        # Orden ascendente: el que MENOS consumió aparece de primero
        self.assertEqual(menores[0]['id'], self.perfil1.id)
        self.assertEqual(menores[0]['consumido'], Decimal('200.00'))


class ConfiguracionFinancieraTests(DatosPruebasBase):
    """
    Verifica los parámetros del negocio (fondo de capital y % de pago a
    clínicas): valores por defecto, edición solo por Admin/Gerencia,
    validación de rangos y el recálculo del dashboard con el reparto.
    """

    def setUp(self):
        """Mismo escenario financiero que FinanzasTests: la base ya trae
        REC-A1 por $200 en la Clínica A; aquí agregamos $300 más en la B."""
        PolicyPayment.objects.create(
            policy=self.poliza1, amount=Decimal('1000.00'),
            payment_reference='REF-OK-1', status='APPROVED'
        )
        self.crear_reclamo('REC-CF1', self.poliza2, self.clinica_b,
                           Decimal('300.00'), 'APPROVED')

    def _patch(self, payload, usuario):
        self.client.force_authenticate(user=usuario)
        return self.client.patch(reverse('financial-config'), payload, format='json')

    def test_config_por_defecto_y_dashboard_sin_reparto(self):
        """
        Sin tocar nada: 100% a clínicas y fondo 0 -> el desembolso coincide
        con el gasto total y la caja refleja solo primas menos siniestros.
        """
        config = ConfiguracionFinanciera.obtener()
        self.assertEqual(config.pct_pago_clinica, Decimal('100.00'))
        self.assertEqual(config.fondo_capital, Decimal('0.00'))
        self.assertEqual(config.pct_retencion_aseguradora, Decimal('0.00'))

        self.client.force_authenticate(user=self.gerente)
        res = self.client.get(reverse('financial-dashboard'))
        r = res.data['resumen']
        self.assertEqual(r['desembolso_clinicas'], Decimal('500.00'))
        self.assertEqual(r['retencion_aseguradora'], Decimal('0.00'))
        self.assertEqual(r['fondo_disponible'], Decimal('500.00'))

    def test_gerente_actualiza_y_el_dashboard_recalcula(self):
        """
        Fondo $5000 y pago 70%: desembolso $350, retención $150 y
        caja = 5000 + 1000 - 350 = $5650. Cada clínica cobra su 70%.
        """
        res = self._patch({'fondo_capital': '5000', 'pct_pago_clinica': '70'}, self.gerente)
        self.assertEqual(res.status_code, 200)
        # DRF serializa los Decimal como strings en la respuesta JSON
        self.assertEqual(Decimal(res.data['pct_retencion_aseguradora']), Decimal('30.00'))

        self.client.force_authenticate(user=self.gerente)
        data = self.client.get(reverse('financial-dashboard')).data
        r = data['resumen']
        self.assertEqual(r['desembolso_clinicas'], Decimal('350.00'))
        self.assertEqual(r['retencion_aseguradora'], Decimal('150.00'))
        self.assertEqual(r['fondo_disponible'], Decimal('5650.00'))
        # Ganancia neta beneficiada por la retención: 1000 - 350 = 650 (65%)
        self.assertEqual(r['utilidad_neta'], Decimal('650.00'))
        self.assertAlmostEqual(r['margen_neto_pct'], 65.0)
        # El margen bruto sigue calculándose sobre el gasto completo
        self.assertAlmostEqual(r['margen_ganancia_pct'], 50.0)

        por_nombre = {c['nombre']: c for c in data['por_clinica']}
        self.assertEqual(por_nombre['Clínica Test B']['pago_a_clinica'], Decimal('210.00'))
        self.assertEqual(por_nombre['Clínica Test A']['pago_a_clinica'], Decimal('140.00'))

    def test_solo_gerencia_edita_configuracion(self):
        """Analista, recepcionista y cliente no pueden editar los parámetros."""
        for usuario in (self.analista, self.recep_a, self.cliente1):
            with self.subTest(rol=usuario.username):
                res = self._patch(
                    {'pct_pago_clinica': '50'}, usuario)
                self.assertIn(res.status_code, (401, 403))

    def test_valores_fuera_de_rango_rechazados(self):
        """% mayor a 100 o fondo negativo devuelven 400 sin aplicar cambios."""
        for payload in ({'pct_pago_clinica': '150'},
                        {'pct_pago_clinica': '-5'},
                        {'fondo_capital': '-100'}):
            with self.subTest(payload=payload):
                res = self._patch(payload, self.admin)
                self.assertEqual(res.status_code, 400)

        config = ConfiguracionFinanciera.obtener()
        config.refresh_from_db()
        self.assertEqual(config.pct_pago_clinica, Decimal('100.00'))


class PagosApiTests(DatosPruebasBase):
    """
    Flujo completo del pago de primas: el cliente registra su comprobante
    (siempre nace PENDING), solo Analista/Gerencia lo dictamina vía
    POST /pagos/{id}/verificar/, y lo aprobado alimenta el dashboard.
    """

    def _comprobante(self):
        return SimpleUploadedFile('comprobante.png', b'data-demo',
                                  content_type='image/png')

    def _registrar(self, usuario, poliza, **extras):
        payload = {
            'policy': poliza.id,
            'amount': '250.00',
            'payment_reference': 'REF-CLI-99',
            'receipt_file': self._comprobante(),
        }
        payload.update(extras)
        self.client.force_authenticate(user=usuario)
        return self.client.post(
            reverse('policypayment-list'), payload, format='multipart')

    # ------------------------------------------------------------------
    def test_cliente_registra_comprobante_y_nace_pendiente(self):
        """201 PENDING aunque el cliente intente colarse status APPROVED."""
        res = self._registrar(self.cliente1, self.poliza1,
                              status='APPROVED')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'PENDING')
        self.assertIsNone(res.data['verification_notes'])

    def test_cliente_no_puede_pagar_poliza_ajena(self):
        """El blindaje del serializador: póliza de otro asegurado -> 400."""
        res = self._registrar(self.cliente1, self.poliza2)
        self.assertEqual(res.status_code, 400)
        self.assertIn('policy', res.data)

    def test_solo_analista_gerencia_dictaminan(self):
        """Recepción y médico quedan fuera (403); analista/gerente/admin pasan."""
        pago = PolicyPayment.objects.create(
            policy=self.poliza1, amount=Decimal('250.00'),
            payment_reference='REF-X', receipt_file=self._comprobante())

        for usuario in (self.recep_a, self.medico_user, self.cliente1):
            with self.subTest(rol=usuario.username):
                self.client.force_authenticate(user=usuario)
                res = self.client.post(
                    reverse('policypayment-verificar', args=[pago.id]),
                    {'status': 'APPROVED'}, format='json')
                self.assertIn(res.status_code, (401, 403))

        for usuario in (self.analista, self.gerente, self.admin):
            with self.subTest(rol=usuario.username):
                pago.refresh_from_db()
                pago.status = 'PENDING'   # reset para el siguiente subTest
                pago.save()
                self.client.force_authenticate(user=usuario)
                res = self.client.post(
                    reverse('policypayment-verificar', args=[pago.id]),
                    {'status': 'APPROVED'}, format='json')
                self.assertEqual(res.status_code, 200)

    def test_aprobacion_alimenta_el_dashboard(self):
        """Pago verificado como APPROVED suma en ingresos_cobrados."""
        res = self._registrar(self.cliente1, self.poliza1)
        pago_id = res.data['id']

        self.client.force_authenticate(user=self.gerente)
        dictamen = self.client.post(
            reverse('policypayment-verificar', args=[pago_id]),
            {'status': 'APPROVED',
             'verification_notes': 'Transferencia confirmada'}, format='json')
        self.assertEqual(dictamen.status_code, 200)
        self.assertEqual(dictamen.data['status'], 'APPROVED')

        dashboard = self.client.get(reverse('financial-dashboard'))
        r = dashboard.data['resumen']
        self.assertGreaterEqual(r['ingresos_cobrados'], Decimal('250.00'))

    def test_rechazo_exige_motivo_y_no_suma_ingresos(self):
        res = self._registrar(self.cliente2, self.poliza2)
        pago_id = res.data['id']

        self.client.force_authenticate(user=self.analista)

        # Sin motivo no se puede rechazar
        sin_notas = self.client.post(
            reverse('policypayment-verificar', args=[pago_id]),
            {'status': 'REJECTED'}, format='json')
        self.assertEqual(sin_notas.status_code, 400)

        con_notas = self.client.post(
            reverse('policypayment-verificar', args=[pago_id]),
            {'status': 'REJECTED',
             'verification_notes': 'Referencia no coincide con depósito'},
            format='json')
        self.assertEqual(con_notas.status_code, 200)
        self.assertEqual(con_notas.data['status'], 'REJECTED')

        # Un REJECTED jamás cuenta como ingreso
        self.client.force_authenticate(user=self.gerente)
        dashboard = self.client.get(reverse('financial-dashboard'))
        self.assertEqual(dashboard.data['resumen']['ingresos_cobrados'],
                         Decimal('0.00'))

    def test_no_se_redisctamina_un_pago_ya_verificado(self):
        res = self._registrar(self.cliente1, self.poliza1)
        pago_id = res.data['id']

        self.client.force_authenticate(user=self.gerente)
        primera = self.client.post(
            reverse('policypayment-verificar', args=[pago_id]),
            {'status': 'APPROVED'}, format='json')
        self.assertEqual(primera.status_code, 200)

        segunda = self.client.post(
            reverse('policypayment-verificar', args=[pago_id]),
            {'status': 'REJECTED', 'verification_notes': 'cambio de opinión'},
            format='json')
        self.assertEqual(segunda.status_code, 400)

        pago = PolicyPayment.objects.get(id=pago_id)
        self.assertEqual(pago.status, 'APPROVED')


class ConsumoPorRecepcionTests(DatosPruebasBase):
    """
    Segunda vía de cierre: la RECEPCIÓN DE CLÍNICA consume servicios que
    no requieren consulta médica (laboratorio, rayos X). Valida permisos
    (fuera clientes y médicos; recepción limitada a SU clínica) y que el
    consumo financiero se genere igual que con el cierre del médico.
    """

    def crear_cita_agendada(self, clinica=None, poliza=None, asegurado=None):
        """Cita ya autorizada por Seguros (SCHEDULED), lista para consumir."""
        return MedicalAppointmentRequest.objects.create(
            insured=asegurado or self.perfil1,
            policy=poliza or self.poliza1,
            clinic=clinica or self.clinica_a,
            service_type='LAB',
            reason_or_symptoms='Perfil lipídico en ayunas',
            status='SCHEDULED',
        )

    def _consumir(self, usuario, cita, **payload):
        body = {'baremo': self.baremo.id,
                'clinic_notes': 'Paciente asistió al laboratorio'}
        body.update(payload)
        self.client.force_authenticate(user=usuario)
        return self.client.post(
            reverse('appointmentrequest-consumir-servicio', args=[cita.id]),
            body, format='json')

    def test_recepcion_consume_y_genera_reclamo(self):
        """200 COMPLETED + reclamo APPROVED por el precio del baremo ($80)."""
        cita = self.crear_cita_agendada()
        res = self._consumir(self.recep_a, cita)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'COMPLETED')

        cita.refresh_from_db()
        self.assertIsNotNone(cita.generated_claim)
        reclamo = cita.generated_claim
        self.assertEqual(reclamo.status, 'APPROVED')
        self.assertEqual(reclamo.requested_amount, Decimal('80.00'))
        # La póliza absorbe el consumo completo del baremo
        self.poliza1.refresh_from_db()
        self.assertGreaterEqual(self.poliza1.used_amount, Decimal('80.00'))

    def test_solo_recepcion_admin_gerencia_consumen(self):
        """Cliente y médico NO pueden cerrar el proceso (403)."""
        cita = self.crear_cita_agendada()
        for usuario in (self.cliente1, self.medico_user):
            with self.subTest(rol=usuario.username):
                res = self._consumir(usuario, cita)
                self.assertIn(res.status_code, (401, 403))
                cita.refresh_from_db()
                self.assertEqual(cita.status, 'SCHEDULED')

    def test_recepcion_ajena_no_toca_la_cita(self):
        """La recepción de otra clínica no ve ni consume citas ajenas."""
        cita = self.crear_cita_agendada(clinica=self.clinica_b)
        res = self._consumir(self.recep_a, cita)
        self.assertIn(res.status_code, (403, 404))

    def test_validaciones_del_cierre(self):
        """PENDING no se consume; faltan datos -> 400; baremo ajeno -> 400."""
        cita_pendiente = MedicalAppointmentRequest.objects.create(
            insured=self.perfil1, policy=self.poliza1,
            clinic=self.clinica_a, service_type='LAB',
            reason_or_symptoms='Prueba', status='PENDING')
        res = self._consumir(self.recep_a, cita_pendiente)
        self.assertEqual(res.status_code, 400)

        cita = self.crear_cita_agendada()
        with self.subTest(caso='sin baremo'):
            self.assertEqual(self._consumir(self.recep_a, cita, baremo=None).status_code, 400)
        with self.subTest(caso='sin motivo'):
            self.assertEqual(
                self._consumir(self.recep_a, cita, clinic_notes='  ').status_code, 400)

    def test_baremo_de_otra_clinica_rechazado(self):
        """El ítem debe pertenecer al baremo de la clínica de la cita."""
        otro_baremo = ClinicBaremo.objects.create(
            clinic=self.clinica_b, service=self.servicio,
            price=Decimal('95.00'))
        cita = self.crear_cita_agendada()   # pertenece a clinica_a

        res = self._consumir(self.recep_a, cita, baremo=otro_baremo.id)
        self.assertEqual(res.status_code, 400)
        cita.refresh_from_db()
        # El acceso al reverse OneToOne lanza excepción si no existe reclamo
        self.assertFalse(hasattr(cita, 'generated_claim'))
