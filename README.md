# PROYECTO-2.-SISTEMA-DISTRIBUIDO-PARA-UNA-CADENA-DE-FARMACIAS-

Proyecto Integral de la materia Tópicos de Bases de Datos · Cadena de farmacias **Yza**.

## Estructura

- `_Docker/docker-compose.yml`: 3 nodos PostgreSQL (Norte 5433, Centro 5434, Sur 5435) + pgAdmin 5050.
- `_SQL/`: scripts re-ejecutables con el esquema, catálogos y índices de cada nodo.
- `login_diseno/`: aplicación Flask de autenticación, dashboards por perfil,
  gestión de roles y punto de venta.

## Puesta en marcha

```bash
# 1) Levantar los nodos
cd PROYECTO_2_SISTEMA_DISTRIBUIDO_PARA_UNA_CADENA_DE_FARMACIAS/_Docker
docker compose up -d

# 2) Ejecutar el SQL de cada nodo (nodo_1_norte.sql, nodo_2_centro.sql, nodo_3_sur.sql)

# 3) Sembrar datos de prueba
cd ../../login_diseno
python seed_datos.py

# 4) Arrancar la app
python app.py
```

Contraseña de prueba para todos los usuarios: `Yza2026!`

| Usuario | Puesto | Rol | Sucursal |
| --- | --- | --- | --- |
| `admin_yza` | Gerente | Administrador | Centro |
| `gerente_norte` / `gerente_centro` / `gerente_sur` | Gerente | Gerente | Norte / Centro / Sur |
| `operador_norte` / `operador_centro` / `operador_sur` | Cajero | Operador | Norte / Centro / Sur |
| `auditor_yza` | Almacenista | Auditor | Centro |
| `consulta_yza` | Farmacéutico | Consulta | Centro |

## Dashboards por rol

Cada rol tiene un menú y una vista de resumen propia (`login_diseno/perfiles.py`):

- **Administrador**: centro de control, estado de los 3 nodos, auditoría y gestión de usuarios.
- **Gerente**: indicadores, ventas y gestión de roles de menor rango en su sucursal.
- **Operador**: punto de venta funcional, buscador de medicamentos y "Mis compras".
- **Auditor**: bitácora de cambios, control de stock e inventario.
- **Consulta**: catálogo y disponibilidad en modo solo lectura.

Los datos se consultan en el nodo de la sucursal del usuario; si la base no está
disponible, la interfaz muestra datos de ejemplo señalados con el chip
**"Datos de ejemplo"** (`login_diseno/datos_dashboard.py`). La interfaz reutiliza
los colores del login existente; no se requiere ningún archivo de Figma.

## Funcionalidades operativas

- **Gestión de roles**: el Administrador puede asignar o dar de baja cualquier
  rol en los 3 nodos, excepto el suyo propio. El Gerente solo puede gestionar a Operadores,
  Auditores y Consulta; están bloqueados otros Gerentes, el Administrador y su
  propio usuario. Dar de baja desactiva el acceso y "Activar" lo reactiva.
- **Ventas**: el punto de venta muestra los medicamentos con existencias, crea
  la venta y su detalle, descuenta el inventario en la misma transacción y
  refleja el resultado en "Mis compras". Los productos con receta piden
  cliente, médico y cédula profesional.
- **Cierre de sesión**: se accede desde el icono de perfil en la esquina
  superior derecha. Muestra una confirmación con **Aceptar** y **Cancelar**;
  el botón anterior del menú lateral fue eliminado.
