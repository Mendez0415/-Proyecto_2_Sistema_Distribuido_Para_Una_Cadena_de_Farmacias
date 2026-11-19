"""Datos para los dashboards.

Las consultas se hacen contra el nodo de la sucursal del usuario (o contra los
tres nodos si es Administrador). Si Docker/Postgres no está disponible se
devuelven datos de ejemplo para que la interfaz sempre se pueda visualizar.
"""

from db import Nodo, todos_los_nodos

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

SQL_INDICADORES = """
    SELECT
        (SELECT count(*) FROM clientes)                                    AS clientes,
        (SELECT count(*) FROM empleados)                                   AS empleados,
        (SELECT count(*) FROM medicamentos)                                AS medicamentos,
        (SELECT COALESCE(sum(total), 0) FROM ventas
          WHERE fecha_hora::date = CURRENT_DATE)                           AS ventas_hoy,
        (SELECT count(*) FROM ventas
          WHERE fecha_hora::date = CURRENT_DATE)                           AS pedidos_hoy,
        (SELECT count(*) FROM inventarios
          WHERE existencia <= stock_minimo)                                AS alertas
"""

SQL_TOP = """
    SELECT m.nombre_comercial AS nombre, SUM(d.cantidad) AS unidades,
           SUM(d.subtotal) AS importe
    FROM detalle_venta d
    JOIN medicamentos m ON m.id_medicamento = d.id_medicamento
    GROUP BY m.nombre_comercial
    ORDER BY unidades DESC, nombre LIMIT 5
"""

SQL_ALERTAS = """
    SELECT m.nombre_comercial AS nombre, i.existencia, i.stock_minimo AS minimo
    FROM inventarios i JOIN medicamentos m ON m.id_medicamento = i.id_medicamento
    WHERE i.existencia <= i.stock_minimo
    ORDER BY i.existencia ASC LIMIT 5
"""

SQL_AUDITORIA = """
    SELECT operacion, tabla_afectada AS tabla, fecha_hora
    FROM auditoria ORDER BY fecha_hora DESC LIMIT 6
"""

SQL_VENTAS = """
    SELECT v.id_venta, v.fecha_hora, v.total,
           COALESCE(c.nombre, 'Mostrador') AS cliente
    FROM ventas v LEFT JOIN clientes c ON c.id_cliente = v.id_cliente
    ORDER BY v.fecha_hora DESC LIMIT 6
"""

SQL_INVENTARIO = """
    SELECT m.nombre, m.nombre_comercial AS comercial, i.existencia,
           i.stock_minimo AS minimo, m.precio_unitario AS precio
    FROM inventarios i JOIN medicamentos m ON m.id_medicamento = i.id_medicamento
    ORDER BY i.existencia ASC LIMIT 8
"""

SQL_CATALOGO = """
    SELECT nombre, nombre_comercial AS comercial, precio_unitario AS precio,
           requiere_receta, stock_minimo AS minimo
    FROM medicamentos ORDER BY nombre LIMIT 10
"""

SQL_CLIENTES = """
    SELECT id_cliente, nombre, correo, telefono, fecha_registro
    FROM clientes ORDER BY fecha_registro DESC LIMIT 20
"""

SQL_EMPLEADOS = """
    SELECT e.nombre, e.puesto, e.correo, r.nombre_rol AS rol
    FROM empleados e
    LEFT JOIN rol r ON r.id_empleado = e.id_empleado AND r.activo
    ORDER BY e.nombre LIMIT 8
"""

SQL_RECETAS = """
    SELECT c.nombre AS cliente, r.nombre_medico AS medico,
           m.nombre_comercial AS medicamento, r.fecha_emision AS fecha
    FROM recetas r
    JOIN clientes c ON c.id_cliente = r.id_cliente
    JOIN medicamentos m ON m.id_medicamento = r.id_medicamento
    ORDER BY r.fecha_emision DESC LIMIT 6
"""

SQL_USUARIOS = """
    SELECT e.id_empleado, e.nombre, e.puesto, e.correo,
           c.usuario, c.activo, c.id_sucursal, r.nombre_rol AS rol
    FROM empleados e
    JOIN credenciales c ON c.id_empleado = e.id_empleado
    LEFT JOIN rol r ON r.id_empleado = e.id_empleado AND r.activo
    ORDER BY e.nombre
"""

SQL_USUARIO_OBJETIVO = """
    SELECT e.id_empleado, e.nombre, r.nombre_rol AS rol
    FROM empleados e
    LEFT JOIN rol r ON r.id_empleado = e.id_empleado AND r.activo
    WHERE e.id_empleado = %s
"""

SQL_DISPONIBLES = """
    SELECT i.id_medicamento, m.nombre, m.nombre_comercial AS comercial,
           m.precio_unitario AS precio, i.existencia, i.stock_minimo AS minimo,
           m.requiere_receta
    FROM inventarios i JOIN medicamentos m ON m.id_medicamento = i.id_medicamento
    WHERE i.existencia > 0
    ORDER BY m.nombre
"""

SQL_MIS_VENTAS = """
    SELECT v.id_venta, v.fecha_hora, v.total,
           COALESCE(c.nombre, 'Mostrador') AS cliente
    FROM ventas v LEFT JOIN clientes c ON c.id_cliente = v.id_cliente
    WHERE v.id_empleado = %s
    ORDER BY v.fecha_hora DESC LIMIT 8
"""

SQL_TENDENCIA = """
    SELECT EXTRACT(ISODOW FROM fecha_hora)::int AS dia, SUM(total) AS total
    FROM ventas
    WHERE fecha_hora >= CURRENT_DATE - INTERVAL '6 days'
    GROUP BY 1 ORDER BY 1
"""


def _consultar(nodo, sql, params=None):
    try:
        return nodo.consultar(sql, params)
    except Exception:
        return None


def _money(valor):
    return "${:,.2f}".format(float(valor or 0))


def _num(valor):
    return int(valor or 0)


def _fecha(valor):
    return valor.strftime("%d/%m %H:%M") if hasattr(valor, "strftime") else str(valor or "")


def _fecha_corta(valor):
    return valor.strftime("%d/%m/%Y") if hasattr(valor, "strftime") else str(valor or "")


def _demo():
    """Estructura base con datos de ejemplo (se usa si la BD no responde)."""
    tendencia = [4200, 5100, 3850, 6200, 5400, 7350, 4680]
    demo_ventas = [
        {"id": "1042", "cliente": "María López", "total": "$485.00", "fecha": "Hoy 10:24"},
        {"id": "1041", "cliente": "Mostrador", "total": "$210.50", "fecha": "Hoy 10:02"},
        {"id": "1040", "cliente": "Juan Castillo", "total": "$735.00", "fecha": "Hoy 09:47"},
        {"id": "1039", "cliente": "Mostrador", "total": "$98.00", "fecha": "Hoy 09:15"},
    ]
    return {
        "origen": "demo",
        "indicadores": {
            "clientes": 24, "empleados": 9, "medicamentos": 10,
            "ventas_hoy": 15380.50, "pedidos_hoy": 18, "alertas": 3,
        },
        "tendencia": [
            {"dia": dia, "valor": valor, "altura": round(valor / max(tendencia) * 100)}
            for dia, valor in zip(DIAS, tendencia)
        ],
        "tendencia_demo": True,
        "top": [
            {"nombre": "Paracetamol 500 mg", "unidades": 48, "importe": "$1,680.00"},
            {"nombre": "Ibuprofeno 400 mg", "unidades": 35, "importe": "$1,837.50"},
            {"nombre": "Omeprazol 20 mg", "unidades": 27, "importe": "$1,620.00"},
            {"nombre": "Loratadina 10 mg", "unidades": 21, "importe": "$882.00"},
            {"nombre": "Vitamina C 1 g", "unidades": 16, "importe": "$1,424.00"},
        ],
        "alertas": [
            {"nombre": "Azitromicina 500 mg", "existencia": 5, "minimo": 8},
            {"nombre": "Ciprofloxacino 500 mg", "existencia": 6, "minimo": 8},
            {"nombre": "Amoxicilina 500 mg", "existencia": 8, "minimo": 10},
        ],
        "actividad": [
            {"operacion": "UPDATE", "tabla": "inventarios", "fecha": "Hoy 09:42"},
            {"operacion": "INSERT", "tabla": "ventas", "fecha": "Hoy 09:15"},
            {"operacion": "INSERT", "tabla": "detalle_venta", "fecha": "Hoy 09:15"},
            {"operacion": "UPDATE", "tabla": "inventarios", "fecha": "Ayer 18:03"},
        ],
        "ventas": demo_ventas,
        "mis_ventas": demo_ventas,
        "inventario": [
            {"nombre": "Azitromicina 500 mg", "comercial": "Zitromax", "existencia": 5, "minimo": 8, "precio": "$145.00"},
            {"nombre": "Ciprofloxacino 500 mg", "comercial": "Ciproxina", "existencia": 6, "minimo": 8, "precio": "$120.00"},
            {"nombre": "Amoxicilina 500 mg", "comercial": "Amoxil", "existencia": 8, "minimo": 10, "precio": "$98.00"},
            {"nombre": "Metformina 850 mg", "comercial": "Glucophage", "existencia": 12, "minimo": 10, "precio": "$68.00"},
            {"nombre": "Paracetamol 500 mg", "comercial": "Tempra", "existencia": 50, "minimo": 20, "precio": "$35.00"},
        ],
        "catalogo": [
            {"nombre": "Amoxicilina 500 mg", "comercial": "Amoxil", "precio": "$98.00", "receta": True, "minimo": 10},
            {"nombre": "Ibuprofeno 400 mg", "comercial": "Advil", "precio": "$52.50", "receta": False, "minimo": 15},
            {"nombre": "Loratadina 10 mg", "comercial": "Clarityne", "precio": "$42.00", "receta": False, "minimo": 12},
            {"nombre": "Omeprazol 20 mg", "comercial": "Losec", "precio": "$60.00", "receta": False, "minimo": 15},
            {"nombre": "Paracetamol 500 mg", "comercial": "Tempra", "precio": "$35.00", "receta": False, "minimo": 20},
        ],
        "clientes": [
            {"id": 10001, "nombre": "María López", "correo": "maria.lopez@correo.com", "telefono": "993-410-0001", "fecha": "12/03/2026"},
            {"id": 10002, "nombre": "Juan Castillo", "correo": "juan.castillo@correo.com", "telefono": "993-410-0002", "fecha": "10/03/2026"},
        ],
        "empleados": [
            {"nombre": "Carlos Pérez", "puesto": "Cajero", "correo": "operador.norte@yza.com", "rol": "Operador"},
            {"nombre": "Laura Méndez", "puesto": "Gerente", "correo": "gerente.norte@yza.com", "rol": "Gerente"},
        ],
        "recetas": [],
        "nodos": [],
        "disponibles": [
            {"id": 1, "nombre": "Paracetamol 500 mg", "comercial": "Tempra", "precio": "$35.00", "precio_num": 35.0, "existencia": 50, "minimo": 20, "receta": False},
            {"id": 2, "nombre": "Ibuprofeno 400 mg", "comercial": "Advil", "precio": "$52.50", "precio_num": 52.5, "existencia": 35, "minimo": 15, "receta": False},
            {"id": 4, "nombre": "Azitromicina 500 mg", "comercial": "Zitromax", "precio": "$145.00", "precio_num": 145.0, "existencia": 5, "minimo": 8, "receta": True},
        ],
        "usuarios": [
            {"id": 10001, "nombre": "Carlos Pérez", "puesto": "Cajero", "correo": "operador.norte@yza.com", "usuario": "operador_norte", "rol": "Operador", "activo": True, "sucursal": "Norte"},
            {"id": 10002, "nombre": "Laura Méndez", "puesto": "Gerente", "correo": "gerente.norte@yza.com", "usuario": "gerente_norte", "rol": "Gerente", "activo": True, "sucursal": "Norte"},
        ],
    }


def _cargar_indicadores(datos, nodos):
    total = {"clientes": 0, "empleados": 0, "medicamentos": 0,
             "ventas_hoy": 0, "pedidos_hoy": 0, "alertas": 0}
    respuesta = False
    for nodo in nodos:
        filas = _consultar(nodo, SQL_INDICADORES)
        if filas:
            respuesta = True
            for clave in total:
                total[clave] += _num(filas[0][clave])
    if respuesta:
        datos["indicadores"] = total
        datos["origen"] = "bd"
    return total


def _cargar_tendencia(datos, nodos):
    acumulado = {i: 0.0 for i in range(1, 8)}
    respuesta = False
    for nodo in nodos:
        filas = _consultar(nodo, SQL_TENDENCIA)
        if filas is not None:
            respuesta = True
            for fila in filas:
                acumulado[int(fila["dia"])] += float(fila["total"] or 0)
    if not respuesta:
        return
    valores = [acumulado[i] for i in range(1, 8)]
    maximo = max(valores) or 1
    datos["tendencia"] = [
        {"dia": dia, "valor": round(valor, 2),
         "altura": max(4, round(valor / maximo * 100))}
        for dia, valor in zip(DIAS, valores)
    ]
    datos["tendencia_demo"] = not any(valores)


def _cargar_lista(datos, nodos, sql, clave, transformar, limite=8, orden=None,
                  conservar_demo=True, params=None):
    filas_totales = []
    for nodo in nodos:
        filas = _consultar(nodo, sql, params)
        if filas:
            filas_totales.extend(transformar(fila) for fila in filas)
    if not filas_totales:
        if not conservar_demo:
            datos[clave] = []  # la BD respondió, pero no hay registros reales
        return
    if orden:
        filas_totales.sort(key=orden)
    datos[clave] = filas_totales[:limite]


def _transformar_top(fila):
    return {"nombre": fila["nombre"], "unidades": _num(fila["unidades"]),
            "importe": _money(fila["importe"])}


def _transformar_alerta(fila):
    return {"nombre": fila["nombre"], "existencia": _num(fila["existencia"]),
            "minimo": _num(fila["minimo"])}


def _transformar_auditoria(fila):
    return {"operacion": fila["operacion"], "tabla": fila["tabla"],
            "fecha": _fecha(fila["fecha_hora"])}


def _transformar_venta(fila):
    return {"id": str(fila["id_venta"]), "cliente": fila["cliente"],
            "total": _money(fila["total"]), "fecha": _fecha(fila["fecha_hora"])}


def _transformar_inventario(fila):
    return {"nombre": fila["nombre"], "comercial": fila["comercial"],
            "existencia": _num(fila["existencia"]), "minimo": _num(fila["minimo"]),
            "precio": _money(fila["precio"])}


def _transformar_catalogo(fila):
    return {"nombre": fila["nombre"], "comercial": fila["comercial"],
            "precio": _money(fila["precio"]), "receta": bool(fila["requiere_receta"]),
            "minimo": _num(fila["minimo"])}


def _transformar_cliente(fila):
    return {"id": _num(fila["id_cliente"]), "nombre": fila["nombre"],
            "correo": fila["correo"] or "—",
            "telefono": fila["telefono"] or "—", "fecha": _fecha_corta(fila["fecha_registro"])}


def _transformar_empleado(fila):
    return {"nombre": fila["nombre"], "puesto": fila["puesto"],
            "correo": fila["correo"] or "—", "rol": fila["rol"] or "Sin rol"}


def _transformar_receta(fila):
    return {"cliente": fila["cliente"], "medico": fila["medico"],
            "medicamento": fila["medicamento"], "fecha": _fecha(fila["fecha"])}


def _transformar_disponible(fila):
    return {"id": _num(fila["id_medicamento"]), "nombre": fila["nombre"],
            "comercial": fila["comercial"], "precio": _money(fila["precio"]),
            "precio_num": round(float(fila["precio"] or 0), 2),
            "existencia": _num(fila["existencia"]), "minimo": _num(fila["minimo"]),
            "receta": bool(fila["requiere_receta"])}


def _transformar_usuario(fila):
    sucursales = {1: "Norte", 2: "Centro", 3: "Sur"}
    return {"id": _num(fila["id_empleado"]), "nombre": fila["nombre"],
            "puesto": fila["puesto"], "correo": fila["correo"] or "—",
            "usuario": fila["usuario"], "rol": fila["rol"] or "Sin rol",
            "activo": bool(fila["activo"]),
            "sucursal": sucursales.get(_num(fila["id_sucursal"]), "—")}


def _cargar_nodos(datos):
    nodos = []
    for nodo in todos_los_nodos():
        filas = _consultar(nodo, SQL_INDICADORES)
        if filas:
            f = filas[0]
            nodos.append({
                "nombre": nodo.nombre,
                "estado": "Operativo",
                "ventas": _money(f["ventas_hoy"]),
                "productos": _num(f["medicamentos"]),
                "alertas": _num(f["alertas"]),
            })
        else:
            nodos.append({
                "nombre": nodo.nombre, "estado": "Sin conexión",
                "ventas": "—", "productos": "—", "alertas": "—",
            })
    datos["nodos"] = nodos


def obtener_datos(rol, sucursal, id_empleado=None):
    """Devuelve el diccionario de datos para las plantillas."""
    datos = _demo()
    try:
        if rol == "Administrador":
            nodos = todos_los_nodos()
        else:
            try:
                nodos = [Nodo(sucursal)]
            except Exception:
                nodos = []
        if not nodos:
            return datos
        _cargar_indicadores(datos, nodos)
        conservar_demo = datos["origen"] == "demo"
        _cargar_tendencia(datos, nodos)
        _cargar_lista(datos, nodos, SQL_TOP, "top", _transformar_top, 5,
                      orden=lambda x: -x["unidades"], conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_ALERTAS, "alertas", _transformar_alerta, 5,
                      orden=lambda x: x["existencia"], conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_AUDITORIA, "actividad", _transformar_auditoria, 6,
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_VENTAS, "ventas", _transformar_venta, 6,
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_INVENTARIO, "inventario", _transformar_inventario, 8,
                      orden=lambda x: x["existencia"] - x["minimo"],
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_CATALOGO, "catalogo", _transformar_catalogo, 10,
                      orden=lambda x: x["nombre"], conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_CLIENTES, "clientes", _transformar_cliente, 20,
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_EMPLEADOS, "empleados", _transformar_empleado, 8,
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_RECETAS, "recetas", _transformar_receta, 6,
                      conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_DISPONIBLES, "disponibles", _transformar_disponible,
                      50, orden=lambda x: x["nombre"], conservar_demo=conservar_demo)
        _cargar_lista(datos, nodos, SQL_USUARIOS, "usuarios", _transformar_usuario, 30,
                      conservar_demo=conservar_demo)
        if id_empleado:
            _cargar_lista(datos, nodos, SQL_MIS_VENTAS, "mis_ventas", _transformar_venta, 8,
                          conservar_demo=conservar_demo, params=(id_empleado,))
        if rol == "Administrador":
            _cargar_nodos(datos)
    except Exception:
        pass  # se conservan los datos de ejemplo
    return datos
