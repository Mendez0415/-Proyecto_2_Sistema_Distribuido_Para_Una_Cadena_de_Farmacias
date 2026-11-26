"""
Persistencia de los objetos del modelo en PostgreSQL (patrón Repositorio).

Cada repositorio trabaja sobre UN nodo (una sucursal) y se apoya en la clase
Nodo de db.py. Los objetos se guardan con obj.a_fila() y se reconstruyen con
_desde_fila(), así que la base de datos nunca se mezcla con las reglas del modelo.
"""
import psycopg2.extras

from modelo import (Cliente, DetalleVenta, Empleado, Inventario, Medicamento,
                    MedicamentoControlado, Receta, Venta)


class Repositorio:
    tabla = None          # nombre de la tabla
    columna_id = None     # nombre de su llave primaria

    def __init__(self, nodo):
        self.nodo = nodo

    # --- cada repositorio sabe reconstruir su objeto ---
    def _desde_fila(self, fila):
        raise NotImplementedError

    @staticmethod
    def _sql_insert(tabla, fila, columna_id=None):
        columnas = ", ".join(fila)
        marcas = ", ".join(["%s"] * len(fila))
        retorno = " RETURNING {}".format(columna_id) if columna_id else ""
        return "INSERT INTO {} ({}) VALUES ({}){}".format(tabla, columnas, marcas, retorno)

    # --- CRUD ---
    def guardar(self, objeto):
        """INSERT: guarda el objeto y le asigna el id que generó la base."""
        fila = objeto.a_fila()
        sql = self._sql_insert(self.tabla, fila, self.columna_id)
        resultado = self.nodo.transaccion([(sql, tuple(fila.values()), "nuevo")])
        objeto._asignar_id(resultado["nuevo"][self.columna_id])
        return objeto

    def obtener(self, id_):
        """SELECT por id: devuelve el objeto o None si no existe."""
        filas = self.nodo.consultar(
            "SELECT * FROM {} WHERE {} = %s".format(self.tabla, self.columna_id), (id_,))
        return self._desde_fila(filas[0]) if filas else None

    def listar(self, limite=100):
        filas = self.nodo.consultar(
            "SELECT * FROM {} ORDER BY {} LIMIT %s".format(self.tabla, self.columna_id), (limite,))
        return [self._desde_fila(f) for f in filas]

    def actualizar(self, objeto):
        """UPDATE: guarda los cambios de un objeto que ya existe. True si se actualizó."""
        if objeto.id is None:
            raise ValueError("Primero hay que guardar el objeto.")
        fila = objeto.a_fila()
        asignaciones = ", ".join("{} = %s".format(c) for c in fila)
        sql = "UPDATE {} SET {} WHERE {} = %s".format(self.tabla, asignaciones, self.columna_id)
        resultado = self.nodo.transaccion([(sql, tuple(fila.values()) + (objeto.id,), "r")])
        return resultado["r"]["rowcount"] > 0

    def eliminar(self, id_):
        """DELETE: True si había algo que eliminar."""
        sql = "DELETE FROM {} WHERE {} = %s".format(self.tabla, self.columna_id)
        return self.nodo.transaccion([(sql, (id_,), "r")])["r"]["rowcount"] > 0


class RepositorioCliente(Repositorio):
    tabla, columna_id = "clientes", "id_cliente"

    def _desde_fila(self, f):
        return Cliente(f["nombre"], f["correo"], f["telefono"], f["direccion"],
                       f["curp"], f["fecha_registro"], id_=f["id_cliente"])


class RepositorioEmpleado(Repositorio):
    tabla, columna_id = "empleados", "id_empleado"

    def _desde_fila(self, f):
        return Empleado(f["nombre"], f["puesto"], f["id_sucursal"], f["correo"],
                        f["telefono"], f["fecha_ingreso"], id_=f["id_empleado"])


class RepositorioMedicamento(Repositorio):
    tabla, columna_id = "medicamentos", "id_medicamento"

    def _desde_fila(self, f):
        # Polimorfismo al leer: la base decide qué clase de objeto se crea.
        clase = MedicamentoControlado if f["requiere_receta"] else Medicamento
        return clase(f["nombre"], f["nombre_comercial"], f["precio_unitario"],
                     f["id_categoria"], f["id_proveedor"], f["stock_minimo"],
                     id_=f["id_medicamento"])


class RepositorioReceta(Repositorio):
    tabla, columna_id = "recetas", "id_receta"

    def _desde_fila(self, f):
        return Receta(f["id_cliente"], f["id_medicamento"], f["nombre_medico"],
                      f["cedula_medico"], f["fecha_emision"], id_=f["id_receta"])


class RepositorioInventario(Repositorio):
    tabla, columna_id = "inventarios", "id_inventario"

    def _desde_fila(self, f):
        return Inventario(f["id_medicamento"], f["id_sucursal"], f["existencia"],
                          f["stock_minimo"], id_=f["id_inventario"])

    def obtener_por_medicamento(self, id_medicamento, id_sucursal):
        filas = self.nodo.consultar(
            "SELECT * FROM inventarios WHERE id_medicamento = %s AND id_sucursal = %s",
            (id_medicamento, id_sucursal))
        return self._desde_fila(filas[0]) if filas else None

    def actualizar(self, inventario):
        if inventario.id is None:
            raise ValueError("Primero hay que guardar el objeto.")
        sql = ("UPDATE inventarios SET existencia = %s, stock_minimo = %s, "
               "fecha_actualizacion = CURRENT_DATE WHERE id_inventario = %s")
        params = (inventario.existencia, inventario.stock_minimo, inventario.id)
        return self.nodo.transaccion([(sql, params, "r")])["r"]["rowcount"] > 0


class RepositorioVenta(Repositorio):
    tabla, columna_id = "ventas", "id_venta"

    def _desde_fila(self, f):
        return Venta(f["id_empleado"], f["id_sucursal"], f["id_cliente"],
                     f["id_receta"], f["fecha_hora"], id_=f["id_venta"])

    def guardar(self, venta, descontar_stock=True):
        """Guarda la venta, sus renglones y (opcional) descuenta el inventario.

        Todo ocurre en una sola transacción: si algo falla (por ejemplo, no hay
        existencias suficientes) se hace ROLLBACK y no queda nada a medias.
        """
        if not venta.detalles:
            raise ValueError("La venta no tiene productos.")
        conn = self.nodo.conectar()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                fila = venta.a_fila()
                cur.execute(self._sql_insert(self.tabla, fila, self.columna_id),
                            tuple(fila.values()))
                id_venta = cur.fetchone()[self.columna_id]
                for d in venta.detalles:
                    renglon = dict(d.a_fila(), id_venta=id_venta)
                    cur.execute(self._sql_insert("detalle_venta", renglon),
                                tuple(renglon.values()))
                    if descontar_stock:
                        cur.execute(
                            "UPDATE inventarios SET existencia = existencia - %s, "
                            "fecha_actualizacion = CURRENT_DATE "
                            "WHERE id_sucursal = %s AND id_medicamento = %s AND existencia >= %s",
                            (d.cantidad, venta.id_sucursal, d.id_medicamento, d.cantidad))
                        if cur.rowcount == 0:
                            raise ValueError("Existencias insuficientes del medicamento {}."
                                             .format(d.id_medicamento))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        venta._asignar_id(id_venta)
        return venta

    def obtener(self, id_):
        filas = self.nodo.consultar("SELECT * FROM ventas WHERE id_venta = %s", (id_,))
        if not filas:
            return None
        venta = self._desde_fila(filas[0])
        detalles = self.nodo.consultar(
            "SELECT id_medicamento, cantidad, precio_unitario FROM detalle_venta "
            "WHERE id_venta = %s ORDER BY id_medicamento", (id_,))
        for d in detalles:
            venta._agregar_detalle_existente(
                DetalleVenta(d["id_medicamento"], d["cantidad"], d["precio_unitario"]))
        return venta

    def actualizar(self, venta):
        raise NotImplementedError("Una venta registrada no se modifica.")