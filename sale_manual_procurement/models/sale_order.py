from odoo import fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    manual_purchase_ids = fields.One2many(
        'purchase.order',
        'manual_sale_order_id',
        string='Cotizaciones de Compra Generadas',
    )
    manual_mrp_ids = fields.One2many(
        'mrp.production',
        'manual_sale_order_id',
        string='Órdenes de Fabricación Generadas',
    )

    def action_confirm(self):
        res = super().action_confirm()

        if (
            len(self) == 1
            and not self.env.context.get('skip_procurement_wizard')
            and not self.env.context.get('website_id')
        ):
            wizard = self.env['sale.procurement.wizard'].create_from_sale_order(self)
            if wizard:
                return {
                    'name': _('Generar Compra o Fabricación'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.procurement.wizard',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'target': 'new',
                }
        return res
