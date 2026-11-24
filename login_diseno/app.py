from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from psycopg2 import errors as pg_errors
from werkzeug.security import check_password_hash, generate_password_hash
from db import Nodo, todos_los_nodos, transaccion_multinodo
from datos_dashboard import SQL_USUARIO_OBJETIVO, obtener_datos
from perfiles import obtener_seccion, perfil_de, puede_gestionar, roles_asignables

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-secreta"  # cámbiala por una cadena larga y propia
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.jinja_env.filters["money"] = lambda v: "${:,.2f}".format(float(v or 0))

SUCURSALES = {1: "Norte", 2: "Centro", 3: "Sur"}
SUCURSALES_ID = {"Norte": 1, "Centro": 2, "Sur": 3}

PUESTOS = ["Gerente", "Farmaceutico", "Cajero", "Almacenista"]

SQL_NUEVO_USUARIO = """
    WITH e AS (
        INSERT INTO empleados (nombre, correo, puesto) VALUES (%s, %s, %s)
        RETURNING id_empleado
    ), r AS (
        INSERT INTO rol (id_empleado, nombre_rol) SELECT id_empleado, %s FROM e
    )
    INSERT INTO credenciales (id_empleado, usuario, contrasena_hash)
    SELECT id_empleado, %s, %s FROM e
    RETURNING id_empleado
"""
SQL_TICKET = """
    SELECT v.id_venta, v.id_empleado, v.fecha_hora, v.total,
           s.nombre AS sucursal, s.direccion, s.ciudad, s.telefono,
           e.nombre AS cajero, COALESCE(c.nombre, 'Mostrador') AS cliente
    FROM ventas v
    JOIN sucursales s ON s.id_sucursal = v.id_sucursal
    JOIN empleados e ON e.id_empleado = v.id_empleado
    LEFT JOIN clientes c ON c.id_cliente = v.id_cliente
    WHERE v.id_venta = %s
"""

SQL_TICKET_LINEAS = """
    SELECT m.nombre_comercial AS comercial, m.nombre, d.cantidad,
           d.precio_unitario AS precio, d.subtotal
    FROM detalle_venta d JOIN medicamentos m ON m.id_medicamento = d.id_medicamento
    WHERE d.id_venta = %s ORDER BY m.nombre
"""

SQL_USUARIO = """
    SELECT c.id_empleado, c.usuario, c.contrasena_hash, c.activo,
           e.nombre, e.puesto, e.id_sucursal, r.nombre_rol
    FROM credenciales c
    JOIN empleados e ON e.id_empleado = c.id_empleado
    LEFT JOIN rol r  ON r.id_empleado = c.id_empleado AND r.activo
    WHERE c.usuario = %s
    LIMIT 1
"""

SQL_PRODUCTO_VENTA = """
    SELECT i.existencia, m.precio_unitario AS precio, m.requiere_receta,
           m.nombre_comercial AS comercial
    FROM inventarios i JOIN medicamentos m ON m.id_medicamento = i.id_medicamento
    WHERE i.id_sucursal = %s AND i.id_medicamento = %s
"""


def buscar_usuario(usuario):
    """Busca el usuario en los tres nodos.
    Devuelve (fila_o_None, hubo_error_de_conexion)."""
    hubo_error = False
    for nodo in todos_los_nodos():
        try:
            filas = nodo.consultar(SQL_USUARIO, (usuario,))
        except Exception:
            hubo_error = True
            continue
        if filas:
            return filas[0], hubo_error
    return None, hubo_error


def registrar_acceso(u):
    """Guarda la fecha del último acceso en el nodo de la sucursal del usuario."""
    try:
        nodo = next(
            n for n in todos_los_nodos() if n.nombre == SUCURSALES[u["id_sucursal"]]
        )
        nodo.ejecutar(
            "UPDATE credenciales SET ultimo_acceso = now() WHERE id_empleado = %s",
            (u["id_empleado"],),
        )
    except Exception:
        pass  # no impedir el acceso si esto falla


def login_requerido(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def _nodo_actual():
    return Nodo(session["usuario"]["sucursal"])


def _id_sucursal():
    u = session["usuario"]
    return u.get("id_sucursal") or SUCURSALES_ID.get(u.get("sucursal"))

def _sucursal_por_folio(id_venta):
    """Los folios son únicos por rango: Norte 1-9999, Centro 10000-19999, Sur 20000-29999."""
    if 1 <= id_venta <= 9999:
        return "Norte"
    if 10000 <= id_venta <= 19999:
        return "Centro"
    if 20000 <= id_venta <= 29999:
        return "Sur"
    return None

def _slug_gestion():
    return "usuarios" if session["usuario"].get("rol") == "Administrador" else "empleados"


def _sucursal_objetivo():
    """Sucursal del usuario a gestionar; el Gerente queda limitado a la suya."""
    u = session["usuario"]
    sucursal = request.form.get("sucursal") or u.get("sucursal")
    if sucursal not in SUCURSALES_ID:
        return None, "Sucursal no válida."
    if u.get("rol") != "Administrador" and sucursal != u.get("sucursal"):
        return None, "Solo puedes gestionar usuarios de tu sucursal."
    return sucursal, None


def _objetivo_valido(id_empleado, sucursal):
    """Valida jerarquía antes de asignar/borrar roles. Devuelve (fila, error)."""
    u = session["usuario"]
    if not perfil_de(u.get("rol")).get("puede_gestionar"):
        return None, "Tu perfil no puede gestionar usuarios."
    if (sucursal == u.get("sucursal")
            and id_empleado == u.get("id_empleado")):
        return None, "No puedes modificar tu propio usuario."
    try:
        filas = Nodo(sucursal).consultar(SQL_USUARIO_OBJETIVO, (id_empleado,))
    except Exception:
        return None, "No se pudo consultar la base de datos."
    if not filas:
        return None, "El usuario no existe en la sucursal seleccionada."
    if not puede_gestionar(u.get("rol"), filas[0]["rol"] or "Consulta"):
        return None, "No puedes modificar a alguien de tu rango o superior."
    return filas[0], None


@app.route("/")
def index():
    return redirect(url_for("dashboard" if "usuario" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "")

        u, hubo_error = buscar_usuario(usuario)

        if u and u["activo"] and check_password_hash(u["contrasena_hash"], clave):
            session.clear()
            session["usuario"] = {
                "id_empleado": u["id_empleado"],
                "usuario": u["usuario"],
                "nombre": u["nombre"],
                "puesto": u["puesto"],
                "rol": u["nombre_rol"],
                "sucursal": SUCURSALES[u["id_sucursal"]],
                "id_sucursal": u["id_sucursal"],
            }
            registrar_acceso(u)
            return redirect(url_for("dashboard"))

        if not u and hubo_error:
            flash(
                "No se pudo conectar con la base de datos. Intenta de nuevo.", "error"
            )
        else:
            flash("Usuario o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/dashboard")
@app.route("/dashboard/<slug>")
@login_requerido
def dashboard(slug="resumen"):
    u = session["usuario"]
    perfil = perfil_de(u.get("rol"))
    seccion = obtener_seccion(perfil, slug)
    datos = obtener_datos(u.get("rol"), u.get("sucursal"), u.get("id_empleado"))
    return render_template(
        "dashboard.html",
        u=u,
        perfil=perfil,
        seccion=seccion,
        datos=datos,
        hoy=datetime.now().strftime("%d/%m/%Y"),
        roles_asignables=roles_asignables(u.get("rol")),
        sucursales=list(SUCURSALES_ID),
        puestos=PUESTOS,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# Ventas: registro real con descuento de inventario
# ------------------------------------------------------------------
@app.route("/dashboard/ventas/nueva", methods=["POST"])
@login_requerido
def nueva_venta():
    u = session["usuario"]
    if not perfil_de(u.get("rol")).get("puede_vender"):
        flash("Tu perfil no puede registrar ventas.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    try:
        id_medicamento = int(request.form.get("id_medicamento", ""))
        cantidad = int(request.form.get("cantidad", ""))
    except (TypeError, ValueError):
        flash("Selecciona un medicamento y una cantidad válida.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    if cantidad <= 0:
        flash("La cantidad debe ser mayor a cero.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    id_cliente = request.form.get("id_cliente") or None
    medico = request.form.get("nombre_medico", "").strip()
    cedula = request.form.get("cedula_medico", "").strip()
    nodo = _nodo_actual()
    id_sucursal = _id_sucursal()

    try:
        productos = nodo.consultar(
            SQL_PRODUCTO_VENTA, (id_sucursal, id_medicamento)
        )
    except Exception:
        flash("No se pudo consultar el inventario. Intenta de nuevo.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    if not productos:
        flash("El medicamento seleccionado no está disponible.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    producto = productos[0]
    if int(producto["existencia"]) < cantidad:
        flash(
            "Stock insuficiente de {}. Solo hay {} unidades.".format(
                producto["comercial"], producto["existencia"]
            ),
            "error",
        )
        return redirect(url_for("dashboard", slug="ventas"))

    if id_cliente:
        try:
            cliente = nodo.consultar(
                "SELECT 1 FROM clientes WHERE id_cliente = %s", (id_cliente,)
            )
        except Exception:
            cliente = None
        if not cliente:
            flash("El cliente seleccionado no es válido.", "error")
            return redirect(url_for("dashboard", slug="ventas"))

    requiere_receta = bool(producto["requiere_receta"])
    if requiere_receta and not (id_cliente and medico and cedula):
        flash(
            "{} requiere receta: selecciona un cliente e indica médico y cédula.".format(
                producto["comercial"]
            ),
            "error",
        )
        return redirect(url_for("dashboard", slug="ventas"))

    total = round(float(producto["precio"]) * cantidad, 2)
    parametros_stock = (cantidad, id_sucursal, id_medicamento, cantidad)
    descontar_stock = """
        s AS (
            UPDATE inventarios
            SET existencia = existencia - %s, fecha_actualizacion = CURRENT_DATE
            WHERE id_sucursal = %s AND id_medicamento = %s AND existencia >= %s
            RETURNING existencia
        )"""
    detalle = """,
        d AS (
            INSERT INTO detalle_venta (id_venta, id_medicamento, cantidad, precio_unitario)
            SELECT id_venta, %s, %s, %s FROM v
        )"""
    parametros_detalle = (id_medicamento, cantidad, producto["precio"])

    if requiere_receta:
        sql = "WITH " + descontar_stock + """,
        r AS (
            INSERT INTO recetas
                (id_cliente, id_medicamento, id_sucursal, nombre_medico, cedula_medico)
            SELECT %s, %s, %s, %s, %s FROM s RETURNING id_receta
        ),
        v AS (
            INSERT INTO ventas (id_sucursal, id_empleado, id_cliente, id_receta, total)
            SELECT %s, %s, %s, id_receta, %s FROM r RETURNING id_venta
        )""" + detalle + """
        SELECT id_venta FROM v
        """
        params = (
            parametros_stock
            + (id_cliente, id_medicamento, id_sucursal, medico, cedula)
            + (id_sucursal, u["id_empleado"], id_cliente, total)
            + parametros_detalle
        )
    else:
        sql = "WITH " + descontar_stock + """,
        v AS (
            INSERT INTO ventas (id_sucursal, id_empleado, id_cliente, id_receta, total)
            SELECT %s, %s, %s, NULL, %s FROM s RETURNING id_venta
        )""" + detalle + """
        SELECT id_venta FROM v
        """
        params = (
            parametros_stock
            + (id_sucursal, u["id_empleado"], id_cliente, total)
            + parametros_detalle
        )

    try:
        resultado = nodo.transaccion([(sql, params, "venta")])
    except Exception:
        flash("No se pudo registrar la venta. Intenta de nuevo.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    if not resultado.get("venta"):
        flash("No se pudo descontar el stock. La venta no se registró.", "error")
        return redirect(url_for("dashboard", slug="ventas"))

    return redirect(url_for("ver_ticket", id_venta=resultado["venta"]["id_venta"], nueva=1))

# ------------------------------------------------------------------
# Inventario: agregar existencias y dar de alta productos nuevos
# ------------------------------------------------------------------
@app.route("/dashboard/inventario/agregar-stock", methods=["POST"])
@login_requerido
def agregar_stock():
    u = session["usuario"]
    destino = url_for("dashboard", slug="inventario")
    if not perfil_de(u.get("rol")).get("puede_inventario"):
        flash("Tu perfil no puede modificar el inventario.", "error")
        return redirect(destino)

    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(destino)

    try:
        id_medicamento = int(request.form.get("id_medicamento", ""))
        cantidad = int(request.form.get("cantidad", ""))
    except (TypeError, ValueError):
        flash("Indica una cantidad válida.", "error")
        return redirect(destino)
    if not 1 <= cantidad <= 100000:
        flash("La cantidad debe estar entre 1 y 100,000.", "error")
        return redirect(destino)

    nodo = Nodo(sucursal)
    id_sucursal = SUCURSALES_ID[sucursal]
    try:
        existentes = nodo.consultar(
            "SELECT m.nombre_comercial AS comercial FROM inventarios i "
            "JOIN medicamentos m ON m.id_medicamento = i.id_medicamento "
            "WHERE i.id_sucursal = %s AND i.id_medicamento = %s",
            (id_sucursal, id_medicamento),
        )
        if not existentes:
            flash("Ese medicamento no está en el inventario de la sucursal.", "error")
            return redirect(destino)
        resultado = nodo.transaccion([(
            "UPDATE inventarios SET existencia = existencia + %s, "
            "fecha_actualizacion = CURRENT_DATE "
            "WHERE id_sucursal = %s AND id_medicamento = %s RETURNING existencia",
            (cantidad, id_sucursal, id_medicamento), "inv",
        )])
        flash(
            "Se agregaron {} pz de {} en {}. Existencias actuales: {}.".format(
                cantidad, existentes[0]["comercial"], sucursal, resultado["inv"]["existencia"]
            ),
            "exito",
        )
    except Exception:
        flash("No se pudo actualizar el inventario. Intenta de nuevo.", "error")
    return redirect(destino)


@app.route("/dashboard/inventario/nuevo", methods=["POST"])
@login_requerido
def nuevo_producto():
    u = session["usuario"]
    destino = url_for("dashboard", slug="inventario")
    if not perfil_de(u.get("rol")).get("puede_crear_producto"):
        flash("Tu perfil no puede dar de alta productos nuevos.", "error")
        return redirect(destino)

    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(destino)

    nombre = request.form.get("nombre", "").strip()
    comercial = request.form.get("nombre_comercial", "").strip()
    if not nombre or not comercial:
        flash("Escribe el nombre del medicamento y su nombre comercial.", "error")
        return redirect(destino)
    try:
        id_categoria = int(request.form.get("id_categoria", ""))
        id_proveedor = int(request.form.get("id_proveedor", ""))
        precio = Decimal(request.form.get("precio", "").strip()).quantize(Decimal("0.01"))
        minimo = int(request.form.get("stock_minimo", ""))
        existencia = int(request.form.get("existencia", ""))
    except (TypeError, ValueError, InvalidOperation):
        flash("Revisa los datos: categoría, proveedor, precio y cantidades deben ser válidos.", "error")
        return redirect(destino)
    if precio <= 0 or minimo < 0 or existencia < 0:
        flash("El precio debe ser mayor a cero y las cantidades no pueden ser negativas.", "error")
        return redirect(destino)
    requiere_receta = request.form.get("requiere_receta") == "on"

    def accion(cursores):
        # El catálogo debe ser idéntico en los 3 nodos: mismo id en cada uno.
        nuevo_id = 0
        for cur in cursores.values():
            cur.execute(
                "SELECT 1 FROM medicamentos WHERE lower(nombre) = lower(%s) "
                "AND lower(nombre_comercial) = lower(%s)", (nombre, comercial))
            if cur.fetchone():
                raise ValueError("Ese medicamento ya existe en el catálogo.")
            cur.execute("SELECT COALESCE(max(id_medicamento), 0) AS m FROM medicamentos")
            nuevo_id = max(nuevo_id, cur.fetchone()["m"] + 1)
        for nombre_nodo, cur in cursores.items():
            cur.execute(
                "INSERT INTO medicamentos (id_medicamento, id_categoria, id_proveedor, nombre, "
                "nombre_comercial, precio_unitario, requiere_receta, stock_minimo) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (nuevo_id, id_categoria, id_proveedor, nombre, comercial,
                 precio, requiere_receta, minimo))
            cur.execute(
                "INSERT INTO inventarios (id_medicamento, existencia, stock_minimo) "
                "VALUES (%s, %s, %s)",
                (nuevo_id, existencia if nombre_nodo == sucursal else 0, minimo))
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('medicamentos', 'id_medicamento'), "
                "(SELECT max(id_medicamento) FROM medicamentos))")
        return nuevo_id

    try:
        transaccion_multinodo(list(SUCURSALES_ID), accion)
        flash(
            "Producto '{}' agregado al catálogo de las 3 sucursales con {} pz en {}.".format(
                comercial, existencia, sucursal),
            "exito",
        )
    except ValueError as e:
        flash(str(e), "error")
    except Exception:
        flash("No se pudo agregar el producto. Para darlo de alta deben responder los 3 nodos.", "error")
    return redirect(destino)

@app.route("/dashboard/usuarios/nuevo", methods=["POST"])
@login_requerido
def nuevo_usuario():
    u = session["usuario"]
    destino = url_for("dashboard", slug=_slug_gestion())
    if not perfil_de(u.get("rol")).get("puede_gestionar"):
        flash("Tu perfil no puede agregar usuarios.", "error")
        return redirect(destino)

    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(destino)

    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip() or None
    puesto = request.form.get("puesto", "").strip()
    rol = request.form.get("nombre_rol", "").strip()
    usuario = request.form.get("usuario", "").strip()
    clave = request.form.get("clave", "")
    clave2 = request.form.get("clave2", "")

    if not nombre:
        flash("Escribe el nombre completo.", "error")
    elif puesto not in PUESTOS:
        flash("Selecciona un puesto válido.", "error")
    elif rol not in roles_asignables(u.get("rol")):
        flash("No tienes permiso para asignar ese rol.", "error")
    elif len(usuario) < 4 or " " in usuario:
        flash("El usuario debe tener al menos 4 caracteres y no llevar espacios.", "error")
    elif len(clave) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "error")
    elif clave != clave2:
        flash("Las contraseñas no coinciden.", "error")
    else:
        existente, hubo_error = buscar_usuario(usuario)
        if existente:
            flash("Ese usuario ya existe, elige otro.", "error")
        elif hubo_error:
            flash("No se pudo verificar el usuario en todas las sucursales. Intenta de nuevo.", "error")
        else:
            try:
                Nodo(sucursal).transaccion([(
                    SQL_NUEVO_USUARIO,
                    (nombre, correo, puesto, rol, usuario, generate_password_hash(clave)),
                    "nuevo",
                )])
                flash("Usuario '{}' creado en {} con rol {}.".format(usuario, sucursal, rol), "exito")
            except pg_errors.UniqueViolation:
                flash("Ese correo ya está registrado en la sucursal.", "error")
            except Exception:
                flash("No se pudo crear el usuario. Intenta de nuevo.", "error")
    return redirect(destino)

# ------------------------------------------------------------------
# Ticket de venta
# ------------------------------------------------------------------
@app.route("/dashboard/ventas/<int:id_venta>/ticket")
@login_requerido
def ver_ticket(id_venta):
    u = session["usuario"]
    perfil = perfil_de(u.get("rol"))
    if not any(slug in ("ventas", "historial") for slug, _, _ in perfil["menu"]):
        flash("Tu perfil no puede consultar tickets.", "error")
        return redirect(url_for("dashboard"))

    sucursal = _sucursal_por_folio(id_venta)
    if not sucursal or (u.get("rol") != "Administrador" and sucursal != u.get("sucursal")):
        flash("Ese ticket no existe en tu sucursal.", "error")
        return redirect(url_for("dashboard"))

    try:
        nodo = Nodo(sucursal)
        ventas = nodo.consultar(SQL_TICKET, (id_venta,))
        lineas = nodo.consultar(SQL_TICKET_LINEAS, (id_venta,)) if ventas else []
    except Exception:
        flash("No se pudo consultar el ticket. Intenta de nuevo.", "error")
        return redirect(url_for("dashboard"))

    if not ventas or (u.get("rol") == "Operador" and ventas[0]["id_empleado"] != u["id_empleado"]):
        flash("Ese ticket no existe o no es de tus ventas.", "error")
        return redirect(url_for("dashboard"))

    slugs = [slug for slug, _, _ in perfil["menu"]]
    if request.args.get("nueva"):
        volver = url_for("dashboard", slug="ventas")
    elif "historial" in slugs:
        volver = url_for("dashboard", slug="historial")
    elif "ventas" in slugs:
        volver = url_for("dashboard", slug="ventas")
    else:
        volver = url_for("dashboard")
    return render_template(
        "ticket.html",
        v=ventas[0],
        lineas=lineas,
        piezas=sum(int(l["cantidad"]) for l in lineas),
        nueva=bool(request.args.get("nueva")),
        volver=volver,
    )

# ------------------------------------------------------------------
# Gestión de roles y usuarios ( Administrador / Gerente )
# ------------------------------------------------------------------
@app.route("/dashboard/usuarios/<int:id_empleado>/rol", methods=["POST"])
@login_requerido
def asignar_rol(id_empleado):
    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))
    objetivo, error = _objetivo_valido(id_empleado, sucursal)
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))

    nuevo_rol = request.form.get("nombre_rol", "").strip()
    if nuevo_rol not in roles_asignables(session["usuario"].get("rol")):
        flash("No tienes permiso para asignar ese rol.", "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))

    nodo = Nodo(sucursal)
    id_sucursal = SUCURSALES_ID[sucursal]
    try:
        nodo.transaccion([
            (
                "UPDATE rol SET activo = false WHERE id_empleado = %s",
                (id_empleado,), None,
            ),
            (
                """
                INSERT INTO rol (id_empleado, id_sucursal, nombre_rol, activo, fecha_asignacion)
                VALUES (%s, %s, %s, true, CURRENT_DATE)
                ON CONFLICT (id_empleado, id_sucursal, nombre_rol)
                DO UPDATE SET activo = true, fecha_asignacion = CURRENT_DATE
                """,
                (id_empleado, id_sucursal, nuevo_rol), None,
            ),
            (
                "UPDATE credenciales SET activo = true WHERE id_empleado = %s",
                (id_empleado,), None,
            ),
        ])
        flash("Rol '{}' asignado a {}.".format(nuevo_rol, objetivo["nombre"]), "exito")
    except Exception:
        flash("No se pudo asignar el rol. Intenta de nuevo.", "error")
    return redirect(url_for("dashboard", slug=_slug_gestion()))


@app.route("/dashboard/usuarios/<int:id_empleado>/baja", methods=["POST"])
@login_requerido
def dar_baja(id_empleado):
    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))
    objetivo, error = _objetivo_valido(id_empleado, sucursal)
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))
    try:
        Nodo(sucursal).transaccion([
            (
                "UPDATE credenciales SET activo = false WHERE id_empleado = %s",
                (id_empleado,), None,
            ),
            (
                "UPDATE rol SET activo = false WHERE id_empleado = %s",
                (id_empleado,), None,
            ),
        ])
        flash("Acceso de {} dado de baja.".format(objetivo["nombre"]), "exito")
    except Exception:
        flash("No se pudo dar de baja al usuario.", "error")
    return redirect(url_for("dashboard", slug=_slug_gestion()))


@app.route("/dashboard/usuarios/<int:id_empleado>/alta", methods=["POST"])
@login_requerido
def dar_alta(id_empleado):
    sucursal, error = _sucursal_objetivo()
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))
    objetivo, error = _objetivo_valido(id_empleado, sucursal)
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard", slug=_slug_gestion()))
    try:
        nodo = Nodo(sucursal)
        operaciones = [(
            "UPDATE credenciales SET activo = true WHERE id_empleado = %s",
            (id_empleado,), None,
        )]
        activos = nodo.consultar(
            "SELECT 1 FROM rol WHERE id_empleado = %s AND activo", (id_empleado,)
        )
        if not activos:
            operaciones.append((
                """
                INSERT INTO rol (id_empleado, id_sucursal, nombre_rol, activo, fecha_asignacion)
                VALUES (%s, %s, 'Consulta', true, CURRENT_DATE)
                ON CONFLICT (id_empleado, id_sucursal, nombre_rol)
                DO UPDATE SET activo = true
                """,
                (id_empleado, SUCURSALES_ID[sucursal]), None,
            ))
        nodo.transaccion(operaciones)
        flash("Acceso de {} reactivado.".format(objetivo["nombre"]), "exito")
    except Exception:
        flash("No se pudo reactivar al usuario.", "error")
    return redirect(url_for("dashboard", slug=_slug_gestion()))


if __name__ == "__main__":
    app.run(debug=True)
