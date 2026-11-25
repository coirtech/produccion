from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoirAttendanceReportLayoutWizard(models.TransientModel):
    _inherit = 'coir.attendance.report.wizard'

    layout_company_id = fields.Many2one(
        'res.company', string='Empresa a personalizar',
        compute='_compute_layout_company', store=True, readonly=False,
        domain="[('id', 'in', company_ids)]",
        help='Cada empresa conserva sus propias columnas para Excel y PDF.',
    )
    layout_output_format = fields.Selection(
        [('xlsx', 'Excel'), ('pdf', 'PDF')],
        string='Formato a personalizar', required=True, default='xlsx',
    )

    @api.depends('company_ids')
    def _compute_layout_company(self):
        for wizard in self:
            if wizard.layout_company_id not in wizard.company_ids:
                wizard.layout_company_id = (
                    wizard.env.company if wizard.env.company in wizard.company_ids
                    else wizard.company_ids[:1]
                )

    def action_customize_columns(self):
        self.ensure_one()
        self._check_report_filters()
        if not self.layout_company_id or self.layout_company_id not in self.company_ids:
            raise ValidationError(_('Selecciona una de las empresas del reporte para personalizar sus columnas.'))
        return self.env['coir.attendance.report.layout']._coir_open_editor(
            self.layout_company_id, self.layout_output_format,
        )
