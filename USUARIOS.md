# Usuarios de Prueba - Gestión de Seguros

Credenciales de los usuarios demo para probar la API. Todos usan la contraseña `123456`.

> **⚠️ Advertencia de Seguridad:**
> - Estos usuarios son **solo para entorno de desarrollo y demostración**.
> - **Nunca** deben usarse en un servidor de producción.
> - Las contraseñas débiles (`123456`) son intencionales para facilitar las pruebas.
> - En producción, usa contraseñas robustas y habilita los validadores de Django.

---

## Credenciales

| Usuario | Contraseña | Rol | Superusuario | Descripción |
|---|---|---|---|---|
| `admin` | `admin` | Administrador General | Sí | Panel de administración Django (`/admin/`) |
| `gerente1` | `123456` | Gerente | Sí | Acceso total al sistema y API |
| `analista1` | `123456` | Analista de Seguros | No | Autoriza/rechaza solicitudes, audita siniestros |
| `medico1` | `123456` | Médico | No | Registra consultas médicas y diagnósticos |
| `recepcion1` | `123456` | Recepción de Clínica | No | Registra citas y gestiona pacientes de su clínica |
| `cliente1` | `123456` | Cliente | No | Ve sus pólizas, pagos, reclamos y solicitudes |

> **Nota:** El usuario `admin` es exclusivo para el panel de administración Django. Los demás usuarios se usan para probar la API REST.

---

## Permisos por Rol

### admin (Administrador General / Superusuario)
- Acceso exclusivo al panel de administración Django: `http://127.0.0.1:8000/admin/`
- Gestiona todos los modelos (usuarios, clínicas, pólizas, siniestros, etc.)
- No se usa para probar la API REST (usar `gerente1` para eso)

### gerente1 (Gerente / Superusuario)
- Acceso completo a todos los endpoints
- Panel de administración: `http://127.0.0.1:8000/admin/`
- Puede gestionar usuarios, clínicas, pólizas, siniestros
- Configuración financiera del sistema

### analista1 (Analista de Seguros)
- Autoriza o rechaza solicitudes de citas/servicios médicos
- Revisa y aprueba/rechaza siniestros
- Ve el dashboard financiero
- Ve clínicas, servicios y baremos (lectura)
- **No puede:** crear usuarios, modificar clínicas, registrar consultas médicas

### medico1 (Médico)
- Ve las citas asignadas a él
- Registra fichas de consulta médica (signos vitales, diagnóstico)
- Ve siniestros asignados
- **No puede:** crear pólizas, autorizar solicitudes, gestionar clínicas

### recepcion1 (Recepción de Clínica)
- Registra solicitudes de citas para SU clínica
- Ve pacientes y servicios de SU clínica
- Gestiona el flujo de atención de su centro
- **No puede:** ver datos de otras clínicas, autorizar coberturas, registrar consultas

### cliente1 (Cliente)
- Ve sus propias pólizas y saldo disponible
- Ve sus pagos realizados
- Ve sus reclamos/siniestros
- Ve sus solicitudes de cita
- **No puede:** ver datos de otros clientes, modificar pólizas, autorizar servicios

---

## Póliza de Prueba

El usuario `cliente1` tiene una póliza preconfigurada:

| Campo | Valor |
|---|---|
| Número de póliza | POL-2026-001 |
| Tipo | Salud / Maternidad |
| Cobertura total | $2,000.00 USD |
| Estado | Activa |
| Vigencia | 1 año desde la fecha de ejecución del seed |

---

## Cómo Obtener un Token JWT

```bash
# Ejemplo con curl
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "cliente1", "password": "123456"}'
```

Respuesta:
```json
{
  "refresh": "...",
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Usar el token `access` en headers de requests posteriores:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

---

## Clínicas de Prueba

El script `setup_demo.py` crea 3 clínicas afiliadas:

| Clínica | Dirección | Servicios |
|---|---|---|
| Clínica El Ávila | Av. San Juan Bosco, Altamira, Caracas | Consulta General ($40), Emergencia ($120), Rayos X ($35), Laboratorio ($50) |
| Centro Médico La Trinidad | Av. Intercomunal La Trinidad, Baruta | Consulta Especializada ($60), Emergencia Pediatría ($130), Ecografía ($75), Hospitalización ($250) |
| Policlínica Metropolitana | Calle A-1, Caurimare | Traumatología ($50), Sutura ($90), Tomografía ($180) |
