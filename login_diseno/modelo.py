"""
Modelo orientado a objetos de Farmacia Yza.

Aquí solo viven las clases del dominio (reglas y validaciones).
Guardarlas y leerlas de PostgreSQL se hace en repositorios.py.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

PUESTOS = ("Gerente", "Farmaceutico", "Cajero", "Almacenista")


def _texto_o_none(valor):
    valor = (valor or "").strip()
    return valor or None


# ======================================================================
# Clase base: todo lo que se guarda en la base tiene un id
# ======================================================================
class Entidad(ABC):
    def __init__(self, id_=None):
        self._id = id_

    @property
    def id(self):
        return self._id

    def _asignar_id(self, valor):
        """Lo usa el repositorio después de insertar (el id lo genera la base)."""
        self._id = valor

    @abstractmethod
    def a_fila(self):
        """Datos del objeto como diccionario columna -> valor (para guardarlo)."""

    def __eq__(self, otro):
        return type(self) is type(otro) and self.id == otro.id and self.a_fila() == otro.a_fila()

    __hash__ = None


# ======================================================================
# HERENCIA 1: Persona -> Cliente / Empleado
# ======================================================================
class Persona(Entidad):
    def __init__(self, nombre, correo=None, telefono=None, id_=None):
        super().__init__(id_)
        self.nombre = nombre
        self.correo = correo
        self.telefono = telefono

    # --- encapsulamiento: atributos privados con validación ---
    @property
    def nombre(self):
        return self._nombre

    @nombre.setter
    def nombre(self, valor):
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("El nombre es obligatorio.")
        self._nombre = valor

    @property
    def correo(self):
        return self._correo

    @correo.setter
    def correo(self, valor):
        valor = _texto_o_none(valor)
        if valor is not None and ("@" not in valor or "." not in valor.split("@")[-1]):
            raise ValueError("El correo no es válido.")
        self._correo = valor

    @property
    def telefono(self):
        return self._telefono

    @telefono.setter
    def telefono(self, valor):
        self._telefono = _texto_o_none(valor)

    # --- POLIMORFISMO 1: cada subclase se describe a su manera ---
    @abstractmethod
    def descripcion(self):
        ...


class Cliente(Persona):
    def __init__(self, nombre, correo=None, telefono=None, direccion=None,
                 curp=None, fecha_registro=None, id_=None):
        super().__init__(nombre, correo, telefono, id_)
        self.direccion = direccion
        self.curp = curp
        self.fecha_registro = fecha_registro or date.today()

    @property
    def direccion(self):
        return self._direccion

    @direccion.setter
    def direccion(self, valor):
        self._direccion = _texto_o_none(valor)

    @property
    def curp(self):
        return self._curp

    @curp.setter
    def curp(self, valor):
        valor = _texto_o_none(valor)
        if valor is not None:
            valor = valor.upper()
            if len(valor) != 18:
                raise ValueError("La CURP debe tener 18 caracteres.")
        self._curp = valor

    def descripcion(self):
        return "Cliente: {}{}".format(self.nombre, " (CURP {})".format(self.curp) if self.curp else "")

    def a_fila(self):
        return {"nombre": self.nombre, "correo": self.correo, "telefono": self.telefono,
                "direccion": self.direccion, "fecha_registro": self.fecha_registro,
                "curp": self.curp}


class Empleado(Persona):
    def __init__(self, nombre, puesto, id_sucursal, correo=None, telefono=None,
                 fecha_ingreso=None, id_=None):
        super().__init__(nombre, correo, telefono, id_)
        self.puesto = puesto
        self.id_sucursal = id_sucursal
        self.fecha_ingreso = fecha_ingreso or date.today()

    @property
    def puesto(self):
        return self._puesto

    @puesto.setter
    def puesto(self, valor):
        if valor not in PUESTOS:
            raise ValueError("Puesto no válido: {}.".format(valor))
        self._puesto = valor

    @property
    def id_sucursal(self):
        return self._id_sucursal

    @id_sucursal.setter
    def id_sucursal(self, valor):
        if valor not in (1, 2, 3):
            raise ValueError("La sucursal debe ser 1, 2 o 3.")
        self._id_sucursal = valor

    def descripcion(self):
        return "Empleado: {} ({}, sucursal {})".format(self.nombre, self.puesto, self.id_sucursal)

    def a_fila(self):
        return {"id_sucursal": self.id_sucursal, "nombre": self.nombre,
                "correo": self.correo, "telefono": self.telefono,
                "puesto": self.puesto, "fecha_ingreso": self.fecha_ingreso}


# ======================================================================
# HERENCIA 2: Medicamento -> MedicamentoControlado
# ======================================================================
class Medicamento(Entidad):
    requiere_receta = False          # la subclase lo redefine

    def __init__(self, nombre, nombre_comercial, precio, id_categoria, id_proveedor,
                 stock_minimo=10, id_=None):
        super().__init__(id_)
        self.nombre = nombre
        self.nombre_comercial = nombre_comercial
        self.precio = precio
        self.id_categoria = id_categoria
        self.id_proveedor = id_proveedor
        self.stock_minimo = stock_minimo

    @property
    def nombre(self):
        return self._nombre

    @nombre.setter
    def nombre(self, valor):
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("El nombre del medicamento es obligatorio.")
        self._nombre = valor

    @property
    def nombre_comercial(self):
        return self._nombre_comercial

    @nombre_comercial.setter
    def nombre_comercial(self, valor):
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("El nombre comercial es obligatorio.")
        self._nombre_comercial = valor

    @property
    def precio(self):
        return self._precio

    @precio.setter
    def precio(self, valor):
        try:
            valor = Decimal(str(valor)).quantize(Decimal("0.01"))
        except InvalidOperation:
            raise ValueError("El precio no es válido.")
        if valor <= 0:
            raise ValueError("El precio debe ser mayor a cero.")
        self._precio = valor

    @property
    def stock_minimo(self):
        return self._stock_minimo

    @stock_minimo.setter
    def stock_minimo(self, valor):
        if int(valor) < 0:
            raise ValueError("El stock mínimo no puede ser negativo.")
        self._stock_minimo = int(valor)

    # --- POLIMORFISMO 2: ¿se puede vender con lo que presenta el cliente? ---
    def puede_venderse(self, receta=None):
        return True

    def a_fila(self):
        return {"id_categoria": self.id_categoria, "id_proveedor": self.id_proveedor,
                "nombre": self.nombre, "nombre_comercial": self.nombre_comercial,
                "precio_unitario": self.precio, "requiere_receta": self.requiere_receta,
                "stock_minimo": self.stock_minimo}


class MedicamentoControlado(Medicamento):
    requiere_receta = True

    def puede_venderse(self, receta=None):
        return receta is not None and receta.aplica_a(self)


class Receta(Entidad):
    def __init__(self, id_cliente, id_medicamento, nombre_medico, cedula_medico,
                 fecha_emision=None, id_=None):
        super().__init__(id_)
        self.id_cliente = id_cliente
        self.id_medicamento = id_medicamento
        self.nombre_medico = nombre_medico
        self.cedula_medico = cedula_medico
        self.fecha_emision = fecha_emision or date.today()

    @property
    def fecha_emision(self):
        return self._fecha_emision

    @fecha_emision.setter
    def fecha_emision(self, valor):
        if valor > date.today():
            raise ValueError("La fecha de emisión no puede ser futura.")
        self._fecha_emision = valor

    def aplica_a(self, medicamento):
        """La receta sirve si fue emitida para ese medicamento."""
        return self.id_medicamento == medicamento.id

    def a_fila(self):
        return {"id_cliente": self.id_cliente, "id_medicamento": self.id_medicamento,
                "nombre_medico": self.nombre_medico, "cedula_medico": self.cedula_medico,
                "fecha_emision": self.fecha_emision}


# ======================================================================
# Inventario: la existencia solo cambia con agregar() y retirar()
# ======================================================================
class Inventario(Entidad):
    def __init__(self, id_medicamento, id_sucursal, existencia=0, stock_minimo=10, id_=None):
        super().__init__(id_)
        self.id_medicamento = id_medicamento
        self.id_sucursal = id_sucursal
        self._existencia = 0
        self.stock_minimo = stock_minimo
        if existencia:
            self.agregar(existencia)

    @property
    def existencia(self):
        return self._existencia            # solo lectura

    @property
    def stock_minimo(self):
        return self._stock_minimo

    @stock_minimo.setter
    def stock_minimo(self, valor):
        if int(valor) < 0:
            raise ValueError("El stock mínimo no puede ser negativo.")
        self._stock_minimo = int(valor)

    @property
    def bajo_minimo(self):
        return self._existencia <= self._stock_minimo

    def agregar(self, cantidad):
        if int(cantidad) <= 0:
            raise ValueError("La cantidad a agregar debe ser mayor a cero.")
        self._existencia += int(cantidad)

    def retirar(self, cantidad):
        if int(cantidad) <= 0:
            raise ValueError("La cantidad a retirar debe ser mayor a cero.")
        if int(cantidad) > self._existencia:
            raise ValueError("Existencias insuficientes: hay {}.".format(self._existencia))
        self._existencia -= int(cantidad)

    def a_fila(self):
        return {"id_sucursal": self.id_sucursal, "id_medicamento": self.id_medicamento,
                "existencia": self.existencia, "stock_minimo": self.stock_minimo}


# ======================================================================
# Venta con sus renglones (composición)
# ======================================================================
class DetalleVenta:
    def __init__(self, id_medicamento, cantidad, precio_unitario):
        if int(cantidad) <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        self.id_medicamento = id_medicamento
        self.cantidad = int(cantidad)
        self.precio_unitario = Decimal(str(precio_unitario))

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def a_fila(self):
        return {"id_medicamento": self.id_medicamento, "cantidad": self.cantidad,
                "precio_unitario": self.precio_unitario}


class Venta(Entidad):
    def __init__(self, id_empleado, id_sucursal, id_cliente=None, id_receta=None,
                 fecha_hora=None, id_=None):
        super().__init__(id_)
        self.id_empleado = id_empleado
        self.id_sucursal = id_sucursal
        self.id_cliente = id_cliente
        self.id_receta = id_receta
        self.fecha_hora = fecha_hora or datetime.now()
        self._detalles = []

    @property
    def detalles(self):
        return tuple(self._detalles)       # copia: no se modifica desde fuera

    @property
    def total(self):
        return sum((d.subtotal for d in self._detalles), Decimal("0"))

    def agregar_detalle(self, medicamento, cantidad, receta=None):
        # Aquí se usa el polimorfismo: cada tipo de medicamento decide si se puede vender.
        if not medicamento.puede_venderse(receta):
            raise PermissionError("'{}' requiere una receta válida.".format(medicamento.nombre_comercial))
        if any(d.id_medicamento == medicamento.id for d in self._detalles):
            raise ValueError("Ese medicamento ya está en la venta.")
        self._detalles.append(DetalleVenta(medicamento.id, cantidad, medicamento.precio))
        if receta is not None:
            self.id_receta = receta.id

    def _agregar_detalle_existente(self, detalle):
        """Lo usa el repositorio al reconstruir una venta que ya estaba guardada."""
        self._detalles.append(detalle)

    def a_fila(self):
        return {"id_sucursal": self.id_sucursal, "id_empleado": self.id_empleado,
                "id_cliente": self.id_cliente, "id_receta": self.id_receta,
                "fecha_hora": self.fecha_hora, "total": self.total}