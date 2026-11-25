import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    coir_absence_enabled = fields.Boolean(
        string="Faltas automáticas COIRTECH", default=True,
        help="A partir de las 09:00, de lunes a viernes, para empleados activos con jornada "
             "programada y sin asistencia. Requiere el control COIRTECH de la empresa.",
    )
    coir_absence_tz = fields.Selection(
        [(name, name) for name in pytz.common_timezones],
        string="Zona horaria de las faltas", required=True, default="America/Mexico_City",
        help="Define la fecha local y el corte de las 09:00. No cambia la zona de las asistencias.",
    )

    @api.constrains("coir_absence_tz")
    def _check_coir_absence_timezone(self):
        for company in self:
            if company.coir_absence_tz not in pytz.all_timezones_set:
                raise ValidationError(_("Selecciona una zona horaria válida para las faltas."))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    coir_absence_enabled = fields.Boolean(related="company_id.coir_absence_enabled", readonly=False)
    coir_absence_tz = fields.Selection(related="company_id.coir_absence_tz", readonly=False)
