"""
Pruebas de persistencia y CRUD sobre objetos (Farmacia Yza, nodo Norte).

Uso:  py pruebas_persistencia.py

Usa los datos del script de la sucursal (medicamentos 1 y 3, inventario del
medicamento 1) y deja la base como la encontró: todo lo que crea lo elimina
y devuelve el stock que descuenta.
"""
import sys

from db import Nodo
from modelo import Cliente, Empleado, Receta, Venta
from repositorios import (RepositorioCliente, RepositorioEmpleado, RepositorioInventario,
                          RepositorioMedicamento, RepositorioReceta, RepositorioVenta)

NODO = "Norte"
ID_SUCURSAL = 1
ID_TEMPRA = 1        # Paracetamol (venta libre)
ID_AMOXIL = 3        # Amoxicilina (requiere receta)

CORREO_CLIENTE = "prueba.oo.cliente@yza.com"
CORREO_BORRAR = "prueba.oo.borrar@yza.com"
CORREO_EMPLEADO = "prueba.oo.empleado@yza.com"

nodo = Nodo(NODO)
clientes = RepositorioCliente(nodo)
empleados = RepositorioEmpleado(nodo)
medicamentos = RepositorioMedicamento(nodo)
recetas = RepositorioReceta(nodo)
inventarios = RepositorioInventario(nodo)
ventas = RepositorioVenta(nodo)

fallos = []


def verificar(descripcion, condicion):
    print("   [{}] {}".format("OK" if condicion else "FALLO", descripcion))
    if not condicion:
        fallos.append(descripcion)


def limpiar():
    """Borra cualquier dato de prueba (también restos de una corrida interrumpida)."""
    nodo.transaccion([
        ("DELETE FROM ventas WHERE id_empleado IN "
         "(SELECT id_empleado FROM empleados WHERE correo = %s)", (CORREO_EMPLEADO,), None),
        ("DELETE FROM recetas WHERE id_cliente IN "
         "(SELECT id_cliente FROM clientes WHERE correo = %s)", (CORREO_CLIENTE,), None),
        ("DELETE FROM empleados WHERE correo = %s", (CORREO_EMPLEADO,), None),
        ("DELETE FROM clientes WHERE correo IN (%s, %s)", (CORREO_CLIENTE, CORREO_BORRAR), None),
    ])


# ----------------------------------------------------------------------
def prueba_1_alta(ctx):
    cliente = Cliente("Cliente Prueba OO", correo=CORREO_CLIENTE,
                      telefono="993-000-0000", curp="abcd123456hxyzrs09")
    verificar("el objeto nuevo todavía no tiene id", cliente.id is None)
    clientes.guardar(cliente)
    verificar("la base le asignó un id ({})".format(cliente.id), cliente.id is not None)
    filas = nodo.consultar("SELECT correo, curp FROM clientes WHERE id_cliente = %s", (cliente.id,))
    verificar("la fila existe en la tabla clientes", len(filas) == 1 and filas[0]["correo"] == CORREO_CLIENTE)
    verificar("la CURP se guardó normalizada en mayúsculas", filas[0]["curp"] == "ABCD123456HXYZRS09")
    ctx["cliente"] = cliente


def prueba_2_lectura(ctx):
    id_cliente = ctx["cliente"].id
    del ctx["cliente"]                       # el objeto original desaparece de memoria
    recargado = clientes.obtener(id_cliente)
    verificar("se reconstruye un objeto Cliente desde la base", type(recargado).__name__ == "Cliente")
    verificar("conserva sus datos ({})".format(recargado.descripcion()),
              recargado.nombre == "Cliente Prueba OO" and recargado.correo == CORREO_CLIENTE)
    ctx["cliente"] = recargado

    amoxil = medicamentos.obtener(ID_AMOXIL)
    verificar("el medicamento que exige receta se lee como {}".format(type(amoxil).__name__),
              type(amoxil).__name__ == "MedicamentoControlado")
    verificar("sin receta no se puede vender", amoxil.puede_venderse() is False)

    receta = recetas.guardar(Receta(recargado.id, ID_AMOXIL, "Dr. Prueba", "1234567"))
    receta_leida = recetas.obtener(receta.id)
    verificar("la receta guardada se recupera igual", receta_leida == receta)
    verificar("con la receta recuperada sí se puede vender", amoxil.puede_venderse(receta_leida) is True)


def prueba_3_modificacion(ctx):
    cliente = ctx["cliente"]
    cliente.telefono = "993-222-2222"
    cliente.direccion = "Calle Prueba 123"
    verificar("actualizar devuelve True", clientes.actualizar(cliente) is True)
    recargado = clientes.obtener(cliente.id)
    verificar("el teléfono nuevo persiste", recargado.telefono == "993-222-2222")
    verificar("la dirección nueva persiste", recargado.direccion == "Calle Prueba 123")
    try:
        cliente.correo = "correo-invalido"
        rechazado = False
    except ValueError:
        rechazado = True
    verificar("un valor inválido se rechaza en el objeto", rechazado)
    verificar("y la base conserva el correo válido", clientes.obtener(cliente.id).correo == CORREO_CLIENTE)


def prueba_4_eliminacion(ctx):
    temporal = clientes.guardar(Cliente("Para borrar", correo=CORREO_BORRAR))
    verificar("el cliente temporal existe", clientes.obtener(temporal.id) is not None)
    verificar("eliminar devuelve True", clientes.eliminar(temporal.id) is True)
    verificar("ya no se puede recuperar", clientes.obtener(temporal.id) is None)
    verificar("eliminar de nuevo devuelve False", clientes.eliminar(temporal.id) is False)


def prueba_5_venta_commit_rollback(ctx):
    cliente = ctx["cliente"]
    empleado = empleados.guardar(Empleado("Cajero Prueba", "Cajero", ID_SUCURSAL, correo=CORREO_EMPLEADO))
    tempra = medicamentos.obtener(ID_TEMPRA)
    existencia_antes = inventarios.obtener_por_medicamento(ID_TEMPRA, ID_SUCURSAL).existencia

    # COMMIT: venta con renglón y descuento de stock en una sola transacción
    venta = Venta(empleado.id, ID_SUCURSAL, id_cliente=cliente.id)
    venta.agregar_detalle(tempra, 2)
    ventas.guardar(venta)
    verificar("la venta se guardó con folio {}".format(venta.id), venta.id is not None)
    leida = ventas.obtener(venta.id)
    verificar("se recupera con su renglón y total ({})".format(leida.total),
              len(leida.detalles) == 1 and leida.total == tempra.precio * 2)
    inv = inventarios.obtener_por_medicamento(ID_TEMPRA, ID_SUCURSAL)
    verificar("el inventario bajó 2 piezas", inv.existencia == existencia_antes - 2)

    # ROLLBACK: más piezas de las que hay
    ventas_antes = nodo.consultar("SELECT count(*) AS n FROM ventas WHERE id_empleado = %s", (empleado.id,))[0]["n"]
    mala = Venta(empleado.id, ID_SUCURSAL)
    mala.agregar_detalle(tempra, existencia_antes + 1000)
    try:
        ventas.guardar(mala)
        fallo_esperado = False
    except ValueError:
        fallo_esperado = True
    verificar("la venta sin existencias suficientes se rechaza", fallo_esperado)
    ventas_despues = nodo.consultar("SELECT count(*) AS n FROM ventas WHERE id_empleado = %s", (empleado.id,))[0]["n"]
    verificar("ROLLBACK: no quedó ninguna venta a medias", ventas_despues == ventas_antes)
    verificar("ROLLBACK: el inventario no cambió",
              inventarios.obtener_por_medicamento(ID_TEMPRA, ID_SUCURSAL).existencia == existencia_antes - 2)

    # Se devuelve el stock usando el propio objeto Inventario
    inv.agregar(2)
    inventarios.actualizar(inv)
    verificar("el stock de prueba se devolvió",
              inventarios.obtener_por_medicamento(ID_TEMPRA, ID_SUCURSAL).existencia == existencia_antes)


PRUEBAS = [
    ("Prueba 1 - Alta (CREATE)", prueba_1_alta),
    ("Prueba 2 - Lectura y persistencia (READ)", prueba_2_lectura),
    ("Prueba 3 - Modificación (UPDATE)", prueba_3_modificacion),
    ("Prueba 4 - Eliminación (DELETE)", prueba_4_eliminacion),
    ("Prueba 5 - Venta: COMMIT y ROLLBACK", prueba_5_venta_commit_rollback),
]

if __name__ == "__main__":
    ctx = {}
    resumen = []
    try:
        limpiar()
        for titulo, funcion in PRUEBAS:
            print("\n" + titulo)
            antes = len(fallos)
            try:
                funcion(ctx)
            except Exception as e:
                verificar("la prueba terminó sin errores ({}: {})".format(type(e).__name__, e), False)
            resumen.append((titulo, len(fallos) == antes))
    finally:
        limpiar()

    print("\n" + "=" * 52)
    for titulo, ok in resumen:
        print("{:<42} {}".format(titulo, "OK" if ok else "FALLO"))
    print("=" * 52)
    print("{} de {} pruebas aprobadas".format(sum(ok for _, ok in resumen), len(PRUEBAS)))
    sys.exit(1 if fallos else 0)