from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    fixed_discount_per_unit = fields.Monetary(
        string='Descuento por pieza',
        currency_field='currency_id',
        default=0.0,
        help='Importe fijo descontado a CADA unidad, en la moneda de la cotizacion. '
             'Es un importe monetario, no un porcentaje.',
    )

    @api.depends(
        'product_id', 'product_uom_id', 'product_uom_qty',
        'price_unit', 'fixed_discount_per_unit',
    )
    def _compute_discount(self):
        """Conserva las funciones estandar de descuentos/facturacion de Odoo.

        Internamente la base de Odoo trabaja con un porcentaje. Solo en las
        lineas que usan el descuento fijo, se calcula ese porcentaje con la
        precision completa del float, para obtener el importe por pieza.
        """
        super()._compute_discount()
        for line in self:
            if line.fixed_discount_per_unit and not line.display_type:
                line.discount = (
                    100.0 * line.fixed_discount_per_unit / line.price_unit
                    if line.price_unit > 0 else 0.0
                )

    @api.constrains('fixed_discount_per_unit', 'price_unit', 'display_type', 'is_downpayment')
    def _check_fixed_discount_per_unit(self):
        for line in self:
            amount = line.fixed_discount_per_unit
            if amount < 0:
                raise ValidationError(_('El descuento por pieza no puede ser negativo.'))
            if not amount:
                continue
            if line.display_type or line.is_downpayment:
                raise ValidationError(_('El descuento por pieza solo puede aplicarse a productos.'))
            currency = line.currency_id or line.env.company.currency_id
            if line.price_unit <= 0 or currency.compare_amounts(amount, line.price_unit) > 0:
                raise ValidationError(_(
                    'El descuento por pieza no puede ser mayor al precio unitario del producto.'
                ))
