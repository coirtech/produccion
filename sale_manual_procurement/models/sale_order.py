from odoo import api, fields, models, _


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
    all_purchase_count = fields.Integer(
        string='Total Compras',
        compute='_compute_all_procurement_counts',
    )
    all_mrp_count = fields.Integer(
        string='Total Fabricaciones',
        compute='_compute_all_procurement_counts',
    )

    def _get_all_linked_purchases(self):
        self.ensure_one()
        origin_pos = self.env['purchase.order'].search([
            ('origin', '=', self.name),
            ('company_id', '=', self.company_id.id),
        ])
        native_pos = self.env['purchase.order']
        if 'purchase_line_ids' in self.env['sale.order.line']._fields:
            native_pos = self.order_line.purchase_line_ids.order_id
        return self.manual_purchase_ids | native_pos | origin_pos

    def _get_all_linked_mos(self):
        self.ensure_one()
        origin_mos = self.env['mrp.production'].search([
            ('origin', '=', self.name),
            ('company_id', '=', self.company_id.id),
        ])
        native_mos = self.env['mrp.production']
        if 'procurement_group_id' in self._fields and self.procurement_group_id:
            if 'stock_move_ids' in self.procurement_group_id._fields:
                moves = self.procurement_group_id.stock_move_ids
                if 'created_production_id' in moves._fields:
                    native_mos = moves.created_production_id
        return self.manual_mrp_ids | native_mos | origin_mos

    @api.depends('manual_purchase_ids', 'manual_mrp_ids', 'state')
    def _compute_all_procurement_counts(self):
        for order in self:
            order.all_purchase_count = len(order._get_all_linked_purchases())
            order.all_mrp_count = len(order._get_all_linked_mos())

    def action_confirm(self):
        res = super().action_confirm()

        if (
            len(self) == 1
            and not self.env.context.get('skip_procurement_wizard')
            and not self.env.context.get('website_id')
        ):
            stockable_lines = self.order_line.filtered(
                lambda l: not l.display_type and l.product_id.type in ('consu', 'product')
            )
            if stockable_lines:
                return {
                    'name': _('Seleccionar Abastecimiento (Compra o Fabricación)'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.procurement.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_sale_order_id': self.id,
                    },
                }
        return res

    def action_view_all_linked_purchases(self):
        self.ensure_one()
        purchases = self._get_all_linked_purchases()
        action = self.env['ir.actions.actions']._for_xml_id('purchase.purchase_rfq')
        if len(purchases) == 1:
            action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            action['res_id'] = purchases.id
        else:
            action['domain'] = [('id', 'in', purchases.ids)]
        return action

    def action_view_all_linked_mos(self):
        self.ensure_one()
        mos = self._get_all_linked_mos()
        action = self.env['ir.actions.actions']._for_xml_id('mrp.mrp_production_action')
        if len(mos) == 1:
            action['views'] = [(self.env.ref('mrp.mrp_production_form_view').id, 'form')]
            action['res_id'] = mos.id
        else:
            action['domain'] = [('id', 'in', mos.ids)]
        return action
