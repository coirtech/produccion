# -*- coding: utf-8 -*-
from odoo import api, fields, models

from ..utils.money_to_words_es import amount_to_words_es


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    coir_purchase_amount_total_in_words = fields.Char(
        string='Importe con letra',
        compute='_compute_coir_purchase_amount_total_in_words',
        readonly=True,
        store=False,
        help='Total de la orden de compra con impuestos, expresado en letras en pesos o dolares.',
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_coir_purchase_amount_total_in_words(self):
        for order in self:
            currency = order.currency_id
            if currency and currency.name in ('MXN', 'USD'):
                amount = currency.round(order.amount_total)
                order.coir_purchase_amount_total_in_words = amount_to_words_es(
                    amount, currency.name
                )
            else:
                order.coir_purchase_amount_total_in_words = False
