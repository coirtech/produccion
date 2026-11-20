# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _pre_action_done_hook(self):
        """Mostrar el error al pulsar Validar, antes del asistente de pendientes."""
        result = super()._pre_action_done_hook()
        self.move_ids._coir_check_incoming_qty_limits()
        return result
