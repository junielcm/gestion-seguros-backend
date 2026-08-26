# ==============================================================================
# ARCHIVO: claims/mixins.py
# DESCRIPCIÓN: Mixin para filtrar automáticamente los querysets por rol (RBAC).
# ==============================================================================

class RoleBasedQuerysetMixin:
    """
    Filtra automáticamente los querysets asegurando que cada rol 
    solo obtenga los datos permitidos.

    NOTA DE DISEÑO: la señal post_save crea un InsuredProfile para TODOS los
    usuarios nuevos (también médicos y recepcionistas), así que NO se puede
    detectar al cliente con 'hasattr(user, "insured_profile")' como primera
    regla: eso haría que todo el personal fuese tratado como cliente y viera
    listas vacías. Por eso primero se consultan los GRUPOS del usuario y el
    perfil solo queda como respaldo para usuarios sin ningún rol asignado.
    """
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        model_name = qs.model.__name__

        # Catálogos de la Red Médica: visibles para CUALQUIER usuario autenticado.
        # (Clientes necesitan listar clínicas para solicitar citas; recepciones y
        #  médicos consultan servicios/precios. La ESCRITURA está protegida aparte
        #  por IsAdminOrManagerOrReadOnly en las vistas.)
        if model_name in ('Clinic', 'MedicalService', 'ClinicBaremo'):
            return qs

        # Admin, Gerente, Analista y Corredor ven todo el flujo operativo/financiero
        if user.is_superuser or user.groups.filter(
            name__in=['admin', 'gerente', 'analistaseguro', 'corredorseguro']
        ).exists():
            return qs

        # Recepcionista de Clínica: solo los registros de SU clínica asignada
        if user.groups.filter(name='recepcionclinica').exists():
            if hasattr(user, 'clinic_profile') and hasattr(qs.model, 'clinic'):
                return qs.filter(clinic=user.clinic_profile.clinic)
            return qs

        # Médico: SOLO las citas/consultas donde él fue asignado
        # (vía su DoctorProfile vinculado; sin perfil no puede ver nada)
        if user.groups.filter(name='medico').exists():
            if hasattr(user, 'doctor_profile'):
                if hasattr(qs.model, 'assigned_doctor'):
                    return qs.filter(assigned_doctor=user.doctor_profile)
                if hasattr(qs.model, 'doctor'):
                    return qs.filter(doctor=user.doctor_profile)
            return qs.none()

        # Cliente (Asegurado): declarado por grupo, o bien un usuario SIN ningún
        # rol que tenga perfil de asegurado (respaldo para registros antiguos)
        es_cliente = (
            user.groups.filter(name='cliente').exists()
            or (not user.groups.exists() and hasattr(user, 'insured_profile'))
        )
        if es_cliente:
            if not hasattr(user, 'insured_profile'):
                return qs.none()

            perfil = user.insured_profile
            if model_name == 'InsuredProfile':
                return qs.filter(id=perfil.id)
            if model_name == 'InsurancePolicy':
                return qs.filter(insured=perfil)
            if model_name in ('Claim', 'PolicyPayment'):
                return qs.filter(policy__insured=perfil)
            if model_name == 'MedicalAppointmentRequest':
                return qs.filter(insured=perfil)

        # Cualquier otro caso (sin rol identificable): sin acceso a datos
        return qs.none()
