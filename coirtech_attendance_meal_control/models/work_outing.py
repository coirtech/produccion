from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .attendance import _COIR_WRITE_TOKEN


class CoirWorkOuting(models.Model):
    _name = "coir.work.outing"
    _description = "Salida temporal de trabajo COIRTECH"
    _order = "start, id"

    attendance_id = fields.Many2one("hr.attendance", string="Jornada", required=True, readonly=True, ondelete="restrict", index=True)
    employee_id = fields.Many2one("hr.employee", related="attendance_id.employee_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", related="attendance_id.coir_company_id", store=True, readonly=True, index=True)
    start = fields.Datetime(string="Salida de trabajo", required=True, readonly=True)
    end = fields.Datetime(string="Regreso al trabajo", readonly=True)
    duration_hours = fields.Float(string="Duración confirmada", compute="_compute_duration", store=True)
    state = fields.Selection([
        ("open", "Fuera por trabajo"), ("returned", "Regreso registrado"),
        ("missing", "Salida sin regreso registrado"),
    ], string="Estado", compute="_compute_duration", store=True)
    review_note = fields.Text(string="Última revisión de RH", readonly=True)

    @api.depends("start", "end", "attendance_id.check_out")
    def _compute_duration(self):
        for outing in self:
            outing.duration_hours = (outing.end - outing.start).total_seconds() / 3600 if outing.end else 0.0
            outing.state = "returned" if outing.end else ("missing" if outing.attendance_id.check_out else "open")

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN):
            raise AccessError(_("Registra la salida de trabajo desde el quiosco COIRTECH."))
        records = super().create(vals_list)
        records.attendance_id._coir_validate_intervals()
        records.attendance_id._coir_touch_revision()
        return records

    def write(self, vals):
        if not (self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN):
            raise AccessError(_("Utiliza Corregir salida con el motivo de la revisión."))
        if set(vals) - {"start", "end", "review_note"}:
            raise AccessError(_("No se puede reasignar una salida de trabajo a otra jornada."))
        self.employee_id._coir_lock_employee()
        result = super().write(vals)
        self.attendance_id._coir_validate_intervals()
        if {"start", "end"}.intersection(vals):
            self.attendance_id._coir_touch_revision()
        return result

    def unlink(self):
        if not (self.env.su and self.env.context.get("module_uninstall")):
            raise UserError(_("Las salidas de trabajo conservan su historial. Utiliza una corrección con motivo."))
        return super().unlink()

    @api.constrains("start", "end", "attendance_id")
    def _check_intervals(self):
        self.attendance_id._coir_validate_intervals()

    def action_correct(self):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede corregir salidas."))
        self.check_access("read")
        return {
            "type": "ir.actions.act_window", "name": _("Corregir salida de trabajo"),
            "res_model": "coir.work.correction", "view_mode": "form", "target": "new",
            "context": {"default_outing_id": self.id, "default_start": self.start, "default_end": self.end},
        }

    def _coir_correct(self, start, end, reason):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede corregir salidas."))
        self.check_access("write")
        self.attendance_id.check_access("write")
        reason = (reason or "").strip()
        if not reason or not start:
            raise ValidationError(_("Indica la salida y el motivo de la corrección."))
        old_start, old_end = self.start, self.end
        actor = self.env.user.display_name
        self.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({"start": start, "end": end or False, "review_note": reason})
        attendance = self.attendance_id
        attendance.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({"coir_review_note": reason})
        def stamp(value):
            return fields.Datetime.to_string(value) if value else self.env._("Sin registro")
        attendance.message_post(body=Markup(
            "<p><strong>%s</strong></p><p>%s: %s</p><p>%s: %s → %s (UTC)</p>"
            "<p>%s: %s → %s (UTC)</p><p>%s: %s</p>"
        ) % tuple(escape(item) for item in (
            _("Revisión de salida temporal COIRTECH"), _("Revisó"), actor,
            _("Salida de trabajo"), stamp(old_start), stamp(start),
            _("Regreso al trabajo"), stamp(old_end), stamp(end), _("Motivo"), reason,
        )))
        return True
