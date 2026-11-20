# -*- coding: utf-8 -*-
"""Control de sobre-recepcion para Odoo 19.

La comprobacion ocurre antes de completar el movimiento de stock; no cambia
las cantidades ni los calculos de las ordenes de compra.
"""

from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError


def _fmt_qty(value):
    """Texto corto, por ejemplo 100 en lugar de 100.0."""
    return f'{value:g}'


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _coir_check_incoming_qty_limits(self):
        """Bloquear excesos de recepcion sin interferir con otras operaciones.

        - Solo entradas desde proveedor/transito (no salidas, traspasos,
          ajustes ni devoluciones de clientes).
        - Compara la cantidad que se va a validar con la demanda del movimiento.
        - Para recepciones de compras, tambien compara el acumulado recibido
          mas lo que se valida ahora contra la linea exacta de la OC.
        - Usa la UoM del movimiento/OC, y considera solo cantidades marcadas
          como recogidas cuando existen operaciones detalladas.
        """
        moves = self.filtered(
            lambda m: m.picking_id
            and m.picking_type_id.code == 'incoming'
            and m.location_id.usage in ('supplier', 'transit')
            and m.state not in ('done', 'cancel')
            and m.picked
        )

        current_by_purchase_line = defaultdict(float)
        purchase_lines = {}
        first_move_by_purchase_line = {}

        for move in moves:
            actual = move._get_picked_quantity()
            if move.product_uom.compare(actual, 0) <= 0:
                continue

            demand = move.product_uom_qty
            if move.product_uom.compare(actual, demand) > 0:
                raise UserError(_(
                    'No puedes exceder la cantidad ordenada.\n\n'
                    'Recepción: %(receipt)s\n'
                    'Producto: %(product)s\n'
                    'Demanda: %(demand)s %(unit)s\n'
                    'Intentas recibir: %(actual)s %(unit)s\n\n'
                    'Reduce la cantidad recibida antes de validar.',
                    receipt=move.picking_id.name,
                    product=move.product_id.display_name,
                    demand=_fmt_qty(demand),
                    actual=_fmt_qty(actual),
                    unit=move.product_uom.name,
                ))

            # Los usuarios de Almacen pueden recibir sin permisos de Compras.
            # Solo leemos la linea vinculada; nunca la modificamos.
            purchase_line = move.purchase_line_id.sudo() if move.purchase_line_id else False
            if not purchase_line or not move._should_count_for_quantity_received():
                continue

            qty_in_po_unit = move.product_uom._compute_quantity(
                actual, purchase_line.product_uom_id, round=False,
            )
            current_by_purchase_line[purchase_line.id] += qty_in_po_unit
            purchase_lines[purchase_line.id] = purchase_line
            first_move_by_purchase_line.setdefault(purchase_line.id, move)

        for purchase_line_id, qty_current in current_by_purchase_line.items():
            line = purchase_lines[purchase_line_id]
            previously_received = line.qty_received
            qty_ordered = line.product_qty
            qty_total = previously_received + qty_current
            uom = line.product_uom_id
            if uom.compare(qty_total, qty_ordered) > 0:
                move = first_move_by_purchase_line[purchase_line_id]
                available = max(0.0, qty_ordered - previously_received)
                raise UserError(_(
                    'No puedes exceder la cantidad ordenada.\n\n'
                    'Orden de compra: %(purchase)s\n'
                    'Recepción: %(receipt)s\n'
                    'Producto: %(product)s\n'
                    'Cantidad ordenada: %(ordered)s %(unit)s\n'
                    'Recibido anteriormente: %(previous)s %(unit)s\n'
                    'Intentas recibir ahora: %(current)s %(unit)s\n'
                    'Máximo pendiente por recibir: %(available)s %(unit)s\n\n'
                    'Reduce la cantidad recibida antes de validar.',
                    purchase=line.order_id.name,
                    receipt=move.picking_id.name,
                    product=line.product_id.display_name,
                    ordered=_fmt_qty(qty_ordered),
                    previous=_fmt_qty(previously_received),
                    current=_fmt_qty(qty_current),
                    available=_fmt_qty(available),
                    unit=uom.name,
                ))

    def _action_done(self, cancel_backorder=False):
        """Ultima barrera: incluye validaciones desde wizards y procesos API."""
        self._coir_check_incoming_qty_limits()
        return super()._action_done(cancel_backorder=cancel_backorder)
