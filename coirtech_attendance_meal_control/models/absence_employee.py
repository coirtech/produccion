import pytz

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    coir_absent_today = fields.Boolean(
        string="Tiene falta hoy", compute="_compute_coir_absent_today",
        groups="hr_attendance.group_hr_attendance_officer",
    )
    coir_absence_label = fields.Char(
        string="Falta de hoy", compute="_compute_coir_absent_today",
        groups="hr_attendance.group_hr_attendance_officer",
    )

    @api.depends_context("uid", "allowed_company_ids")
    @api.depends("company_id")
    def _compute_coir_absent_today(self):
        now = fields.Datetime.now()
        for company, employees in self.grouped("company_id").items():
            timezone = company.sudo().coir_absence_tz or "America/Mexico_City"
            day = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone)).date()
            absent_ids = set(self.env["coir.attendance.absence"].search([
                ("employee_id", "in", employees.ids), ("company_id", "=", company.id),
                ("date", "=", day), ("state", "=", "absent"),
            ]).employee_id.ids)
            for employee in employees:
                employee.coir_absent_today = employee.id in absent_ids
                employee.coir_absence_label = "FALTA" if employee.id in absent_ids else False

    def _coir_lock_employee(self):
        result = super()._coir_lock_employee()
        self.env["coir.attendance.absence"].invalidate_model()
        return result
