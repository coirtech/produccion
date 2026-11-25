from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    coir_meal_control_enabled = fields.Boolean(
        string="Control manual de jornada COIRTECH",
        default=False,
        help="Seis movimientos manuales en el quiosco. Comida y salidas temporales pagadas, sin alertas de duración.",
    )

    @api.constrains("coir_meal_control_enabled", "auto_check_out")
    def _check_coir_manual_checkout(self):
        for company in self:
            if company.coir_meal_control_enabled and company.auto_check_out:
                raise ValidationError(_(
                    "Para usar el control manual de comidas COIRTECH, desactiva "
                    "Salida automática en Asistencias. La salida final debe "
                    "registrarla el empleado o corregirla Recursos Humanos."
                ))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    coir_meal_control_enabled = fields.Boolean(
        related="company_id.coir_meal_control_enabled",
        readonly=False,
    )
