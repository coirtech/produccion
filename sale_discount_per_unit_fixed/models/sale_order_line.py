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

    # Memoria de la edicion del formulario. Permite distinguir una linea nueva
    # que nunca tuvo descuento fijo de una linea nueva que acaba de borrarlo.
    # No interviene en los importes ni cambia las reglas de las tarifas.
    fixed_discount_per_unit_applied = fields.Boolean(
        default=False, copy=False, readonly=True,
    )

    @api.onchange('fixed_discount_per_unit')
    def _onchange_fixed_discount_per_unit(self):
        for line in self:
            if line.fixed_discount_per_unit:
                line.fixed_discount_per_unit_applied = True
                if not line.display_type:
                    line.discount = line._fixed_discount_percentage()
            elif (line.fixed_discount_per_unit_applied
                  or line._origin.fixed_discount_per_unit):
                # Cero es una instruccion de retirar el descuento, no de
                # conservar el porcentaje interno calculado anteriormente.
                line.discount = 0.0
                line.fixed_discount_per_unit_applied = False

    def _fixed_discount_percentage(self):
        self.ensure_one()
        return (100.0 * self.fixed_discount_per_unit / self.price_unit
                if self.price_unit > 0 else 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if 'fixed_discount_per_unit' in vals:
                vals['fixed_discount_per_unit_applied'] = bool(vals['fixed_discount_per_unit'])
        return super().create(vals_list)

    def write(self, vals):
        if 'fixed_discount_per_unit' not in vals:
            return super().write(vals)

        vals = dict(vals)
        vals['fixed_discount_per_unit_applied'] = bool(vals['fixed_discount_per_unit'])
        if vals['fixed_discount_per_unit']:
            return super().write(vals)

        # Al guardar (incluidos importaciones y RPC), no depender del onchange
        # ni de que la columna de porcentaje este visible. Limitar el reinicio
        # a las lineas que realmente usaban el descuento monetario.
        clearing = self.filtered(lambda line: line.fixed_discount_per_unit
                                 or line.fixed_discount_per_unit_applied)
        remaining = self - clearing
        result = True
        if clearing:
            result = super(SaleOrderLine, clearing).write(dict(vals, discount=0.0))
        if remaining:
            result = super(SaleOrderLine, remaining).write(vals) and result
        return result

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
                line.discount = line._fixed_discount_percentage()

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
