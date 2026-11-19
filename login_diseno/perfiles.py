"""Perfiles de interfaz según el rol/puesto del empleado.

Cada perfil define:
  - plantilla: vista de resumen propia (diseño distinto por puesto)
  - menu: opciones visibles en el sidebar (slug, etiqueta, icono)
  - acciones: accesos rápidos del resumen
  - etiqueta/aviso: información de alcance que se muestra en la interfaz
"""

# Jerarquía de roles: un usuario solo puede gestionar a otro de menor rango.
JERARQUIA = {"Consulta": 0, "Auditor": 0, "Operador": 0, "Gerente": 1, "Administrador": 2}
TODOS_LOS_ROLES = ["Administrador", "Gerente", "Operador", "Auditor", "Consulta"]


def puede_gestionar(rol_actual, rol_objetivo):
    """True cuando rol_actual puede asignar/borrar el rol_objetivo."""
    actual = JERARQUIA.get(rol_actual)
    objetivo = JERARQUIA.get(rol_objetivo)
    return actual is not None and objetivo is not None and objetivo < actual


def roles_asignables(rol_actual):
    """Roles que el usuario puede asignar (nunca de su rango o superior)."""
    return [r for r in TODOS_LOS_ROLES if puede_gestionar(rol_actual, r)]


PERFILES = {
    "Administrador": {
        "nombre": "Administrador",
        "plantilla": "partials/resumen_admin.html",
        "titulo": "Centro de control",
        "subtitulo": "Visión global de la red de farmacias Yza",
        "etiqueta": "Acceso total",
        "aviso": "Tienes visibilidad de los 3 nodos y de la configuración del sistema.",
        "puede_gestionar": True,
        "puede_vender": False,
        "menu": [
            ("resumen", "Resumen general", "grid"),
            ("red", "Red y sucursales", "store"),
            ("inventario", "Inventario", "pill"),
            ("ventas", "Ventas", "chart"),
            ("usuarios", "Usuarios y roles", "users"),
            ("auditoria", "Auditoría", "shield"),
            ("configuracion", "Configuración", "settings"),
        ],
        "acciones": [
            ("Ver nodos", "red", "store"),
            ("Auditoría", "auditoria", "shield"),
            ("Usuarios", "usuarios", "users"),
        ],
    },
    "Gerente": {
        "nombre": "Gerente de sucursal",
        "plantilla": "partials/resumen_gerente.html",
        "titulo": "Resumen de sucursal",
        "subtitulo": "Indicadores y operación de tu sucursal",
        "etiqueta": "Gestión de sucursal",
        "aviso": "Tu información se limita al nodo de tu sucursal. Puedes gestionar roles de menor rango y registrar ventas.",
        "puede_gestionar": True,
        "puede_vender": True,
        "menu": [
            ("resumen", "Resumen", "grid"),
            ("ventas", "Ventas", "chart"),
            ("inventario", "Inventario", "pill"),
            ("clientes", "Clientes", "users"),
            ("empleados", "Empleados", "users"),
            ("recetas", "Recetas", "receipt"),
            ("reportes", "Reportes", "clipboard"),
        ],
        "acciones": [
            ("Nueva venta", "ventas", "cart"),
            ("Ver inventario", "inventario", "pill"),
            ("Reportes", "reportes", "clipboard"),
        ],
    },
    "Operador": {
        "nombre": "Operador de caja",
        "plantilla": "partials/resumen_operador.html",
        "titulo": "Punto de venta",
        "subtitulo": "Operación diaria de caja y mostrador",
        "etiqueta": "Operación",
        "aviso": "Acceso a ventas, catálogo y clientes de tu sucursal.",
        "puede_gestionar": False,
        "puede_vender": True,
        "menu": [
            ("resumen", "Mi turno", "grid"),
            ("ventas", "Nueva venta", "cart"),
            ("catalogo", "Buscar medicamentos", "search"),
            ("clientes", "Clientes", "users"),
            ("recetas", "Recetas", "receipt"),
            ("historial", "Mis compras", "clock"),
        ],
        "acciones": [
            ("Nueva venta", "ventas", "cart"),
            ("Buscar producto", "catalogo", "search"),
            ("Mis compras", "historial", "clock"),
        ],
    },
    "Auditor": {
        "nombre": "Auditor",
        "plantilla": "partials/resumen_auditor.html",
        "titulo": "Panel de auditoría",
        "subtitulo": "Trazabilidad, inventarios y control de cambios",
        "etiqueta": "Solo control",
        "aviso": "Consultas de lectura sobre movimientos y registros.",
        "puede_gestionar": False,
        "puede_vender": False,
        "menu": [
            ("resumen", "Panel de auditoría", "shield"),
            ("movimientos", "Movimientos", "clipboard"),
            ("inventario", "Inventario", "pill"),
            ("alertas", "Alertas de stock", "alert"),
            ("ventas", "Ventas", "chart"),
            ("reportes", "Reportes", "clipboard"),
        ],
        "acciones": [
            ("Movimientos", "movimientos", "clipboard"),
            ("Alertas", "alertas", "alert"),
            ("Exportar reporte", "reportes", "download"),
        ],
    },
    "Consulta": {
        "nombre": "Consulta",
        "plantilla": "partials/resumen_consulta.html",
        "titulo": "Consultas y catálogo",
        "subtitulo": "Información de medicamentos y disponibilidad",
        "etiqueta": "Solo lectura",
        "aviso": "Tu perfil permite consultar información sin modificar registros.",
        "puede_gestionar": False,
        "puede_vender": False,
        "menu": [
            ("resumen", "Catálogo", "grid"),
            ("inventario", "Consultar inventario", "pill"),
            ("recetas", "Recetas", "receipt"),
            ("clientes", "Clientes", "users"),
            ("ayuda", "Ayuda", "shield"),
        ],
        "acciones": [
            ("Buscar medicamento", "resumen", "search"),
            ("Ver inventario", "inventario", "pill"),
            ("Ayuda", "ayuda", "shield"),
        ],
    },
}

SECCIONES = {
    "resumen": ("Resumen", "Información general de tu perfil."),
    "red": ("Red y sucursales", "Estado de los tres nodos distribuidos de la cadena."),
    "inventario": ("Inventario", "Existencias, mínimos y alertas de la sucursal."),
    "ventas": ("Ventas", "Registro y consulta de ventas de la sucursal."),
    "usuarios": ("Usuarios y roles", "Cuentas, puestos y Roles asignados en la red."),
    "auditoria": ("Auditoría", "Registro de altas, cambios y bajas en la base de datos."),
    "configuracion": ("Configuración", "Parámetros generales del sistema distribuido."),
    "clientes": ("Clientes", "Clientes registrados en la sucursal."),
    "empleados": ("Empleados", "Personal de la sucursal y su puesto."),
    "recetas": ("Recetas", "Recetas registradas y su vigencia."),
    "reportes": ("Reportes", "Indicadores y exportación de información."),
    "catalogo": ("Buscar medicamentos", "Catálogo de medicamentos disponibles."),
    "movimientos": ("Movimientos", "Historial de movimientos registrados por auditoría."),
    "alertas": ("Alertas de stock", "Productos con existencias en o bajo el mínimo."),
    "historial": ("Mis compras", "Ventas registradas desde tu puesto de trabajo."),
    "ayuda": ("Ayuda", "Guía rápida de uso del sistema."),
}


def perfil_de(rol):
    """Devuelve el perfil correspondiente al rol. Desconocido => solo lectura."""
    return PERFILES.get(rol or "", PERFILES["Consulta"])


def obtener_seccion(perfil, slug):
    """Valida que la sección pertenezca al menú del perfil."""
    permitidas = {item[0] for item in perfil["menu"]}
    slug = slug if slug in permitidas else "resumen"
    titulo, descripcion = SECCIONES.get(slug, SECCIONES["resumen"])
    return {"slug": slug, "titulo": titulo, "descripcion": descripcion}
