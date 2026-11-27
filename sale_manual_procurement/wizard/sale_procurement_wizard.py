from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


class SaleProcurementWizard(models.TransientModel):
    _name = 'sale.procurement.wizard'
    _description = 'Asistente de Compra o Fabricación desde Venta'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'sale.procurement.wizard.line',
        'wizard_id',
        string='Productos',
    )

    @staticmethod
    def _get_sale_line_uom(s_line):
        if 'product_uom_id' in s_line._fields:
            return s_line.product_uom_id
        return s_line.product_uom

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sale_id = self.env.context.get('default_sale_order_id')
        if sale_id and 'line_ids' in fields_list:
            sale = self.env['sale.order'].browse(sale_id)
            lines_vals = []
            for s_line in sale.order_line.filtered(
                lambda l: not l.display_type and l.product_id.type in ('consu', 'product')
            ):
                bom_map = self.env['mrp.bom']._bom_find(
                    s_line.product_id,
                    company_id=sale.company_id.id,
                    bom_type='normal',
                )
                has_bom = bool(bom_map.get(s_line.product_id))
                uom = self._get_sale_line_uom(s_line)
                lines_vals.append(Command.create({
                    'sale_line_id': s_line.id,
                    'product_id': s_line.product_id.id,
                    'product_uom_qty': s_line.product_uom_qty,
                    'product_uom_id': uom.id,
                    'action_type': 'manufacture' if has_bom else 'purchase',
                }))
            res['line_ids'] = lines_vals
        return res

    def action_set_all_purchase(self):
        self.ensure_one()
        self.line_ids.write({'action_type': 'purchase'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_set_all_manufacture(self):
        self.ensure_one()
        self.line_ids.write({'action_type': 'manufacture'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_documents(self):
        self.ensure_one()
        sale = self.sale_order_id

        purchase_lines = self.line_ids.filtered(lambda l: l.action_type == 'purchase')
        mrp_lines = self.line_ids.filtered(lambda l: l.action_type == 'manufacture')

        # 1. Validar Listas de Materiales antes de crear registros
        bom_by_line = {}
        for m_line in mrp_lines:
            bom_map = self.env['mrp.bom']._bom_find(
                m_line.product_id,
                company_id=sale.company_id.id,
                bom_type='normal',
            )
            bom = bom_map.get(m_line.product_id)
            if not bom:
                raise UserError(_(
                    'El producto "%s" no tiene una Lista de Materiales (BoM) activa para fabricarse.'
                ) % m_line.product_id.display_name)
            bom_by_line[m_line.id] = bom

        # 2. Crear UNA SOLA Cotización de Compra (RFQ) sin proveedor asignado
        if purchase_lines:
            warehouse = sale.warehouse_id
            picking_type = warehouse.in_type_id
            po_line_fields = self.env['purchase.order.line']._fields
            uom_field_name = 'product_uom_id' if 'product_uom_id' in po_line_fields else 'product_uom'

            po_line_vals = []
            for p_line in purchase_lines:
                s_line = p_line.sale_line_id
                line_dict = {
                    'product_id': p_line.product_id.id,
                    'name': s_line.name or p_line.product_id.display_name,
                    'product_qty': p_line.product_uom_qty,
                    uom_field_name: p_line.product_uom_id.id,
                    'price_unit': p_line.product_id.standard_price or 0.0,
                    'date_planned': sale.commitment_date or fields.Datetime.now(),
                }
                if 'sale_order_id' in po_line_fields:
                    line_dict['sale_order_id'] = sale.id
                if 'sale_line_id' in po_line_fields:
                    line_dict['sale_line_id'] = s_line.id
                po_line_vals.append(Command.create(line_dict))

            po_vals = {
                'partner_id': False,
                'origin': sale.name,
                'company_id': sale.company_id.id,
                'currency_id': sale.currency_id.id or sale.company_id.currency_id.id,
                'date_order': fields.Datetime.now(),
                'manual_sale_order_id': sale.id,
                'order_line': po_line_vals,
            }
            if picking_type:
                po_vals['picking_type_id'] = picking_type.id

            self.env['purchase.order'].create(po_vals)

        # 3. Crear Órdenes de Fabricación (MO) nativas con su Lista de Materiales
        mo_fields = self.env['mrp.production']._fields
        for m_line in mrp_lines:
            bom = bom_by_line[m_line.id]
            warehouse = sale.warehouse_id
            mo_picking_type = warehouse.manu_type_id

            mo_vals = {
                'product_id': m_line.product_id.id,
                'product_qty': m_line.product_uom_qty,
                'product_uom_id': m_line.product_uom_id.id,
                'bom_id': bom.id,
                'origin': sale.name,
                'company_id': sale.company_id.id,
                'date_start': fields.Datetime.now(),
                'manual_sale_order_id': sale.id,
            }
            if 'procurement_group_id' in mo_fields and 'procurement_group_id' in sale._fields and sale.procurement_group_id:
                mo_vals['procurement_group_id'] = sale.procurement_group_id.id

            if mo_picking_type:
                mo_vals['picking_type_id'] = mo_picking_type.id
                mo_vals['location_src_id'] = mo_picking_type.default_location_src_id.id or warehouse.lot_stock_id.id
                mo_vals['location_dest_id'] = mo_picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id

            self.env['mrp.production'].create(mo_vals)

        return {'type': 'ir.actions.act_window_close'}


class SaleProcurementWizardLine(models.TransientModel):
    _name = 'sale.procurement.wizard.line'
    _description = 'Línea del Asistente de Compra o Fabricación'

    wizard_id = fields.Many2one(
        'sale.procurement.wizard',
        required=True,
        ondelete='cascade',
    )
    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Línea de Venta',
        required=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        readonly=True,
    )
    product_uom_qty = fields.Float(
        string='Cantidad',
        required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='UdM',
        required=True,
        readonly=True,
    )
    action_type = fields.Selection(
        selection=[
            ('purchase', 'Cotización de Compra'),
            ('manufacture', 'Orden de Fabricación'),
        ],
        string='Acción a Generar',
        required=True,
        default='purchase',
    )
