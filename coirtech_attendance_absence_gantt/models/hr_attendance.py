"""Feed the existing Enterprise Gantt through its native server pipeline.

No JavaScript methods, templates, payload shapes or colors are replaced. The
projection inherits the installed hr.attendance model, including Enterprise's
own get_gantt_data implementation. Its positive rows are the original values.
"""
from odoo import api, models, _
from odoo.exceptions import UserError


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model
    def get_gantt_data(self, *args, **kwargs):
        if self._name == "hr.attendance":
            self.check_access("read")
            return self.env["coir.attendance.gantt"].get_gantt_data(*args, **kwargs)
        # On the projection this reaches the exact installed Enterprise
        # implementation, including open attendances, grouping and progress.
        return super().get_gantt_data(*args, **kwargs)

    def _coir_guard_virtual_attendance(self):
        if self._name == "hr.attendance" and any(i < 0 for i in self.ids):
            self.env["coir.attendance.absence"].browse([-i for i in self.ids if i < 0]).check_access("read")
            raise UserError(_(
                "FALTA: el empleado todavía no ha registrado entrada ese día. "
                "Este indicador no tiene horas trabajadas ni es una asistencia. "
                "Desaparece automáticamente al registrar la entrada."
            ))

    @api.readonly
    def web_read(self, specification):
        self._coir_guard_virtual_attendance()
        return super().web_read(specification)

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        if self._name == "hr.attendance" and self.id < 0:
            absence = self.env["coir.attendance.absence"].browse(-self.id)
            absence.check_access("read")
            return absence.get_formview_action(access_uid=access_uid)
        return super().get_formview_action(access_uid=access_uid)

    def write(self, vals):
        self._coir_guard_virtual_attendance()
        return super().write(vals)

    def unlink(self):
        self._coir_guard_virtual_attendance()
        return super().unlink()
