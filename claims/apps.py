from django.apps import AppConfig


class ClaimsConfig(AppConfig):
    """
    Configuración de la app 'claims': el módulo principal del proyecto,
    donde vive toda la lógica de seguros (pólizas, siniestros, red médica).
    """
    name = 'claims'
