from datetime import datetime

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


# This identity-only marker cannot be supplied through an RPC JSON context.
# Only the validated private kiosk service and correction wizard use it.
_COIR_WRITE_TOKEN = object()


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    coir_managed = fields.Boolean(
        string="Comida pagada COIRTECH", default=False, copy=False,
        readonly=True, index=True,
        help="Política guardada al iniciar esta jornada en el quiosco COIRTECH. "
             "No se aplica retroactivamente a asistencias anteriores.",
    )
    coir_section_id = fields.Many2one(
        "coir.meal.section", string="Sección", readonly=True,
        copy=False, ondelete="restrict", index=True,
    )
    coir_section_name = fields.Char(
        string="Sección al registrar", readonly=True, copy=False,
    )
    coir_meal_start = fields.Datetime(
        string="Salida a comer", readonly=True, copy=False, tracking=True,
    )
    coir_meal_end = fields.Datetime(
        string="Regreso de comida", readonly=True, copy=False, tracking=True,
    )
    coir_meal_status = fields.Selection(
        [
            ("none", "Sin comida registrada"),
            ("open", "En comida"),
            ("returned", "Regreso registrado"),
            ("missing", "Salida sin regreso registrado"),
        ],
        string="Estado de comida", compute="_compute_coir_meal_status",
        store=True, index=True,
    )
    coir_meal_hours = fields.Float(
        string="Duración de comida", compute="_compute_coir_meal_hours",
        store=True, readonly=True,
        help="Duración conocida únicamente cuando existen salida y regreso. "
             "Una comida sin regreso registrado no tiene duración confirmada.",
    )
    coir_review_note = fields.Text(
        string="Última revisión de RH", readonly=True, copy=False, tracking=True,
    )
    coir_company_id = fields.Many2one(
        "res.company", related="employee_id.company_id", string="Empresa",
        store=True, readonly=True, index=True,
    )
    coir_work_outing_ids = fields.One2many(
        "coir.work.outing", "attendance_id", string="Salidas de trabajo", readonly=True, copy=False,
    )
    coir_work_hours = fields.Float(
        string="Tiempo confirmado de salidas", compute="_compute_coir_work", store=True,
    )
    coir_open_work_outing_id = fields.Many2one(
        "coir.work.outing", string="Salida temporal abierta", compute="_compute_coir_work", store=True,
    )
    coir_work_status = fields.Selection([
        ("none", "Sin salidas de trabajo"), ("open", "Fuera por trabajo"),
        ("returned", "Regresos registrados"), ("missing", "Salida sin regreso registrado"),
    ], string="Estado de salidas", compute="_compute_coir_work", store=True, index=True)
    coir_revision = fields.Integer(string="Revisión de movimientos", default=0, readonly=True, copy=False)

    @api.depends("coir_work_outing_ids.start", "coir_work_outing_ids.end", "check_out")
    def _compute_coir_work(self):
        for attendance in self:
            outings = attendance.coir_work_outing_ids
            opened = outings.filtered(lambda rec: not rec.end).sorted(key=lambda rec: (rec.start, rec.id))
            attendance.coir_work_hours = sum((rec.end - rec.start).total_seconds() / 3600 for rec in outings if rec.end)
            attendance.coir_open_work_outing_id = opened[:1]
            attendance.coir_work_status = (
                ("missing" if attendance.check_out else "open") if opened
                else ("returned" if outings else "none")
            )

    @api.depends("coir_managed", "coir_meal_start", "coir_meal_end", "check_out")
    def _compute_coir_meal_status(self):
        for attendance in self:
            if not attendance.coir_meal_start:
                attendance.coir_meal_status = "none"
            elif attendance.coir_meal_end:
                attendance.coir_meal_status = "returned"
            else:
                attendance.coir_meal_status = "missing" if attendance.check_out else "open"

    @api.depends("coir_meal_start", "coir_meal_end")
    def _compute_coir_meal_hours(self):
        for attendance in self:
            attendance.coir_meal_hours = (
                (attendance.coir_meal_end - attendance.coir_meal_start).total_seconds() / 3600
                if attendance.coir_meal_start and attendance.coir_meal_end else 0.0
            )

    @api.depends("check_in", "check_out", "coir_managed")
    def _compute_worked_hours(self):
        return super()._compute_worked_hours()

    def _get_worked_hours_in_range(self, start_dt, end_dt):
        self.ensure_one()
        if not self.coir_managed:
            return super()._get_worked_hours_in_range(start_dt, end_dt)
        start = max(self.check_in, start_dt)
        stop = min(self.check_out, end_dt) if self.check_out else end_dt
        return max(0.0, (stop - start).total_seconds() / 3600)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        protected = {
            "coir_managed", "coir_section_id", "coir_section_name",
            "coir_meal_start", "coir_meal_end", "coir_review_note", "coir_company_id",
            "coir_work_outing_ids", "coir_revision", "coir_work_hours", "coir_work_status",
            "coir_open_work_outing_id", "coir_meal_hours", "coir_meal_status",
        }
        # Apply the same defaults the ORM will use before checking a new entry.
        # This also prevents default_coir_* context values bypassing protection.
        defaults = self.default_get(list(protected | {"employee_id", "check_in"}))
        vals_list = [{**defaults, **original} for original in vals_list]
        employees = self.env["hr.employee"].sudo().browse(sorted({
            vals.get("employee_id") for vals in vals_list if vals.get("employee_id")
        })).exists()
        employees._coir_lock_employee()
        created = self.browse()
        trusted = self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN
        for original in vals_list:
            vals = dict(original)
            if any(vals.get(key) for key in protected) and not trusted:
                raise AccessError(_("Inicia la jornada desde el quiosco COIRTECH."))
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id")).exists()
            authorization = self.env["coir.reentry.authorization"]
            if employee and employee.company_id.coir_meal_control_enabled:
                stamp = fields.Datetime.to_datetime(vals.get("check_in") or fields.Datetime.now())
                closed, authorization, until = employee._coir_entry_decision(stamp)
                if closed and not authorization:
                    raise UserError(employee._coir_entry_block_message(until))
            if vals.get("coir_managed"):
                if not employee or not employee.company_id.coir_meal_control_enabled:
                    raise ValidationError(_("El control de comidas no está activo para este empleado."))
                section = employee.coir_meal_section_id
                vals["coir_section_id"] = section.id if section else False
                vals["coir_section_name"] = section.name if section else False
                vals["coir_revision"] = 1
            attendance = super().create([vals])
            if authorization:
                authorization.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN)._coir_consume(attendance.sudo())
            created |= attendance
        return created

    def write(self, vals):
        immutable = {"coir_managed", "coir_section_id", "coir_section_name", "coir_company_id"}
        if immutable.intersection(vals):
            raise AccessError(_("La política y sección de una jornada ya registrada no se pueden cambiar."))
        trusted = self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN
        if {
            "coir_meal_start", "coir_meal_end", "coir_review_note", "coir_work_outing_ids",
            "coir_revision", "coir_work_hours", "coir_work_status", "coir_open_work_outing_id",
            "coir_meal_hours", "coir_meal_status",
        }.intersection(vals) and not trusted:
            raise AccessError(_("Utiliza Revisar comida para corregir los movimientos, indicando el motivo."))
        managed = self.filtered("coir_managed")
        if managed and "employee_id" in vals:
            if any(att.employee_id.id != vals["employee_id"] for att in managed):
                raise ValidationError(_("No se puede reasignar a otro empleado una jornada COIRTECH."))
        if managed and {"check_in", "check_out"}.intersection(vals) and not trusted:
            if not self.env.su and not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
                raise AccessError(_("Solo un administrador de Asistencias puede corregir esta jornada."))
        if vals.get("check_out") and any(
            not attendance.check_out and (
                (attendance.coir_meal_start and not attendance.coir_meal_end)
                or attendance.coir_open_work_outing_id
            ) for attendance in managed
        ):
            raise UserError(_("Registra primero el regreso de comida o de la salida de trabajo antes de la salida final. Recursos Humanos puede corregir una omisión."))
        movement = {"coir_meal_start", "coir_meal_end", "check_in", "check_out"}.intersection(vals)
        if movement:
            self.employee_id.sudo()._coir_lock_employee()
            for attendance in self:
                values = dict(vals)
                if attendance.coir_managed:
                    values["coir_revision"] = attendance.coir_revision + 1
                super(HrAttendance, attendance).write(values)
            return True
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda a: a.coir_managed and (a.coir_meal_start or a.coir_work_outing_ids)):
            if not (self.env.su and self.env.context.get("module_uninstall")):
                raise UserError(_("Esta asistencia contiene movimientos de comida. Utiliza la revisión de RH para conservar su historial."))
        return super().unlink()

    @api.constrains("coir_managed", "coir_meal_start", "coir_meal_end", "check_in", "check_out", "employee_id", "coir_section_id")
    def _check_coir_meal_times(self):
        for attendance in self:
            start, end = attendance.coir_meal_start, attendance.coir_meal_end
            if (start or end) and not attendance.coir_managed:
                raise ValidationError(_("Solo las jornadas iniciadas en COIRTECH pueden tener movimientos de comida."))
            if end and not start:
                raise ValidationError(_("Registra primero la salida a comer."))
            if start and start < attendance.check_in:
                raise ValidationError(_("La comida no puede comenzar antes de la entrada."))
            if end and end < start:
                raise ValidationError(_("El regreso no puede ser anterior a la salida a comer."))
            if attendance.check_out and any(
                value and value > attendance.check_out for value in (start, end)
            ):
                raise ValidationError(_("Los movimientos de comida deben estar dentro de la jornada."))
            if attendance.coir_section_id and attendance.coir_section_id.company_id != attendance.employee_id.company_id:
                raise ValidationError(_("La sección y el empleado deben pertenecer a la misma empresa."))
        self._coir_validate_intervals()

    def _coir_validate_intervals(self):
        for attendance in self.sudo():
            intervals = []
            if attendance.coir_meal_start:
                intervals.append((attendance.coir_meal_start, attendance.coir_meal_end or datetime.max))
            outings = attendance.coir_work_outing_ids.sorted(key=lambda rec: (rec.start, rec.id))
            for outing in outings:
                if not attendance.coir_managed:
                    raise ValidationError(_("Las salidas de trabajo requieren una jornada COIRTECH."))
                if outing.start < attendance.check_in:
                    raise ValidationError(_("La salida de trabajo no puede ser anterior a la entrada."))
                if outing.end and outing.end < outing.start:
                    raise ValidationError(_("El regreso al trabajo no puede ser anterior a su salida."))
                if attendance.check_out and (outing.start > attendance.check_out or (outing.end and outing.end > attendance.check_out)):
                    raise ValidationError(_("Las salidas de trabajo deben quedar dentro de la jornada."))
                interval = (outing.start, outing.end or datetime.max)
                if any(interval[0] < end and interval[1] > start for start, end in intervals):
                    raise ValidationError(_("La comida y las salidas de trabajo no pueden superponerse."))
                intervals.append(interval)

    def _coir_touch_revision(self):
        for attendance in self:
            attendance.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({"coir_revision": attendance.coir_revision + 1})

    def action_coir_authorize_reentry(self):
        self.ensure_one()
        self.check_access("read")
        return self.employee_id.action_coir_authorize_reentry()

    def action_coir_review_meal(self):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede revisar comidas."))
        if not self.coir_managed:
            raise UserError(_("Esta asistencia no pertenece al control de comidas COIRTECH."))
        return {
            "type": "ir.actions.act_window", "name": _("Revisar comida"),
            "res_model": "coir.meal.correction", "view_mode": "form", "target": "new",
            "context": {
                "default_attendance_id": self.id,
                "default_meal_start": self.coir_meal_start,
                "default_meal_end": self.coir_meal_end,
            },
        }

    def _coir_correct_meal(self, start, end, reason):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede revisar comidas."))
        self.check_access("write")
        if not self.coir_managed:
            raise UserError(_("No se pueden convertir asistencias históricas al control COIRTECH."))
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(_("Escribe el motivo de la corrección."))
        old_start, old_end = self.coir_meal_start, self.coir_meal_end
        actor = self.env.user.display_name
        self.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({
            "coir_meal_start": start or False,
            "coir_meal_end": end or False,
            "coir_review_note": reason,
        })
        def stamp(value):
            return fields.Datetime.to_string(value) if value else self.env._("Sin registro")
        self.message_post(body=Markup(
            "<p><strong>%s</strong></p><p>%s: %s</p>"
            "<p>%s: %s → %s (UTC)</p><p>%s: %s → %s (UTC)</p><p>%s: %s</p>"
        ) % tuple(escape(item) for item in (
            _("Revisión de comida COIRTECH"), _("Revisó"), actor,
            _("Salida a comer"), stamp(old_start), stamp(start),
            _("Regreso"), stamp(old_end), stamp(end), _("Motivo"), reason,
        )))
        return True
