# -*- coding: utf-8 -*-
from odoo import api, fields, models

from ..utils.money_to_words_es import amount_to_words_es


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    coir_amount_total_in_words = fields.Char(
        string='Importe con letra',
        compute='_compute_coir_amount_total_in_words',
        readonly=True,
        store=False,
        help='Total con impuestos y descuentos, expresado en letras en MXN o USD.',
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_coir_amount_total_in_words(self):
        for order in self:
            currency = order.currency_id
            if currency.name in ('MXN', 'USD'):
                # Use Odoo's currency rounding for consistency with the PDF total.
                rounded_amount = currency.round(order.amount_total)
                order.coir_amount_total_in_words = amount_to_words_es(
                    rounded_amount, currency.name
                )
            else:
                order.coir_amount_total_in_words = False
