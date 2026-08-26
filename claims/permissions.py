# ==============================================================================
# ARCHIVO: claims/permissions.py
# DESCRIPCIÓN: Permisos personalizados de Django REST Framework que implementan
#              el control de acceso por rol (RBAC) usando los grupos de
#              Django Auth. Cada clase valida qué rol puede hacer cada acción.
# ==============================================================================

from rest_framework import permissions

class IsAdminOrManager(permissions.BasePermission):
    """
    Permiso exclusivo para la administración de usuarios del sistema.
    Solo superusuarios o miembros de los grupos 'admin' / 'gerente'.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_superuser
            or request.user.groups.filter(name__in=['admin', 'gerente']).exists()
        )


class IsAdminOrManagerOrReadOnly(permissions.BasePermission):
    """
    Permisos para la Gestión de la Red Médica (Clínicas, Catálogo y Baremos):
    - Lectura: cualquier usuario autenticado (recepciones, médicos, clientes
      necesitan consultar clínicas y precios).
    - Escritura (crear/editar/eliminar): EXCLUSIVO de superusuarios y miembros
      de los grupos 'admin' / 'gerente'.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        return (
            request.user.is_superuser
            or request.user.groups.filter(name__in=['admin', 'gerente']).exists()
        )


class IsInsuranceAnalyst(permissions.BasePermission):
    """
    Permiso exclusivo para el DICTAMEN de solicitudes de citas / servicios médicos.
    Solo superusuarios o miembros de los grupos 'analistaseguro' / 'admin' / 'gerente'
    pueden autorizar o rechazar cobertura. La recepción de clínica queda excluida.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name__in=['analistaseguro', 'admin', 'gerente']
            ).exists()
        )


class IsDoctor(permissions.BasePermission):
    """
    Permiso exclusivo para el registro de atención médica.
    Solo superusuarios o miembros del grupo 'medico'.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_superuser
            or request.user.groups.filter(name='medico').exists()
        )


class IsReceptionOrAdminManager(permissions.BasePermission):
    """
    Acciones operativas de la clínica abiertas a Recepción (por ejemplo,
    consumir servicios de laboratorio/rayos X que no pasan por consulta
    médica) y a Admin/Gerencia. El alcance de Recepción a SOLO SU clínica
    lo garantiza RoleBasedQuerysetMixin + has_object_permission; aquí solo
    se valida el rol. Los clientes y médicos quedan fuera a propósito:
    el cierre del proceso no puede ejecutarlo el asegurado.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name__in=['admin', 'gerente', 'recepcionclinica']
            ).exists()
        )


class RoleBasedPermission(permissions.BasePermission):
    """
    Permiso centralizado para validar el acceso según los 7 roles del sistema.
    """

    def has_permission(self, request, view):
        # Todo usuario debe estar autenticado para acceder
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Permitimos el acceso a la vista; la validación detallada 
        # por cada registro individual se maneja en has_object_permission.
        return True 

    def has_object_permission(self, request, view, obj):
        user = request.user

        # 1. Admin y Gerente tienen visibilidad global de lectura/supervisión
        if user.is_superuser or user.groups.filter(name__in=['admin', 'gerente']).exists():
            return True

        # 2. Analista de Seguros y Corredor: supervisión del flujo completo
        if user.groups.filter(name__in=['analistaseguro', 'corredorseguro']).exists():
            return True

        # 3. Recepción de Clínica: solo registros de su clínica asignada
        if user.groups.filter(name='recepcionclinica').exists():
            if hasattr(user, 'clinic_profile'):
                if hasattr(obj, 'clinic'):
                    return obj.clinic == user.clinic_profile.clinic
                if hasattr(obj, 'assigned_clinic'):
                    return obj.assigned_clinic == user.clinic_profile.clinic
            return False

        # 4. Médico: solo consultas o siniestros asignados a él
        if user.groups.filter(name='medico').exists():
            if hasattr(user, 'doctor_profile'):
                if hasattr(obj, 'assigned_doctor'):
                    return obj.assigned_doctor == user.doctor_profile
                if hasattr(obj, 'doctor'):
                    return obj.doctor == user.doctor_profile
            return False

        # 5. Cliente: solo sus propias pólizas, pagos y reclamos.
        #    Se identifica por GRUPO; el perfil como atributo es un respaldo
        #    únicamente para usuarios sin ningún rol (la señal post_save crea
        #    InsuredProfile para todos los usuarios, no solo clientes).
        es_cliente = (
            user.groups.filter(name='cliente').exists()
            or (not user.groups.exists() and hasattr(user, 'insured_profile'))
        )
        if es_cliente:
            if not hasattr(user, 'insured_profile'):
                return False
            perfil = user.insured_profile
            if obj.__class__.__name__ == 'InsuredProfile':
                return obj == perfil
            if hasattr(obj, 'insured'):
                return obj.insured == perfil
            if hasattr(obj, 'policy') and obj.policy:
                return obj.policy.insured == perfil

        return False