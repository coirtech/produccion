# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _is_portal_quote_sign_request(self):
        """Retorna True únicamente durante la petición de firma en el portal de ventas."""
        if not request or not getattr(request, 'httprequest', None):
            return False
        path = request.httprequest.path or ''
        return path.startswith('/my/orders/') and path.endswith('/accept')

    def _action_confirm(self):
        if self._is_portal_quote_sign_request():
            return True
        return super()._action_confirm()

    def action_confirm(self):
        if self._is_portal_quote_sign_request():
            return True
        return super().action_confirm()

    def _send_order_confirmation_mail(self):
        if self._is_portal_quote_sign_request():
            return
        return super()._send_order_confirmation_mail()
