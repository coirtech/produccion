"""Independent daily absence indicators; never create an hr.attendance row."""
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain


# An RPC context cannot manufacture this identity-only service capability.
_ABSENCE_WRITE_TOKEN = object()


def _utc_naive(value):
    if isinstance(value, datetime) and value.tzinfo:
        return value.astimezone(pytz.UTC).replace(tzinfo=None)
    return fields.Datetime.to_datetime(value)


def _day_bounds(day, timezone):
    day = fields.Date.to_date(day)
    tz = pytz.timezone(timezone)
    start = tz.localize(datetime.combine(day, time.min), is_dst=False)
    end = tz.localize(datetime.combine(day + timedelta(days=1), time.min), is_dst=False)
    return start, end


def _genuine_attendance(attendance):
    """Only Odoo's 0/1-second technical absence placeholders are not presence."""
    return not (
        not attendance.coir_managed
        and attendance.in_mode == "technical" and attendance.out_mode == "technical"
        and attendance.check_out
        and 0 <= (attendance.check_out - attendance.check_in).total_seconds() <= 1
    )


class CoirAttendanceAbsence(models.Model):
    _name = "coir.attendance.absence"
    _description = "Falta diaria COIRTECH"
    _order = "date desc, employee_id, id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True,
                                  readonly=True, index=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one("res.company", string="Empresa", required=True,
                                 readonly=True, index=True, ondelete="restrict")
    department_id = fields.Many2one("hr.department", string="Departamento al registrar",
                                    readonly=True, index=True, ondelete="set null")
    section_id = fields.Many2one("coir.meal.section", string="Sección al registrar",
                                 readonly=True, ondelete="set null")
    section_name = fields.Char(string="Nombre de sección al registrar", readonly=True)
    date = fields.Date(string="Fecha", required=True, readonly=True, index=True)
    timezone = fields.Char(string="Zona horaria al registrar", required=True, readonly=True)
    state = fields.Selection([
        ("absent", "FALTA"), ("resolved", "Entrada registrada"),
        ("cancelled", "Sin jornada exigible"),
    ], string="Estado", default="absent", required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string="Detectada el", required=True, readonly=True)
    resolved_at = fields.Datetime(string="Resuelta el", readonly=True)
    attendance_id = fields.Many2one("hr.attendance", string="Asistencia que resolvió la falta",
                                    readonly=True, index=True, ondelete="set null")
    start_datetime = fields.Datetime(string="Inicio del indicador", required=True, readonly=True)
    end_datetime = fields.Datetime(string="Fin del indicador", required=True, readonly=True)

    _employee_company_date_unique = models.Constraint(
        "UNIQUE(employee_id, company_id, date)",
        "Ya existe un indicador de falta para este empleado y fecha.",
    )
    _visual_interval_valid = models.Constraint(
        "CHECK(end_datetime > start_datetime)", "El intervalo visual debe ser positivo.",
    )

    @api.depends("employee_id.name", "date")
    def _compute_name(self):
        for absence in self:
            absence.name = "FALTA · %s · %s" % (absence.employee_id.name or "", absence.date or "")

    @api.model_create_multi
    def create(self, vals_list):
        self._check_service_write()
        return super().create(vals_list)

    def write(self, vals):
        self._check_service_write()
        return super().write(vals)

    def unlink(self):
        if not (self.env.su and self.env.context.get("module_uninstall")):
            raise UserError(_("Las faltas conservan su historial y se resuelven al registrar la entrada."))
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Las faltas son automáticas y no se pueden duplicar."))

    def _check_service_write(self):
        if not (self.env.su and self.env.context.get("coir_absence_write_token") is _ABSENCE_WRITE_TOKEN):
            raise AccessError(_("Las faltas las administra el proceso automático de COIRTECH."))

    def _service(self):
        return self.sudo().with_context(coir_absence_write_token=_ABSENCE_WRITE_TOKEN)

    @api.model
    def _work_intervals_by_employee(self, employees, day, timezone):
        """Effective schedules, including public holidays and approved calendar leaves."""
        start, stop = _day_bounds(day, timezone)
        calendars = employees._get_calendars(day)
        grouped = defaultdict(lambda: self.env["hr.employee"])
        result = {employee.id: [] for employee in employees}
        for employee in employees:
            # Odoo 19 falls back to the resource's current calendar when no
            # contract version covers the requested date. A known future or
            # ended contract must not turn that fallback into a required day.
            contracts = employee.version_ids.filtered("contract_date_start")
            if contracts and not any(version._is_in_contract(day) for version in contracts):
                continue
            calendar = calendars.get(employee.id)
            if calendar:
                grouped[(calendar.id, calendar.tz or employee.tz or timezone)] |= employee
        for (calendar_id, calendar_tz), selected in grouped.items():
            calendar = self.env["resource.calendar"].browse(calendar_id)
            work = calendar._work_intervals_batch(
                start, stop, resources=selected.resource_id,
                tz=pytz.timezone(calendar_tz), compute_leaves=True,
            )
            for employee in selected:
                result[employee.id] = [
                    (_utc_naive(begin), _utc_naive(end))
                    for begin, end, _attendance in work[employee.resource_id.id]
                    if end > begin
                ]
        return result

    @api.model
    def _presence_by_employee(self, employees, day, timezone, now):
        start, stop = _day_bounds(day, timezone)
        previous_start, _unused = _day_bounds(fields.Date.to_date(day) - timedelta(days=1), timezone)
        records = self.env["hr.attendance"].sudo().search([
            ("employee_id", "in", employees.ids),
            ("check_in", "<", _utc_naive(stop)), ("check_in", "<=", now),
            "|", "|", ("check_in", ">=", _utc_naive(start)),
            ("check_out", ">", _utc_naive(start)),
            "&", ("check_out", "=", False), ("check_in", ">=", _utc_naive(previous_start)),
        ], order="check_in, id")
        result = {}
        for attendance in records:
            if _genuine_attendance(attendance):
                result.setdefault(attendance.employee_id.id, attendance)
        return result

    def _set_state(self, state, now, attendance=None):
        self.ensure_one()
        attendance_id = attendance.id if attendance else False
        if self.state == state and self.attendance_id.id == attendance_id:
            return
        self._service().write({
            "state": state, "attendance_id": attendance_id,
            "resolved_at": now if state != "absent" else False,
        })
        self.employee_id.invalidate_recordset(["coir_absent_today", "coir_absence_label"])

    @api.model
    def _generate_for_day(self, company, day, now=None):
        """Idempotent current-day service. Dates in the past are not backfilled."""
        company.ensure_one()
        company = company.sudo()
        now = _utc_naive(now or fields.Datetime.now())
        day = fields.Date.to_date(day)
        timezone = company.coir_absence_tz or "America/Mexico_City"
        local_now = pytz.UTC.localize(now).astimezone(pytz.timezone(timezone))
        if (not company.coir_meal_control_enabled or not company.coir_absence_enabled
                or day != local_now.date() or day.weekday() >= 5 or local_now.hour < 9):
            return self.browse()
        service = self._service().with_company(company)
        employees = self.env["hr.employee"].sudo().with_company(company).search([
            ("active", "=", True), ("company_id", "=", company.id),
        ], order="id")
        employees._coir_lock_employee()
        service.invalidate_model()
        work = service._work_intervals_by_employee(employees, day, timezone)
        presence = service._presence_by_employee(employees, day, timezone, now)
        existing = service.search([("company_id", "=", company.id), ("date", "=", day)])
        by_employee = {record.employee_id.id: record for record in existing}
        active = service.browse()
        for employee in employees:
            record = by_employee.get(employee.id)
            attendance = presence.get(employee.id)
            intervals = work[employee.id]
            if attendance:
                if record:
                    record._set_state("resolved", now, attendance)
                continue
            if not intervals:
                if record:
                    record._set_state("cancelled", now)
                continue
            # Fixed 09:00 cutoff as requested; a scheduled later shift does not
            # move the cutoff. These timestamps are indicators, never work time.
            if not record:
                section = employee.coir_meal_section_id
                record = service.create({
                    "employee_id": employee.id, "company_id": company.id,
                    "department_id": employee.department_id.id,
                    "section_id": section.id, "section_name": section.name or False,
                    "date": day, "timezone": timezone, "state": "absent",
                    "generated_at": now,
                    "start_datetime": min(begin for begin, end in intervals),
                    "end_datetime": max(end for begin, end in intervals),
                })
                employee.invalidate_recordset(["coir_absent_today", "coir_absence_label"])
            else:
                record._set_state("absent", now)
            active |= record
        # Archiving an employee today removes the active visual indicator.
        for record in existing.filtered(lambda row: row.employee_id not in employees and row.state == "absent"):
            record._set_state("cancelled", now)
        return active.with_env(self.env)

    @api.model
    def _cron_generate_absences(self):
        now = _utc_naive(fields.Datetime.now())
        companies = self.env["res.company"].sudo().search([
            ("coir_meal_control_enabled", "=", True), ("coir_absence_enabled", "=", True),
        ], order="id")
        for company in companies:
            day = pytz.UTC.localize(now).astimezone(pytz.timezone(company.coir_absence_tz)).date()
            self._generate_for_day(company, day, now=now)
        return True

    @api.model
    def _reconcile_employee(self, employee, day, now=None, allow_create=False):
        """Reconcile an existing day after a real attendance change."""
        employee.ensure_one()
        now = _utc_naive(now or fields.Datetime.now())
        day = fields.Date.to_date(day)
        employee = employee.sudo()
        employee._coir_lock_employee()
        service = self._service()
        service.invalidate_model()
        records = service.search([("employee_id", "=", employee.id), ("date", "=", day)])
        if not records and allow_create:
            return self._generate_for_day(employee.company_id, day, now=now)
        for record in records:
            presence = service._presence_by_employee(employee, day, record.timezone, now).get(employee.id)
            if presence:
                record._set_state("resolved", now, presence)
            else:
                intervals = service.with_company(record.company_id)._work_intervals_by_employee(
                    employee, day, record.timezone,
                )[employee.id] if day.weekday() < 5 else []
                record._set_state("absent" if intervals else "cancelled", now)
        return records.with_env(self.env)

    @api.model
    def _reconcile_employees(self, employees, attendance_spans=None):
        """Only existing dates; a manual import never invents historical absences."""
        if not employees:
            return
        service = self._service()
        domain = Domain("employee_id", "in", employees.ids)
        if attendance_spans is not None:
            windows = []
            for employee_id, check_in, check_out in attendance_spans:
                # UTC date +/- one day safely contains any retained local zone.
                # An open attendance covers only its entry date and the next
                # local day, matching _presence_by_employee's overnight rule.
                lower = _utc_naive(check_in).date() - timedelta(days=1)
                upper = (_utc_naive(check_out).date() if check_out
                         else _utc_naive(check_in).date() + timedelta(days=1)) + timedelta(days=1)
                windows.append(
                    Domain("employee_id", "=", employee_id)
                    & Domain("date", ">=", lower) & Domain("date", "<=", upper)
                )
            if not windows:
                return
            domain &= Domain.OR(windows)
        records = service.search(domain)
        for record in records.sorted(lambda row: (row.employee_id.id, row.date, row.id)):
            service._reconcile_employee(record.employee_id, record.date)


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    def _coir_affected_absences(self):
        """Approved leave/holiday corrections also reconcile existing past days."""
        if not self:
            return self.env["coir.attendance.absence"]
        start = min(self.mapped("date_from")).date() - timedelta(days=1)
        stop = max(self.mapped("date_to")).date() + timedelta(days=1)
        domain = [("date", ">=", start), ("date", "<=", stop)]
        if all(leave.company_id for leave in self):
            domain.append(("company_id", "in", self.company_id.ids))
        return self.env["coir.attendance.absence"].sudo().search(domain)

    def _coir_reconcile_absence_records(self, absences):
        for absence in absences.sorted(lambda row: (row.employee_id.id, row.date, row.id)):
            absence._reconcile_employee(absence.employee_id, absence.date)

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._coir_reconcile_absence_records(leaves._coir_affected_absences())
        return leaves

    def write(self, vals):
        affects_schedule = bool({"date_from", "date_to", "resource_id", "calendar_id", "company_id", "time_type"}.intersection(vals))
        before = self._coir_affected_absences() if affects_schedule else self.env["coir.attendance.absence"]
        result = super().write(vals)
        if affects_schedule:
            self._coir_reconcile_absence_records(before | self._coir_affected_absences())
        return result

    def unlink(self):
        affected = self._coir_affected_absences()
        result = super().unlink()
        self._coir_reconcile_absence_records(affected)
        return result
