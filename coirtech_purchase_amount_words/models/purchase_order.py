# -*- coding: utf-8 -*-
from odoo import api, fields, models

from ..utils.amount_words import amount_to_words, amount_words_label


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    coir_purchase_amount_total_in_words = fields.Char(
        string='Importe con letra',
        compute='_compute_coir_purchase_amount_total_in_words',
        readonly=True,
        store=False,
        help='Total con impuestos, en pesos o dolares, segun el idioma del proveedor (espanol o ingles).',
    )

    coir_purchase_amount_words_label = fields.Char(
        string='Etiqueta de importe con letra',
        compute='_compute_coir_purchase_amount_total_in_words',
        readonly=True,
        store=False,
    )

    @api.depends('amount_total', 'currency_id', 'currency_id.name',
                 'currency_id.rounding', 'partner_id', 'partner_id.lang')
    def _compute_coir_purchase_amount_total_in_words(self):
        for order in self:
            currency = order.currency_id
            language = order.partner_id.lang
            order.coir_purchase_amount_words_label = amount_words_label(language)
            if currency and currency.name in ('MXN', 'USD'):
                amount = currency.round(order.amount_total)
                order.coir_purchase_amount_total_in_words = amount_to_words(
                    amount, currency.name, language
                )
            else:
                order.coir_purchase_amount_total_in_words = False
