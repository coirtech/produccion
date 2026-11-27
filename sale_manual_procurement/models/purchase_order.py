from odoo import fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_id = fields.Many2one(
        'res.partner',
        required=False,
    )
    manual_sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta Origen',
        index=True,
        copy=False,
    )

    def button_confirm(self):
        for order in self:
            if not order.partner_id:
                raise UserError(_(
                    'Debes seleccionar un Proveedor en la cotización %s antes de confirmar la compra.'
                ) % order.name)
        return super().button_confirm()
