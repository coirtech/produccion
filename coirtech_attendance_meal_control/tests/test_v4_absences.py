from datetime import datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirV4Absences(TransactionCase):
    """Real Time Off records, authorization transitions and exclusion history."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            "auto_check_out": False, "coir_meal_control_enabled": True,
            "coir_absence_enabled": True, "coir_absence_tz": "America/Mexico_City",
            "coir_absence_tracking_started_at": "2026-11-01 06:00:00",
        })
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "COIRTECH V4 eight hours", "company_id": cls.company.id,
            "tz": "America/Mexico_City",
            "attendance_ids": [Command.clear()] + [Command.create({
                "name": "V4 work", "dayofweek": str(day), "day_period": period,
                "hour_from": start, "hour_to": stop,
            }) for day in range(5) for period, start, stop in (("morning", 8, 12), ("afternoon", 13, 17))],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "V4 Time Off employee", "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id, "tz": "America/Mexico_City", "ruleset_id": False,
        })
        cls.Absence = cls.env["coir.attendance.absence"]
        cls.vacation = cls._new_type("vacation")
        cls.paid = cls._new_type("paid_absence")
        cls.unpaid = cls._new_type("unpaid_absence")
        cls.disability = cls._new_type("disability")
        cls.hourly = cls._new_type("paid_absence", "hour")
        cls.half_day = cls._new_type("vacation", "half_day")
        cls.officer = new_test_user(
            cls.env, login="coir_v4_backend_officer", company_id=cls.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_officer",
        )

    @classmethod
    def _new_type(cls, category=False, unit="day", validation="no_validation"):
        return cls.env["hr.leave.type"].create({
            "name": "V4 type %s %s %s" % (category or "unmapped", unit, validation),
            "company_id": cls.company.id, "requires_allocation": False,
            "leave_validation_type": validation, "request_unit": unit,
            "coir_attendance_category": category,
        })

    def _record(self, day="2026-11-23", employee=None):
        return self.Absence.search([
            ("employee_id", "=", (employee or self.employee).id), ("date", "=", day),
        ])

    def _run(self, now="2026-11-23 15:00:00", day="2026-11-23"):
        stamp = fields.Datetime.to_datetime(now)
        with patch.object(fields.Datetime, "now", return_value=stamp):
            self.Absence._generate_for_day(self.company, day, now=stamp)
        return self._record(day)

    def _leave(self, leave_type=None, day="2026-11-23", end_day=None,
               now="2026-11-23 15:00:00", **extra):
        values = {
            "employee_id": self.employee.id, "holiday_status_id": (leave_type or self.vacation).id,
            "request_date_from": day, "request_date_to": end_day or day,
            **extra,
        }
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(now)):
            return self.env["hr.leave"].create(values)

    def _attendance(self, check_in="2026-11-23 19:05:00", check_out=False):
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(check_in)):
            return self.env["hr.attendance"].create({
                "employee_id": self.employee.id, "check_in": check_in, "check_out": check_out,
            })

    def test_full_approved_leave_replaces_falta_without_worked_hours(self):
        original = self._run()
        leave = self._leave(now="2026-11-23 16:00:00")
        self.assertEqual(leave.state, "validate")
        self.assertEqual(self._record(), original)
        self.assertEqual(original.state, "approved")
        self.assertEqual(original.report_label, "VACACIONES")
        self.assertEqual(original.leave_hours, 8)
        self.assertTrue(original.was_automatic_absence)
        self.assertFalse(original.attendance_id)
        self.assertFalse(self.env["hr.attendance"].search([
            ("employee_id", "=", self.employee.id), ("coir_managed", "=", True),
        ]))
        self._run("2026-11-23 18:00:00")
        self.assertEqual(self._record(), original)
        self.assertEqual(original.state, "approved")

    def test_all_four_explicit_categories_are_distinct_from_automatic_falta(self):
        for leave_type, day, label in (
            (self.vacation, "2026-11-23", "VACACIONES"),
            (self.paid, "2026-11-24", "FALTA CON SUELDO"),
            (self.unpaid, "2026-11-25", "FALTA SIN SUELDO"),
            (self.disability, "2026-11-26", "INCAPACIDAD"),
        ):
            self._leave(leave_type, day)
            record = self._record(day)
            self.assertEqual(record.state, "approved")
            self.assertEqual(record.leave_label, label)
            self.assertFalse(record.was_automatic_absence)

    def test_unmapped_approved_type_protects_against_false_falta(self):
        leave_type = self._new_type()
        self._leave(leave_type)
        record = self._run()
        self.assertEqual(record.state, "approved")
        self.assertIn("TIPO POR CONFIGURAR", record.leave_label)
        leave_type.coir_attendance_category = "disability"
        self.assertEqual(record.leave_label, "INCAPACIDAD")

    def test_second_approval_pending_is_not_final_approval(self):
        leave_type = self._new_type("vacation", validation="both")
        leave = self._leave(leave_type)
        self.assertEqual(leave.state, "confirm")
        self.assertEqual(self._run().state, "absent")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            leave.action_approve(check_state=False)
        self.assertEqual(leave.state, "validate1")
        self.assertEqual(self._record().state, "absent")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 17)):
            leave.action_approve()
        self.assertEqual(leave.state, "validate")
        self.assertEqual(self._record().state, "approved")

    def test_partial_hours_have_no_full_falta_and_review_only_after_remaining_work(self):
        self._run()
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        record = self._record()
        self.assertEqual(record.state, "partial")
        self.assertEqual(record.leave_hours, 4)
        self.assertIn("08:00–12:00", record.leave_periods)
        self._run("2026-11-23 22:59:59")
        self.assertEqual(record.state, "partial")
        self._run("2026-11-23 23:00:00")
        self.assertEqual(record.state, "review")
        self.assertIn("sin registro de asistencia", record.review_reason)
        self.assertNotEqual(record.state, "absent")

    def test_native_half_day_is_partial_and_late_entry_keeps_real_time(self):
        self._leave(self.half_day, request_date_from_period="am", request_date_to_period="am")
        record = self._record()
        self.assertEqual(record.state, "partial")
        self.assertEqual(record.leave_hours, 4)
        attendance = self._attendance()
        self.assertEqual(record.state, "partial")
        self.assertFalse(record.review_reason)
        self.assertEqual(record.attendance_id, attendance)
        self.assertEqual(attendance.check_in, datetime(2026, 11, 23, 19, 5))
        self.assertIn("VACACIONES", record.leave_label)

    def test_afternoon_permission_closes_review_at_end_of_required_morning(self):
        self._leave(self.hourly, request_hour_from=13, request_hour_to=17)
        record = self._run("2026-11-23 17:59:59")
        self.assertEqual(record.state, "partial")
        self._run("2026-11-23 18:00:00")
        self.assertEqual(record.state, "review")
        self.assertFalse(record.was_automatic_absence)

    def test_real_entry_resolves_only_missing_attendance_incident(self):
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        record = self._run("2026-11-23 23:00:00")
        self.assertEqual(record.state, "review")
        attendance = self._attendance("2026-11-23 23:30:00")
        self.assertEqual(record.state, "partial")
        self.assertFalse(record.review_reason)
        self.assertEqual(record.attendance_id, attendance)
        self.assertEqual(record.leave_hours, 4)

    def test_entry_during_approved_interval_is_review_without_deleting_either_source(self):
        leave = self._leave()
        attendance = self._attendance("2026-11-23 16:00:00")
        record = self._record()
        self.assertEqual(record.state, "review")
        self.assertIn("durante una ausencia aprobada", record.review_reason)
        self.assertEqual(leave.state, "validate")
        self.assertEqual(attendance.check_in, datetime(2026, 11, 23, 16))
        self.assertTrue(record.leave_ids)

    def test_entry_at_exact_end_of_authorized_interval_is_not_overlap(self):
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        self._attendance("2026-11-23 18:00:00")
        self.assertEqual(self._record().state, "partial")
        self.assertFalse(self._record().review_reason)

    def test_distinct_contiguous_permissions_can_cover_full_day(self):
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        afternoon_type = self._new_type("vacation", "hour")
        self._leave(afternoon_type, request_hour_from=13, request_hour_to=17)
        record = self._record()
        self.assertEqual(record.state, "approved")
        self.assertEqual(record.leave_hours, 8)
        self.assertIn("FALTA CON SUELDO", record.leave_label)
        self.assertIn("VACACIONES", record.leave_label)
        self.assertFalse(record.review_reason)

    def test_overlapping_approved_permissions_are_reviewed_without_double_counting(self):
        other_type = self._new_type("vacation", "hour")
        # Native Odoo only permits "on top" requests on Worked Time types.
        # Create the Worked Time request first, so its interval remains part
        # of the employee's native work time when the absence is approved.
        # The COIRTECH mapping is independent from that accrual classification.
        other_type.write({"time_type": "other", "allow_request_on_top": True})
        self._leave(other_type, request_hour_from=10, request_hour_to=12)
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        record = self._record()
        self.assertEqual(record.state, "review")
        self.assertIn("superpuestas", record.review_reason)
        self.assertEqual(record.leave_hours, 4)
        self.assertEqual(len(record.leave_ids), 2)

    def test_hourly_permission_covering_short_workday_counts_as_full(self):
        self.calendar.attendance_ids.filtered(lambda row: row.day_period == "afternoon").unlink()
        self.calendar.attendance_ids.write({"hour_to": 10})
        self._leave(self.hourly, request_hour_from=8, request_hour_to=10)
        record = self._record()
        self.assertEqual(record.state, "approved")
        self.assertEqual(record.leave_hours, 2)

    def test_retroactive_full_approval_corrects_original_falta_then_cancel_restores_it(self):
        original = self._run()
        leave = self._leave(now="2026-11-25 18:00:00")
        self.assertEqual(original.state, "approved")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 26, 18)):
            leave.write({"state": "cancel"})
        self.assertEqual(original.state, "absent")
        self.assertTrue(original.was_automatic_absence)
        self.assertEqual(self._record(), original)

    def test_historical_cancel_without_original_falta_creates_review_not_backfill(self):
        leave = self._leave(now="2026-11-23 14:00:00")
        record = self._record()
        self.assertFalse(record.was_automatic_absence)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 25, 18)):
            leave.write({"state": "cancel"})
        self.assertEqual(record.state, "review")
        self.assertIn("cancelada o modificada", record.review_reason)
        self.assertFalse(record.was_automatic_absence)

    def test_today_cancel_without_original_falta_uses_current_cutoff(self):
        leave = self._leave(now="2026-11-23 14:00:00")
        record = self._record()
        self.assertFalse(record.was_automatic_absence)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            leave.write({"state": "cancel"})
        self.assertEqual(record.state, "absent")
        self.assertTrue(record.was_automatic_absence)

    def test_approved_sources_before_tracking_are_visible_without_historical_incidence(self):
        self.company.coir_absence_tracking_started_at = "2026-11-24 06:00:00"
        leave = self._leave(now="2026-11-25 18:00:00")
        record = self._record()
        self.assertEqual(record.state, "approved")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 25, 18)):
            leave.write({"state": "cancel"})
        self.assertEqual(record.state, "cancelled")
        self.assertFalse(record.was_automatic_absence)

    def test_initial_sync_reads_existing_approved_sources_without_generating_missing_days(self):
        self.company.coir_meal_control_enabled = False
        self._leave(day="2026-11-16", now="2026-11-20 18:00:00")
        self.assertFalse(self._record("2026-11-16"))
        self.company.coir_meal_control_enabled = True
        self.assertEqual(self._record("2026-11-16").state, "approved")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 25, 18)):
            self.Absence._sync_approved_leaves("2026-11-16", "2026-11-20", [self.company.id])
        record = self._record("2026-11-16")
        self.assertEqual(record.state, "approved")
        self.assertFalse(record.was_automatic_absence)
        self.assertFalse(self._record("2026-11-17"))
        self.assertFalse(self._record("2026-11-18"))

    def test_exclusion_removes_current_falta_records_audit_and_keeps_clock_in(self):
        record = self._run()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            self.employee.coir_attendance_report_excluded = True
        self.assertEqual(record.state, "cancelled")
        self.assertIn("Excluido", record.resolution_reason)
        history = self.employee.coir_attendance_exclusion_ids
        self.assertEqual(len(history), 1)
        self.assertFalse(history.end_datetime)
        self.assertEqual(history.excluded_by_id, self.env.user)
        attendance = self._attendance("2026-11-23 17:00:00")
        self.assertTrue(attendance.exists())
        self.assertEqual(attendance.check_in, datetime(2026, 11, 23, 17))
        self.assertFalse(self._run("2026-11-23 18:00:00").filtered(lambda row: row.state == "absent"))

    def test_reinclusion_evaluates_today_and_never_reactivates_excluded_yesterday(self):
        monday = self._run()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            self.employee.coir_attendance_report_excluded = True
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 24, 16)):
            self.employee.coir_attendance_report_excluded = False
            self.Absence._reconcile_employee(self.employee, fields.Date.to_date("2026-11-23"))
        self.assertEqual(monday.state, "cancelled")
        self.assertEqual(self._record("2026-11-24").state, "absent")
        history = self.employee.coir_attendance_exclusion_ids
        self.assertEqual(history.end_datetime, datetime(2026, 11, 24, 16))
        self.assertEqual(history.included_by_id, self.env.user)

    def test_partial_leave_during_exclusion_never_creates_missing_attendance_incidence(self):
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 13)):
            self.employee.coir_attendance_report_excluded = True
        self._leave(self.hourly, request_hour_from=8, request_hour_to=12)
        record = self._run("2026-11-23 23:00:00")
        self.assertEqual(record.state, "partial")
        self.assertFalse(record.review_reason)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 24, 16)):
            self.employee.coir_attendance_report_excluded = False
            self.Absence._sync_approved_leaves("2026-11-23", "2026-11-23", [self.company.id])
        self.assertEqual(record.state, "partial")
        self.assertFalse(record.review_reason)

    def test_archiving_stops_falta_and_does_not_create_exclusion_history(self):
        record = self._run()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            self.employee.active = False
        self.assertEqual(record.state, "cancelled")
        self.assertIn("archivado", record.resolution_reason)
        self.assertFalse(self.employee.coir_attendance_exclusion_ids)
        self.assertFalse(self._run("2026-11-24 16:00:00", "2026-11-24"))

    def test_weekend_still_has_no_falta_but_real_approved_weekend_work_is_visible(self):
        self.calendar.attendance_ids = [Command.create({
            "name": "Saturday required", "dayofweek": "5", "day_period": "morning",
            "hour_from": 8, "hour_to": 12,
        })]
        self.assertFalse(self._run("2026-11-28 16:00:00", "2026-11-28"))
        self._leave(day="2026-11-28", now="2026-11-28 16:00:00")
        self.assertEqual(self._record("2026-11-28").state, "approved")

    def test_hr_permission_and_immutable_exclusion_history(self):
        with self.assertRaises(AccessError):
            self.employee.with_user(self.officer).write({"coir_attendance_report_excluded": True})
        self.employee.coir_attendance_report_excluded = True
        history = self.employee.coir_attendance_exclusion_ids
        with self.assertRaises(AccessError):
            history.sudo().with_context(coir_exclusion_write_token="forged").write({"end_datetime": fields.Datetime.now()})
        with self.assertRaises(UserError):
            history.sudo().unlink()

    def test_public_employee_filter_for_officer_without_private_hr_access(self):
        self.employee.attendance_manager_id = self.officer
        self.env.invalidate_all()
        Employee = self.env["hr.employee"].with_user(self.officer)
        self.assertEqual(Employee.search([
            ("id", "=", self.employee.id), ("coir_attendance_report_excluded", "=", False),
        ]).ids, self.employee.ids)
        self.employee.coir_attendance_report_excluded = True
        self.env.invalidate_all()
        self.assertFalse(Employee.search([
            ("id", "=", self.employee.id), ("coir_attendance_report_excluded", "=", False),
        ]))

    def test_sync_cannot_request_unauthorized_company(self):
        other = self.env["res.company"].create({"name": "V4 inaccessible company"})
        with self.assertRaises(AccessError):
            self.Absence.with_user(self.officer)._sync_approved_leaves(company_ids=[other.id])

    def test_cron_recovers_friday_partial_after_weekend_outage_without_backfill(self):
        self._leave(self.hourly, day="2026-11-20", now="2026-11-20 22:00:00",
                    request_hour_from=8, request_hour_to=12)
        record = self._record("2026-11-20")
        self.assertEqual(record.state, "partial")
        self.assertTrue(record.review_check_pending)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 15)):
            self.Absence._cron_generate_absences()
        self.assertEqual(record.state, "review")
        self.assertFalse(record.review_check_pending)
        self.assertFalse(record.was_automatic_absence)
        self.assertFalse(self._record("2026-11-19"))
        self.assertFalse(self._record("2026-11-21"))
        self.assertFalse(self._record("2026-11-22"))

    def test_flexible_calendar_keeps_v3_cutoff_without_permission_but_reviews_approved_coverage(self):
        self.calendar.write({"flexible_hours": True})
        record = self._run()
        self.assertEqual(record.state, "absent")
        self._leave()
        self.assertEqual(record.state, "review")
        self.assertIn("flexible", record.review_reason)
        self.assertEqual(record.leave_label, "VACACIONES")
        self.assertEqual(record.leave_hours, 0)
