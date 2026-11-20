from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_datetime

from .attendance import _COIR_WRITE_TOKEN


def _iso_utc(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else False


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    coir_meal_section_id = fields.Many2one(
        "coir.meal.section", string="Sección COIRTECH",
        check_company=True, ondelete="restrict",
        groups="hr_attendance.group_hr_attendance_user,hr.group_hr_user",
        help="Agrupa los reportes. No impone horarios de entrada ni de comida.",
    )

    @api.constrains("coir_meal_section_id", "company_id")
    def _check_coir_section_company(self):
        for employee in self:
            if employee.coir_meal_section_id and employee.coir_meal_section_id.company_id != employee.company_id:
                raise ValidationError(_("La sección y el empleado deben pertenecer a la misma empresa."))

    def _coir_lock_employee(self):
        """Serialize every channel on one row, including repeatable-read retries."""
        if not self:
            return
        self.env.cr.execute("SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(sorted(self.ids))])
        self.env.cr.execute("UPDATE hr_employee SET write_date = write_date WHERE id IN %s", [tuple(sorted(self.ids))])
        self.invalidate_recordset()
        self.env["hr.attendance"].invalidate_model()
        self.env["coir.work.outing"].invalidate_model()
        self.env["coir.reentry.authorization"].invalidate_model()

    def _coir_day_bounds(self, at):
        """Effective employee calendar timezone; UTC-naive database boundaries."""
        self.ensure_one()
        at = fields.Datetime.to_datetime(at)
        tz = pytz.timezone(self._get_tz() or "UTC")
        local_date = pytz.utc.localize(at).astimezone(tz).date()
        start = tz.localize(datetime.combine(local_date, time.min), is_dst=False)
        end = tz.localize(datetime.combine(local_date + timedelta(days=1), time.min), is_dst=False)
        return local_date, start.astimezone(pytz.utc).replace(tzinfo=None), end.astimezone(pytz.utc).replace(tzinfo=None)

    def _coir_entry_decision(self, at):
        """Last genuine final exit, one-use voucher, and UTC end of local day.

        New CREATE never gets an exemption based on mode or a caller context.
        Only real native absence placeholders do not count as final exits.
        """
        self.ensure_one()
        at = fields.Datetime.to_datetime(at)
        day, day_start, day_end = self._coir_day_bounds(at)
        closed = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", self.id), ("check_out", ">=", day_start),
            ("check_out", "<", day_end),
        ], order="check_out desc, id desc")
        closed = closed.filtered(lambda rec: not (
            not rec.coir_managed and rec.in_mode == "technical" and rec.out_mode == "technical"
            and 0 <= (rec.check_out - rec.check_in).total_seconds() <= 1
        ))[:1]
        authorization = self.env["coir.reentry.authorization"].sudo().search([
            ("employee_id", "=", self.id), ("company_id", "=", self.company_id.id),
            ("valid_date", "=", day), ("state", "=", "pending"),
        ], order="authorized_at, id", limit=1) if closed else self.env["coir.reentry.authorization"]
        return closed, authorization, day_end

    def _coir_entry_block_message(self, until):
        self.ensure_one()
        return _(
            "Ya registraste la salida final de este día. La siguiente entrada se habilita el %(date)s. "
            "Para una jornada adicional, solicita autorización a Recursos Humanos.",
            date=format_datetime(self.env, until, tz=self._get_tz(), dt_format="dd/MM/yyyy HH:mm"),
        )

    def _coir_open_attendance(self):
        self.ensure_one()
        return self.env["hr.attendance"].search([
            ("employee_id", "=", self.id), ("check_out", "=", False),
        ], order="check_in desc, id desc", limit=1)

    def _coir_meal_state(self):
        self.ensure_one()
        attendance = self._coir_open_attendance()
        if not attendance:
            closed, authorization, until = self._coir_entry_decision(fields.Datetime.now())
            blocked = bool(closed and not authorization)
            return {
                "attendance_id": 0, "state": "closed" if blocked else "absent",
                "allowed_actions": [] if blocked else ["check_in"], "meal_start": False,
                "meal_end": False, "section_name": self.coir_meal_section_id.name or "",
                "managed": False, "check_in": False, "check_out": _iso_utc(closed.check_out),
                "revision": 0, "work_start": False, "work_outing_id": 0,
                "blocked_until": _iso_utc(until) if blocked else False,
                "blocking_message": self._coir_entry_block_message(until) if blocked else "",
            }
        outing = attendance.coir_open_work_outing_id
        if not attendance.coir_managed:
            state, allowed = "working", ["check_out"]
        elif outing:
            state, allowed = "away", ["work_return"]
        elif attendance.coir_meal_start and not attendance.coir_meal_end:
            state, allowed = "eating", ["meal_return"]
        elif attendance.coir_meal_end:
            state, allowed = "returned", ["work_exit", "check_out"]
        else:
            state, allowed = "working", ["meal_start", "work_exit", "check_out"]
        return {
            "attendance_id": attendance.id, "state": state,
            "allowed_actions": allowed, "meal_start": _iso_utc(attendance.coir_meal_start),
            "meal_end": _iso_utc(attendance.coir_meal_end),
            "section_name": attendance.coir_section_name or "",
            "managed": bool(attendance.coir_managed),
            "check_in": _iso_utc(attendance.check_in), "check_out": False,
            "revision": attendance.coir_revision,
            "work_start": _iso_utc(outing.start), "work_outing_id": outing.id or 0,
            "blocked_until": False, "blocking_message": "",
        }

    def _coir_apply_meal_action(self, action, expected_attendance_id, expected_state,
                               confirm_without_return=False, geo_information=None,
                               expected_revision=None):
        self.ensure_one()
        self._coir_lock_employee()
        if not self.active or not self.company_id.coir_meal_control_enabled:
            raise UserError(_("El control de comidas no está activo para este empleado."))
        current = self._coir_meal_state()
        if (current["attendance_id"] != expected_attendance_id or current["state"] != expected_state
                or (expected_revision is not None and current["revision"] != expected_revision)):
            raise UserError(_("El estado del empleado cambió. Identifícate de nuevo antes de registrar otro movimiento."))
        if action not in current["allowed_actions"]:
            if action == "check_in" and current["state"] == "closed":
                raise UserError(current["blocking_message"])
            raise UserError(_("Este movimiento no corresponde al estado actual del empleado."))
        geo = {
            key: value for key, value in (geo_information or {}).items()
            if key in {"latitude", "longitude", "location", "ip_address", "browser", "mode"}
        }
        geo["mode"] = "kiosk"
        now = fields.Datetime.now()
        Attendance = self.env["hr.attendance"].sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN)
        if action == "check_in":
            attendance = Attendance.create({
                "employee_id": self.id, "check_in": now, "coir_managed": True,
                **{"in_" + key: value for key, value in geo.items()},
            })
            return self.env["hr.attendance"].browse(attendance.id)
        attendance = Attendance.browse(current["attendance_id"])
        if action == "meal_start":
            attendance.write({"coir_meal_start": now})
        elif action == "meal_return":
            attendance.write({"coir_meal_end": now})
        elif action == "work_exit":
            self.env["coir.work.outing"].sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).create({
                "attendance_id": attendance.id, "start": now,
            })
        elif action == "work_return":
            attendance.coir_open_work_outing_id.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({"end": now})
        else:
            attendance.write({
                "check_out": now, **{"out_" + key: value for key, value in geo.items()},
            })
        return self.env["hr.attendance"].browse(attendance.id)

    def action_coir_authorize_reentry(self):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede autorizar otra entrada."))
        self.check_access("read")
        return {
            "type": "ir.actions.act_window", "name": _("Autorizar entrada adicional"),
            "res_model": "coir.reentry.authorization", "view_mode": "form", "target": "new",
            "context": {"default_employee_id": self.id,
                        "default_valid_date": self._coir_day_bounds(fields.Datetime.now())[0]},
        }
