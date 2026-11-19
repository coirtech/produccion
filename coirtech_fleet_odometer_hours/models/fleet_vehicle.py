from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    odometer_unit = fields.Selection(
        selection_add=[("hours", "Horas")],
        ondelete={"hours": "set default"},
    )
