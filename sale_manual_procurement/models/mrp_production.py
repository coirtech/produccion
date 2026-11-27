from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    manual_sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta Origen',
        index=True,
        copy=False,
    )
