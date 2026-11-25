"""V4: approved Time Off and opt-out policy, without synthetic attendances.

The daily indicator is a projection of original records.  Its authorized hours
are descriptive and are never added to hr.attendance or payroll totals.
"""
from collections import defaultdict
from datetime import timedelta

import pytz

from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .absence import _day_bounds, _genuine_attendance, _utc_naive


_EXCLUSION_WRITE_TOKEN = object()
_CATEGORY_LABELS = {
    "vacation": "VACACIONES",
    "paid_absence": "FALTA CON SUELDO",
    "unpaid_absence": "FALTA SIN SUELDO",
    "disability": "INCAPACIDAD",
}
_REPORT_STATES = ("absent", "approved", "partial", "review")


def _merged(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _intersect(left, right):
    return _merged((max(a, c), min(b, d)) for a, b in left for c, d in right
                   if max(a, c) < min(b, d))


def _subtract(intervals, removed):
    result = _merged(intervals)
    for start, end in _merged(removed):
        remaining = []
        for left, right in result:
            if end <= left or start >= right:
                remaining.append((left, right))
            else:
                if left < start:
                    remaining.append((left, start))
                if right > end:
                    remaining.append((end, right))
        result = remaining
    return result


class CoirAttendanceExclusion(models.Model):
    _name = "coir.attendance.exclusion"
    _description = "Historial de exclusión del reporte COIRTECH"
    _order = "start_datetime desc, id desc"
    _check_company_auto = True

    employee_id = fields.Many2one("hr.employee", required=True, readonly=True,
                                  index=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True,
                                 index=True, ondelete="restrict")
    start_datetime = fields.Datetime(string="Excluido desde", required=True, readonly=True, index=True)
    end_datetime = fields.Datetime(string="Reincorporado el", readonly=True, index=True)
    excluded_by_id = fields.Many2one("res.users", string="Excluido por", readonly=True, ondelete="set null")
    included_by_id = fields.Many2one("res.users", string="Reincorporado por", readonly=True, ondelete="set null")

    _interval_valid = models.Constraint(
        "CHECK(end_datetime IS NULL OR end_datetime >= start_datetime)",
        "La reincorporación debe ser posterior al inicio de la exclusión.",
    )

    def _service(self):
        return self.sudo().with_context(coir_exclusion_write_token=_EXCLUSION_WRITE_TOKEN)

    def _check_service_write(self):
        if not (self.env.su and self.env.context.get("coir_exclusion_write_token") is _EXCLUSION_WRITE_TOKEN):
            raise AccessError(_("El historial se actualiza desde la casilla del empleado."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_service_write()
        return super().create(vals_list)

    def write(self, vals):
        self._check_service_write()
        return super().write(vals)

    def unlink(self):
        if not (self.env.su and self.env.context.get("module_uninstall")):
            raise UserError(_("El historial de exclusión se conserva para las revisiones de Recursos Humanos."))
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("El historial de exclusión no se puede duplicar."))


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    coir_attendance_report_excluded = fields.Boolean(
        string="Excluir del Reporte de asistencia", default=False, copy=False,
        help="Oculta todos los periodos de este empleado en el reporte COIRTECH y sus exportaciones. "
             "Detiene las faltas automáticas. Conserva sus marcajes, permisos y acceso al quiosco.",
    )
    coir_attendance_exclusion_ids = fields.One2many(
        "coir.attendance.exclusion", "employee_id", string="Historial de exclusión", readonly=True,
        groups="hr.group_hr_user,hr_attendance.group_hr_attendance_manager",
    )

    def _coir_check_exclusion_permission(self):
        if not (self.env.su or self.env.user.has_group("hr.group_hr_user")
                or self.env.user.has_group("hr_attendance.group_hr_attendance_manager")):
            raise AccessError(_("Sólo Recursos Humanos o un administrador de Asistencias puede cambiar la exclusión."))

    def _coir_record_exclusion_change(self, excluded, at, actor_id):
        History = self.env["coir.attendance.exclusion"]._service()
        for employee in self.sudo():
            open_periods = History.search([("employee_id", "=", employee.id), ("end_datetime", "=", False)])
            if excluded and not open_periods:
                History.create({
                    "employee_id": employee.id, "company_id": employee.company_id.id,
                    "start_datetime": at, "excluded_by_id": actor_id,
                })
            elif not excluded:
                open_periods.write({"end_datetime": at, "included_by_id": actor_id})

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get("coir_attendance_report_excluded") for values in vals_list):
            self._coir_check_exclusion_permission()
        employees = super().create(vals_list)
        excluded = employees.filtered("coir_attendance_report_excluded")
        if excluded:
            excluded._coir_record_exclusion_change(True, fields.Datetime.now(), self.env.uid)
        return employees

    def write(self, vals):
        changes_exclusion = "coir_attendance_report_excluded" in vals
        affects_today = changes_exclusion or "active" in vals
        changed = self.browse()
        if changes_exclusion:
            self._coir_check_exclusion_permission()
            self.check_access("write")
            self.sudo()._coir_lock_employee()
            changed = self.filtered(lambda employee: employee.coir_attendance_report_excluded != bool(vals["coir_attendance_report_excluded"]))
        now = fields.Datetime.now()
        result = super().write(vals)
        if changed:
            changed._coir_record_exclusion_change(bool(vals["coir_attendance_report_excluded"]), now, self.env.uid)
            self.env["coir.attendance.day"].invalidate_model()
        if affects_today:
            Absence = self.env["coir.attendance.absence"]
            for employee in self.sudo():
                timezone = employee.company_id.coir_absence_tz or "America/Mexico_City"
                day = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone)).date()
                # Re-inclusion resumes today's policy, never historical catch-up.
                Absence._reconcile_employee(employee, day, now=now,
                                             allow_create=bool(changed and not employee.coir_attendance_report_excluded))
        return result

    def _coir_excluded_on(self, day, timezone, now=None):
        """Any excluded portion protects a historical day; today uses the live switch."""
        self.ensure_one()
        employee = self.sudo()
        day = fields.Date.to_date(day)
        now = _utc_naive(now or fields.Datetime.now())
        today = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone)).date()
        if day >= today:
            return employee.coir_attendance_report_excluded
        start, stop = _day_bounds(day, timezone)
        return bool(self.env["coir.attendance.exclusion"].sudo().search_count([
            ("employee_id", "=", self.id), ("start_datetime", "<", _utc_naive(stop)),
            "|", ("end_datetime", "=", False), ("end_datetime", ">", _utc_naive(start)),
        ], limit=1))


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    # Attendance officers without private HR access search this public SQL
    # projection. Expose only the operational switch, never its audit history.
    coir_attendance_report_excluded = fields.Boolean(
        string="Excluir del Reporte de asistencia", readonly=True,
    )


class ResCompany(models.Model):
    _inherit = "res.company"

    coir_absence_tracking_started_at = fields.Datetime(
        string="Inicio del seguimiento COIRTECH", readonly=True, copy=False,
        help="Límite conservador para nuevas incidencias históricas. Las faltas automáticas nunca se rellenan hacia atrás.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("coir_meal_control_enabled") and vals.get("coir_absence_enabled", True):
                vals.setdefault("coir_absence_tracking_started_at", fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        newly_enabled = self.filtered(lambda company: not company.coir_meal_control_enabled) if vals.get("coir_meal_control_enabled") else self.browse()
        result = super().write(vals)
        if {"coir_meal_control_enabled", "coir_absence_enabled"}.intersection(vals):
            missing = self.filtered(lambda company: company.coir_meal_control_enabled
                                    and company.coir_absence_enabled and not company.coir_absence_tracking_started_at)
            if missing:
                super(ResCompany, missing).write({"coir_absence_tracking_started_at": fields.Datetime.now()})
        if newly_enabled:
            # Initial module installation normally leaves the COIRTECH switch
            # off. Enabling it later must expose existing approved history in
            # the list immediately, without requiring an export or waiting for
            # a current-day cron to visit those historical dates.
            self.env["coir.attendance.absence"].sudo()._sync_approved_leaves(company_ids=newly_enabled.ids)
        return result


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    coir_attendance_category = fields.Selection(
        [(key, label) for key, label in _CATEGORY_LABELS.items()],
        string="Categoría en el reporte COIRTECH",
        help="Correspondencia explícita para el reporte. No modifica pagos, descuentos ni configuración de nómina. "
             "Sin correspondencia, una ausencia aprobada sigue siendo válida y se muestra como tipo por configurar.",
    )

    def write(self, vals):
        result = super().write(vals)
        if {"coir_attendance_category", "request_unit"}.intersection(vals):
            leaves = self.env["hr.leave"].sudo().search([
                ("holiday_status_id", "in", self.ids), ("state", "=", "validate"),
                ("employee_id.company_id.coir_meal_control_enabled", "=", True),
            ])
            self.env["coir.attendance.absence"]._sync_leave_spans(leaves._coir_attendance_spans())
        return result


class CoirAttendanceAbsence(models.Model):
    _inherit = "coir.attendance.absence"

    state = fields.Selection(selection_add=[
        ("approved", "Ausencia aprobada"), ("partial", "Ausencia parcial aprobada"),
        ("review", "Revisión de Recursos Humanos"),
    ], ondelete={"approved": "set default", "partial": "set default", "review": "set default"})
    leave_label = fields.Char(string="Ausencia aprobada", readonly=True)
    leave_hours = fields.Float(string="Horas autorizadas", readonly=True, digits=(16, 2))
    leave_periods = fields.Char(string="Periodo autorizado", readonly=True)
    review_reason = fields.Char(string="Incidencia de Recursos Humanos", readonly=True)
    review_due_datetime = fields.Datetime(string="Cierre del tramo pendiente", readonly=True, index=True)
    review_check_pending = fields.Boolean(string="Revisión de cierre pendiente", readonly=True, index=True)
    resolution_reason = fields.Char(string="Motivo de resolución", readonly=True)
    report_label = fields.Char(string="Estado del reporte", compute="_compute_report_label", store=True)
    was_automatic_absence = fields.Boolean(
        string="Tuvo una falta automática", default=True, readonly=True,
        help="Permite revisar una falta original sin inventar faltas en fechas históricas.",
    )
    had_approved_leave = fields.Boolean(readonly=True, default=False)
    leave_ids = fields.Many2many(
        "hr.leave", "coir_attendance_absence_leave_rel", "absence_id", "leave_id",
        string="Ausencias de origen", readonly=True,
        groups="hr_holidays.group_hr_holidays_user",
    )

    def _coir_visible_in_report(self):
        """Only expose today/past indicators in COIRTECH reports.

        Approved future Time Off remains untouched in hr.leave and in this
        source model; it becomes visible automatically on its local day.  This
        is also applied at PDF/Excel construction time to guard saved wizard
        selections or calls which bypass the read-only SQL report view.
        """
        if not self:
            return self
        now = pytz.UTC.localize(_utc_naive(fields.Datetime.now()))
        local_today = {}
        visible_ids = []
        for notice in self:
            timezone = notice.timezone or notice.company_id.coir_absence_tz or "America/Mexico_City"
            if timezone not in local_today:
                local_today[timezone] = now.astimezone(pytz.timezone(timezone)).date()
            if notice.date <= local_today[timezone]:
                visible_ids.append(notice.id)
        return self.browse(visible_ids)

    @api.depends("state", "leave_label")
    def _compute_report_label(self):
        for record in self:
            if record.state == "absent":
                record.report_label = "FALTA"
            elif record.state == "approved":
                record.report_label = record.leave_label or "AUSENCIA APROBADA"
            elif record.state == "partial":
                record.report_label = "%s — PARCIAL" % (record.leave_label or "AUSENCIA APROBADA")
            elif record.state == "review":
                record.report_label = "%s — REVISAR RH" % record.leave_label if record.leave_label else "REVISAR RH"
            elif record.state == "resolved":
                record.report_label = "Entrada registrada"
            else:
                record.report_label = "Sin incidencia vigente"

    @api.depends("employee_id.name", "date", "report_label")
    def _compute_name(self):
        for record in self:
            record.name = "%s · %s · %s" % (record.report_label or "COIRTECH", record.employee_id.name or "", record.date or "")

    @api.model
    def _planned_intervals(self, employee, day, timezone):
        """Required work before Time Off, but after real holidays/rest periods.

        Excluding hr.leave-backed calendar leaves avoids interpreting a fully
        authorized workday as a nonworking day and losing its category.
        """
        employee = employee.sudo()
        versions = employee.version_ids.filtered("contract_date_start")
        if versions and not any(version._is_in_contract(day) for version in versions):
            return [], True
        calendar = employee._get_calendars(day).get(employee.id)
        if not calendar or calendar.flexible_hours or calendar.duration_based:
            return [], False
        start, stop = _day_bounds(day, timezone)
        work = calendar.sudo()._work_intervals_batch(
            start, stop, resources=employee.resource_id,
            domain=[("time_type", "=", "leave"), ("holiday_id", "=", False)],
            tz=pytz.timezone(calendar.tz or employee.tz or timezone), compute_leaves=True,
        )
        return _merged([(_utc_naive(begin), _utc_naive(end))
                        for begin, end, _meta in work[employee.resource_id.id] if end > begin]), True

    @api.model
    def _day_attendances(self, employee, day, timezone, now):
        start, stop = _day_bounds(day, timezone)
        previous_start, _unused = _day_bounds(day - timedelta(days=1), timezone)
        records = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", employee.id), ("check_in", "<", _utc_naive(stop)),
            ("check_in", "<=", now), "|", "|", ("check_in", ">=", _utc_naive(start)),
            ("check_out", ">", _utc_naive(start)), "&", ("check_out", "=", False),
            ("check_in", ">=", _utc_naive(previous_start)),
        ], order="check_in, id")
        return records.filtered(_genuine_attendance)

    @api.model
    def _approved_for_day(self, employee, day, timezone):
        start, stop = _day_bounds(day, timezone)
        return self.env["hr.leave"].sudo().search([
            ("employee_id", "=", employee.id), ("state", "=", "validate"),
            ("date_from", "<", _utc_naive(stop)), ("date_to", ">", _utc_naive(start)),
        ], order="date_from, date_to, id")

    @api.model
    def _review_period_is_tracked(self, employee, company, day, timezone, now, record=None):
        today = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone)).date()
        if day > today or employee._coir_excluded_on(day, timezone, now=now):
            return False
        if day == today and (not employee.active or not company.coir_meal_control_enabled):
            return False
        if record and record.was_automatic_absence:
            return True
        started = company.coir_absence_tracking_started_at
        return bool(started and day >= pytz.UTC.localize(started).astimezone(pytz.timezone(timezone)).date())

    @api.model
    def _leave_day_values(self, employee, leaves, work, known_schedule, day, timezone, now, attendances, can_review):
        start, stop = _day_bounds(day, timezone)
        bounds = [(_utc_naive(start), _utc_naive(stop))]
        labels, periods, covered_by_leave = [], [], []
        zone = pytz.timezone(timezone)
        applicable = self.env["hr.leave"].sudo()
        for leave in leaves:
            coverage = _intersect([(leave.date_from, leave.date_to)], work if known_schedule else bounds)
            if not coverage:
                continue
            applicable |= leave
            label = _CATEGORY_LABELS.get(leave.holiday_status_id.coir_attendance_category,
                                         "AUSENCIA APROBADA — TIPO POR CONFIGURAR")
            if label not in labels:
                labels.append(label)
            for begin, end in coverage:
                local_begin = pytz.UTC.localize(begin).astimezone(zone)
                local_end = pytz.UTC.localize(end).astimezone(zone)
                periods.append("%s–%s (%s)" % (local_begin.strftime("%H:%M"), local_end.strftime("%H:%M"), label))
            covered_by_leave.append((leave.id, coverage))
        if not applicable:
            return None
        covered = _merged([interval for _leave_id, values in covered_by_leave for interval in values])
        remainder = _subtract(work, covered) if known_schedule else []
        reasons = []
        for index, (_leave_id, values) in enumerate(covered_by_leave):
            if any(_intersect(values, other) for _other_id, other in covered_by_leave[index + 1:]):
                reasons.append("Ausencias aprobadas superpuestas; revisar las solicitudes de origen.")
                break
        # Compare actual intervals, not just dates. A return exactly at the end
        # of an authorized interval is not an overlap.
        real_intervals = [(attendance.check_in, min(attendance.check_out or now, now))
                          for attendance in attendances]
        if (_intersect(real_intervals, covered)
                or any(begin <= attendance.check_in < end
                       for attendance in attendances for begin, end in covered)):
            reasons.append("Asistencia registrada durante una ausencia aprobada.")
        if not known_schedule:
            reasons.append("Horario de trabajo no definido o flexible; revisar la cobertura autorizada.")
        elif remainder and not attendances and now >= max(end for begin, end in remainder) and can_review:
            reasons.append("Ausencia parcial aprobada sin registro de asistencia en el resto de la jornada.")
        state = "review" if reasons else ("partial" if remainder else "approved")
        review_due = max(end for begin, end in remainder) if known_schedule and remainder else False
        # During an excluded interval, keep approved source information for
        # future visibility, but never create a no-show incidence.
        return {
            "state": state, "leave_label": " + ".join(labels),
            "leave_hours": sum((end - begin).total_seconds() / 3600 for begin, end in covered) if known_schedule else 0.0,
            "leave_periods": "; ".join(periods), "review_reason": " ".join(reasons) or False,
            "review_due_datetime": review_due,
            "review_check_pending": bool(review_due and not attendances and now < review_due),
            "leave_ids": [Command.set(applicable.ids)], "had_approved_leave": True,
            "attendance_id": attendances[:1].id or False,
            "start_datetime": min(begin for begin, end in covered),
            "end_datetime": max(end for begin, end in covered),
            "resolution_reason": "Cubierta por ausencia aprobada de Odoo.",
        }

    @api.model
    def _persist_day_outcome(self, employee, company, day, timezone, now, record, values):
        service = self._service().with_company(company)
        if record:
            changed = {}
            for key, value in values.items():
                if key == "leave_ids":
                    ids = value[0][2] if value and value[0][0] == Command.SET else []
                    if set(record.sudo().leave_ids.ids) != set(ids):
                        changed[key] = value
                elif key == "attendance_id":
                    if record.attendance_id.id != value:
                        changed[key] = value
                elif record[key] != value:
                    changed[key] = value
            if "state" in changed:
                changed["resolved_at"] = now if values["state"] != "absent" else False
            if changed:
                record._service().write(changed)
        else:
            section = employee.coir_meal_section_id
            record = service.create({
                "employee_id": employee.id, "company_id": company.id, "date": day,
                "timezone": timezone, "department_id": employee.department_id.id,
                "section_id": section.id, "section_name": section.name or False,
                "generated_at": now, "was_automatic_absence": values["state"] == "absent",
                "resolved_at": now if values["state"] != "absent" else False, **values,
            })
        employee.invalidate_recordset(["coir_absent_today", "coir_absence_label"])
        return record

    @api.model
    def _sync_employee_day(self, employee, day, now=None, allow_new_absence=False):
        """One authoritative reconciliation path for cron, source edits and imports."""
        now = _utc_naive(now or fields.Datetime.now())
        day = fields.Date.to_date(day)
        employee = employee.sudo()
        company = employee.company_id.sudo()
        service = self._service().with_company(company)
        employee._coir_lock_employee()
        service.invalidate_model()
        record = service.search([("employee_id", "=", employee.id), ("company_id", "=", company.id), ("date", "=", day)], limit=1)
        timezone = record.timezone or company.coir_absence_tz or "America/Mexico_City"
        local_now = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone))
        today = local_now.date()
        work, known_schedule = service._planned_intervals(employee, day, timezone)
        attendances = service._day_attendances(employee, day, timezone, now)
        leaves = service._approved_for_day(employee, day, timezone)
        if not known_schedule and not leaves:
            # Keep the pre-V4 fixed-09:00 policy for flexible/duration-based
            # schedules when native Odoo supplies effective work intervals.
            # With approved Time Off, an approximate schedule must not pretend
            # to establish exact partial-day coverage.
            work = service._work_intervals_by_employee(employee, day, timezone).get(employee.id, [])
            known_schedule = bool(work)
        excluded = employee._coir_excluded_on(day, timezone, now=now)
        tracked = service._review_period_is_tracked(employee, company, day, timezone, now, record)
        values = service._leave_day_values(employee, leaves, work, known_schedule, day, timezone, now, attendances, tracked)
        if values:
            # Existing approved sources may be shown in historical reports even
            # if they predate installing COIRTECH. No automatic FALTA is created.
            if not company.coir_meal_control_enabled and not record:
                return record
            return service._persist_day_outcome(employee, company, day, timezone, now, record, values)

        common = {"leave_label": False, "leave_hours": 0.0, "leave_periods": False,
                  "leave_ids": [Command.clear()], "review_reason": False,
                  "review_due_datetime": False, "review_check_pending": False,
                  "attendance_id": attendances[:1].id or False}
        if record and attendances:
            return service._persist_day_outcome(employee, company, day, timezone, now, record,
                {**common, "state": "resolved", "resolution_reason": "Entrada real registrada."})
        if excluded or (day >= today and not employee.active):
            if record:
                reason = "Excluido del control COIRTECH." if excluded else "Empleado archivado."
                return service._persist_day_outcome(employee, company, day, timezone, now, record,
                    {**common, "state": "cancelled", "resolution_reason": reason})
            return record
        if not known_schedule or not work:
            if record:
                return service._persist_day_outcome(employee, company, day, timezone, now, record,
                    {**common, "state": "cancelled", "resolution_reason": "Sin jornada exigible definida."})
            return record

        eligible_today = (day == today and day.weekday() < 5 and local_now.hour >= 9
                          and company.coir_meal_control_enabled and company.coir_absence_enabled and employee.active)
        original_historical = bool(day < today and record and record.was_automatic_absence and day.weekday() < 5)
        if not attendances and ((eligible_today and (allow_new_absence or (record and record.was_automatic_absence)))
                                or original_historical):
            return service._persist_day_outcome(employee, company, day, timezone, now, record, {
                **common, "state": "absent", "was_automatic_absence": True,
                "resolution_reason": False, "start_datetime": min(begin for begin, end in work),
                "end_datetime": max(end for begin, end in work),
            })
        if record and record.had_approved_leave and not attendances and day < today and tracked:
            return service._persist_day_outcome(employee, company, day, timezone, now, record, {
                **common, "state": "review",
                "review_reason": "Ausencia aprobada cancelada o modificada sin registro de asistencia; revisión de Recursos Humanos.",
                "resolution_reason": "Revisión histórica sin crear una falta automática.",
            })
        if record:
            return service._persist_day_outcome(employee, company, day, timezone, now, record,
                {**common, "state": "cancelled", "resolution_reason": "No corresponde una falta automática vigente."})
        return record

    @api.model
    def _generate_for_day(self, company, day, now=None):
        company.ensure_one()
        company = company.sudo()
        day = fields.Date.to_date(day)
        now = _utc_naive(now or fields.Datetime.now())
        timezone = company.coir_absence_tz or "America/Mexico_City"
        local_now = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone))
        if (not company.coir_meal_control_enabled or not company.coir_absence_enabled
                or day != local_now.date() or day.weekday() >= 5 or local_now.hour < 9):
            return self.browse()
        employees = self.env["hr.employee"].sudo().with_context(active_test=False).search([
            ("company_id", "=", company.id), ("active", "=", True),
        ], order="id")
        existing = self.sudo().search([("company_id", "=", company.id), ("date", "=", day)])
        employees |= existing.employee_id
        employees._coir_lock_employee()
        result = self.browse()
        for employee in employees.sorted("id"):
            record = self._sync_employee_day(employee, day, now=now, allow_new_absence=True)
            if record.state == "absent":
                result |= record.with_env(self.env)
        return result

    @api.model
    def _reconcile_employee(self, employee, day, now=None, allow_create=False):
        return self._sync_employee_day(employee, day, now=now, allow_new_absence=allow_create).with_env(self.env)

    @api.model
    def _sync_leave_spans(self, spans):
        """Private source-hook service; spans are original employee/date intervals."""
        pairs = set()
        Employee = self.env["hr.employee"].sudo().with_context(active_test=False)
        now = fields.Datetime.now()
        for employee_id, start, stop in spans:
            if not (employee_id and start and stop and stop > start):
                continue
            employee = Employee.browse(employee_id).exists()
            if not employee or not employee.company_id.coir_meal_control_enabled:
                continue
            timezone = employee.company_id.coir_absence_tz or "America/Mexico_City"
            zone = pytz.timezone(timezone)
            first = pytz.UTC.localize(_utc_naive(start)).astimezone(zone).date()
            last = pytz.UTC.localize(_utc_naive(stop) - timedelta(microseconds=1)).astimezone(zone).date()
            current = first
            while current <= last:
                pairs.add((employee.id, current))
                current += timedelta(days=1)
        result = self.sudo().browse()
        for employee_id, day in sorted(pairs):
            # Approvals/cancellations today may trigger normal automatic policy;
            # the service itself prohibits creating historical FALTA records.
            result |= self._sync_employee_day(Employee.browse(employee_id), day, now=now, allow_new_absence=True)
        return result.with_env(self.env)

    @api.model
    def _sync_approved_leaves(self, date_from=None, date_to=None, company_ids=None):
        """Populate approved source information, including before installing V4.

        Callers outside sudo can only request their currently authorized
        companies. Sudo reads are limited to those employees; ordinary record
        rules still protect the resulting attendance report records.
        """
        allowed = set(self.env.companies.ids)
        requested = set(company_ids or allowed)
        if not self.env.su and not requested.issubset(allowed):
            raise AccessError(_("No puedes sincronizar ausencias de una empresa no autorizada."))
        company_domain = [("coir_meal_control_enabled", "=", True)]
        if company_ids is not None or not self.env.su:
            company_domain.append(("id", "in", list(requested)))
        companies = self.env["res.company"].sudo().search(company_domain)
        result = self.sudo().browse()
        now = fields.Datetime.now()
        for company in companies:
            timezone = company.coir_absence_tz or "America/Mexico_City"
            domain = [("employee_id.company_id", "=", company.id), ("state", "=", "validate")]
            lower = upper = None
            if date_from:
                lower = fields.Date.to_date(date_from)
                begin, _end = _day_bounds(lower, timezone)
                domain.append(("date_to", ">", _utc_naive(begin)))
            if date_to:
                upper = fields.Date.to_date(date_to)
                _begin, end = _day_bounds(upper, timezone)
                domain.append(("date_from", "<", _utc_naive(end)))
            leaves = self.env["hr.leave"].sudo().search(domain)
            spans = []
            for leave in leaves:
                start, stop = leave.date_from, leave.date_to
                if lower:
                    start = max(start, _utc_naive(_day_bounds(lower, timezone)[0]))
                if upper:
                    stop = min(stop, _utc_naive(_day_bounds(upper, timezone)[1]))
                spans.append((leave.employee_id.id, start, stop))
            result |= self._sync_leave_spans(spans).sudo()
            # Removed permissions must also disappear from already materialized
            # rows, even after an offline import or an interrupted old cron.
            stale_domain = [("company_id", "=", company.id), ("had_approved_leave", "=", True)]
            if lower:
                stale_domain.append(("date", ">=", lower))
            if upper:
                stale_domain.append(("date", "<=", upper))
            for record in self.sudo().search(stale_domain):
                if record not in result:
                    result |= self._sync_employee_day(record.employee_id, record.date, now=now, allow_new_absence=True)
        return result.with_env(self.env)

    @api.model
    def _initialize_v4_tracking(self):
        """Run on install/update before the initial approved-source projection."""
        companies = self.env["res.company"].sudo().search([
            ("coir_meal_control_enabled", "=", True), ("coir_absence_enabled", "=", True),
            ("coir_absence_tracking_started_at", "=", False),
        ])
        now = fields.Datetime.now()
        for company in companies:
            original = self.sudo().search([("company_id", "=", company.id), ("was_automatic_absence", "=", True)], order="date, id", limit=1)
            started = _utc_naive(_day_bounds(original.date, original.timezone)[0]) if original else now
            company.coir_absence_tracking_started_at = started
        return True

    @api.model
    def _cron_generate_absences(self):
        now = fields.Datetime.now()
        companies = self.env["res.company"].sudo().search([("coir_meal_control_enabled", "=", True)])
        for company in companies:
            day = pytz.UTC.localize(now).astimezone(pytz.timezone(company.coir_absence_tz)).date()
            # Yesterday is needed when a partial day closes across midnight or
            # the scheduler was stopped at the end of the previous workday.
            self.sudo()._sync_approved_leaves(day - timedelta(days=1), day, [company.id])
            # Recover known pending partial days after longer outages (for
            # example Friday -> Monday). This queue contains existing notices,
            # never unobserved historical employee/day combinations. A bounded
            # batch prevents scanning or backfilling the entire history.
            pending = self.sudo().search([
                ("company_id", "=", company.id), ("review_check_pending", "=", True),
                ("review_due_datetime", "<=", now),
            ], order="employee_id, date, id", limit=500)
            for record in pending:
                self._sync_employee_day(record.employee_id, record.date, now=now, allow_new_absence=False)
            self._generate_for_day(company, day, now=now)
        return True


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _coir_attendance_spans(self):
        return [(leave.employee_id.id, leave.date_from, leave.date_to)
                for leave in self.sudo() if leave.employee_id and leave.date_from and leave.date_to]

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        self.env["coir.attendance.absence"]._sync_leave_spans(leaves._coir_attendance_spans())
        return leaves

    def write(self, vals):
        relevant = {
            "state", "employee_id", "holiday_status_id", "date_from", "date_to",
            "request_date_from", "request_date_to", "request_hour_from", "request_hour_to",
            "request_date_from_period", "request_date_to_period", "resource_calendar_id",
        }.intersection(vals)
        before = self._coir_attendance_spans() if relevant else []
        result = super().write(vals)
        if relevant:
            self.env["coir.attendance.absence"]._sync_leave_spans(before + self._coir_attendance_spans())
        return result

    def unlink(self):
        before = self._coir_attendance_spans()
        result = super().unlink()
        self.env["coir.attendance.absence"]._sync_leave_spans(before)
        return result
