from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


class SaleProcurementWizard(models.TransientModel):
    _name = 'sale.procurement.wizard'
    _description = 'Asistente de Compra o Fabricación desde Venta'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
    )
    action_type = fields.Selection(
        selection=[
            ('purchase', 'Cotización de Compra'),
            ('manufacture', 'Orden de Fabricación'),
        ],
        string='Opción',
        required=True,
        default='purchase',
    )

    @staticmethod
    def _get_sale_line_uom(s_line):
        if 'product_uom_id' in s_line._fields:
            return s_line.product_uom_id
        return s_line.product_uom

    @api.model
    def create_from_sale_order(self, sale):
        stockable_lines = sale.order_line.filtered(
            lambda l: not l.display_type and l.product_id.type in ('consu', 'product')
        )
        if not stockable_lines:
            return False

        return self.create({
            'sale_order_id': sale.id,
            'action_type': 'purchase',
        })

    def action_generate_documents(self):
        self.ensure_one()
        sale = self.sale_order_id
        stockable_lines = sale.order_line.filtered(
            lambda l: not l.display_type and l.product_id.type in ('consu', 'product')
        )
        if not stockable_lines:
            return {'type': 'ir.actions.act_window_close'}

        # OPCIÓN 1: Crear UNA SOLA Cotización de Compra (RFQ) sin proveedor asignado
        if self.action_type == 'purchase':
            warehouse = sale.warehouse_id
            picking_type = warehouse.in_type_id
            po_line_fields = self.env['purchase.order.line']._fields
            uom_field_name = 'product_uom_id' if 'product_uom_id' in po_line_fields else 'product_uom'

            po_line_vals = []
            for s_line in stockable_lines:
                uom = self._get_sale_line_uom(s_line)
                line_dict = {
                    'product_id': s_line.product_id.id,
                    'name': s_line.name or s_line.product_id.display_name,
                    'product_qty': s_line.product_uom_qty,
                    uom_field_name: uom.id,
                    'price_unit': s_line.product_id.standard_price or 0.0,
                }
                if 'date_planned' in po_line_fields:
                    line_dict['date_planned'] = sale.commitment_date or fields.Datetime.now()
                if 'sale_line_id' in po_line_fields:
                    line_dict['sale_line_id'] = s_line.id
                if 'sale_order_id' in po_line_fields:
                    line_dict['sale_order_id'] = sale.id
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

        # OPCIÓN 2: Crear Órdenes de Fabricación (MO) nativas con su Lista de Materiales
        elif self.action_type == 'manufacture':
            bom_by_line = {}
            for s_line in stockable_lines:
                bom_map = self.env['mrp.bom']._bom_find(
                    s_line.product_id,
                    company_id=sale.company_id.id,
                    bom_type='normal',
                )
                bom = bom_map.get(s_line.product_id)
                if not bom:
                    raise UserError(_(
                        'El producto "%s" no tiene una Lista de Materiales (BoM) activa para fabricarse.'
                    ) % s_line.product_id.display_name)
                bom_by_line[s_line.id] = bom

            mo_fields = self.env['mrp.production']._fields
            warehouse = sale.warehouse_id
            mo_picking_type = warehouse.manu_type_id

            for s_line in stockable_lines:
                bom = bom_by_line[s_line.id]
                uom = self._get_sale_line_uom(s_line)

                mo_vals = {
                    'product_id': s_line.product_id.id,
                    'product_qty': s_line.product_uom_qty,
                    'product_uom_id': uom.id,
                    'bom_id': bom.id,
                    'origin': sale.name,
                    'company_id': sale.company_id.id,
                    'date_start': fields.Datetime.now(),
                    'manual_sale_order_id': sale.id,
                }
                if 'procurement_group_id' in mo_fields and 'procurement_group_id' in sale._fields and sale.procurement_group_id:
                    mo_vals['procurement_group_id'] = sale.procurement_group_id.id
                if 'sale_line_id' in mo_fields:
                    mo_vals['sale_line_id'] = s_line.id
                if 'reference_ids' in mo_fields and 'reference_ids' in sale._fields and sale.reference_ids:
                    mo_vals['reference_ids'] = [Command.set(sale.reference_ids.ids)]

                if mo_picking_type:
                    mo_vals['picking_type_id'] = mo_picking_type.id
                    mo_vals['location_src_id'] = mo_picking_type.default_location_src_id.id or warehouse.lot_stock_id.id
                    mo_vals['location_dest_id'] = mo_picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id

                self.env['mrp.production'].create(mo_vals)

        return {'type': 'ir.actions.act_window_close'}


# Se conserva el modelo vacío para permitir una actualización limpia desde versiones anteriores
class SaleProcurementWizardLine(models.TransientModel):
    _name = 'sale.procurement.wizard.line'
    _description = 'Línea del Asistente de Compra o Fabricación'

    wizard_id = fields.Many2one('sale.procurement.wizard', ondelete='cascade')
