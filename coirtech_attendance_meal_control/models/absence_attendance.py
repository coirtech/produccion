from odoo import api, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _coir_absence_spans(self):
        return [(row.employee_id.id, row.check_in, row.check_out) for row in self.sudo()]

    @api.model_create_multi
    def create(self, vals_list):
        attendances = super().create(vals_list)
        # All channels (COIRTECH kiosk, native kiosk, manual, import) pass here.
        self.env["coir.attendance.absence"]._reconcile_employees(
            attendances.employee_id.sudo(), attendance_spans=attendances._coir_absence_spans(),
        )
        return attendances

    def write(self, vals):
        affects_presence = bool({"employee_id", "check_in", "check_out", "in_mode", "out_mode"}.intersection(vals))
        employees = self.employee_id.sudo() if affects_presence else self.env["hr.employee"]
        before = []
        if affects_presence:
            self.check_access("write")
            before = self._coir_absence_spans()
            if vals.get("employee_id"):
                employees |= self.env["hr.employee"].sudo().browse(vals["employee_id"]).exists()
            employees._coir_lock_employee()
        result = super().write(vals)
        if affects_presence:
            self.env["coir.attendance.absence"]._reconcile_employees(
                employees, attendance_spans=before + self._coir_absence_spans(),
            )
        return result

    def unlink(self):
        self.check_access("unlink")
        employees = self.employee_id.sudo()
        before = self._coir_absence_spans()
        employees._coir_lock_employee()
        result = super().unlink()
        self.env["coir.attendance.absence"]._reconcile_employees(employees, attendance_spans=before)
        return result
