"""V4.3 uses native Time Off names without changing authorization or attendance."""
from datetime import datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirV43Absences(TransactionCase):

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
            "name": "V4.3 workday", "company_id": cls.company.id,
            "tz": "America/Mexico_City",
            "attendance_ids": [Command.clear()] + [Command.create({
                "name": "V4.3 work", "dayofweek": str(day), "day_period": period,
                "hour_from": start, "hour_to": stop,
            }) for day in range(5)
                for period, start, stop in (("morning", 8, 12), ("afternoon", 13, 17))],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "V4.3 employee", "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id, "tz": "America/Mexico_City",
            "ruleset_id": False,
        })
        cls.Absence = cls.env["coir.attendance.absence"]

    def _type(self, name="Permiso familiar", unit="day", validation="both"):
        return self.env["hr.leave.type"].create({
            "name": name, "company_id": self.company.id, "requires_allocation": False,
            "leave_validation_type": validation, "request_unit": unit,
        })

    def _leave(self, leave_type=None, day="2026-11-23", now="2026-11-23 15:00:00", **extra):
        leave_type = leave_type or self._type()
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(now)):
            return self.env["hr.leave"].create({
                "employee_id": self.employee.id, "holiday_status_id": leave_type.id,
                "request_date_from": day, "request_date_to": day, **extra,
            })

    def _record(self, day="2026-11-23"):
        return self.Absence.search([("employee_id", "=", self.employee.id), ("date", "=", day)])

    def _reconcile(self, now="2026-11-23 15:00:00", day="2026-11-23"):
        stamp = fields.Datetime.to_datetime(now)
        with patch.object(fields.Datetime, "now", return_value=stamp):
            return self.Absence._reconcile_employee(self.employee, day, now=stamp, allow_create=True)

    def test_pending_request_preserves_native_name_and_no_authorized_hours(self):
        leave_type = self._type("Permiso familiar sin sueldo")
        leave_type.coir_attendance_category = "vacation"  # Ignored legacy data.
        leave = self._leave(leave_type)
        notice = self._reconcile()
        self.assertEqual(leave.state, "confirm")
        self.assertEqual(notice.leave_label, leave_type.name)
        self.assertEqual(notice.report_label, leave_type.name)
        self.assertEqual(notice.leave_hours, 0)
        self.assertFalse(notice.had_approved_leave)
        self.assertTrue(notice.had_leave_request)
        self.assertFalse(notice.was_automatic_absence)
        self.assertFalse(notice.review_reason)
        self.assertIn("08:00–12:00", notice.leave_periods)
        self.assertEqual(notice.leave_ids, leave)
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_first_and_final_approval_change_only_authorized_hours(self):
        leave = self._leave()
        notice = self._record()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            leave.action_approve(check_state=False)
        self.assertEqual(leave.state, "validate1")
        self.assertEqual(self._record(), notice)
        self.assertEqual(notice.leave_hours, 0)
        self.assertFalse(notice.had_approved_leave)
        self.assertEqual(notice.report_label, leave.holiday_status_id.name)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 17)):
            leave.action_approve()
        self.assertEqual(leave.state, "validate")
        self.assertEqual(notice.leave_hours, 8)
        self.assertTrue(notice.had_approved_leave)
        self.assertEqual(notice.report_label, leave.holiday_status_id.name)
        self.assertFalse(notice.attendance_id)

    def test_native_type_rename_updates_pending_and_approved_indicators(self):
        leave_type = self._type("Comisión especial")
        pending = self._leave(leave_type)
        approved = self._leave(leave_type, day="2026-11-24")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 17)):
            approved.action_approve(check_state=False)
            approved.action_approve()
            leave_type.name = "Permiso por trámite personal"
        for day in ("2026-11-23", "2026-11-24"):
            self.assertEqual(self._record(day).leave_label, leave_type.name)
            self.assertIn(leave_type.name, self._record(day).leave_periods)
        self.assertEqual(pending.state, "confirm")
        self.assertEqual(approved.state, "validate")

    def test_partial_pending_request_reviews_unworked_remainder_without_full_falta(self):
        leave = self._leave(self._type("Permiso de trámite", unit="hour"),
                            request_hour_from=8, request_hour_to=12)
        notice = self._record()
        self.assertEqual(notice.state, "partial")
        self.assertFalse(notice.review_reason)
        self.assertEqual(notice.leave_hours, 0)
        self._reconcile(now="2026-11-23 23:00:00")
        self.assertEqual(notice.state, "review")
        self.assertEqual(notice.leave_label, "Permiso de trámite")
        self.assertIn("sin registro de asistencia", notice.review_reason)
        self.assertNotIn("aprob", notice.review_reason.lower())
        self.assertEqual(leave.state, "confirm")
        self.assertFalse(notice.was_automatic_absence)

    def test_mixed_pending_and_approved_periods_count_only_approved_union(self):
        approved = self._leave(self._type("Permiso matutino", unit="hour", validation="no_validation"),
                              request_hour_from=8, request_hour_to=12)
        pending = self._leave(self._type("Permiso vespertino", unit="hour"),
                             request_hour_from=13, request_hour_to=17)
        notice = self._record()
        self.assertEqual(approved.state, "validate")
        self.assertEqual(pending.state, "confirm")
        self.assertEqual(notice.state, "approved")  # Technical full-coverage key, not hr.leave approval.
        self.assertEqual(notice.leave_hours, 4)
        self.assertEqual(notice.leave_label, "Permiso matutino + Permiso vespertino")
        self.assertIn("13:00–17:00", notice.leave_periods)
        self.assertFalse(notice.review_reason)

    def test_refused_today_request_restores_normal_cutoff_without_source_label(self):
        leave = self._leave()
        notice = self._record()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 16)):
            leave.action_refuse()
        self.assertEqual(leave.state, "refuse")
        self.assertEqual(notice.state, "absent")
        self.assertEqual(notice.report_label, "FALTA")
        self.assertFalse(notice.leave_label)
        self.assertFalse(notice.leave_ids)
        self.assertEqual(notice.leave_hours, 0)

    def test_historical_pending_cancellation_without_original_falta_only_reviews(self):
        leave = self._leave(now="2026-11-23 14:00:00")
        notice = self._record()
        self.assertFalse(notice.was_automatic_absence)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 25, 18)):
            leave.write({"state": "cancel"})
        self.assertEqual(notice.state, "review")
        self.assertFalse(notice.was_automatic_absence)
        self.assertFalse(notice.leave_label)
        self.assertFalse(notice.had_approved_leave)
        self.assertTrue(notice.had_leave_request)
        self.assertIn("cancelada", notice.review_reason)
        self.assertFalse(self._record("2026-11-24"))

    def test_pending_future_request_is_hidden_until_its_company_local_day(self):
        leave = self._leave(day="2026-11-24")
        notice = self._record("2026-11-24")
        self.assertTrue(notice)
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 24, 5, 59, 59)):
            self.assertFalse(notice._coir_visible_in_report())
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 24, 6, 0, 0)):
            self.assertEqual(notice._coir_visible_in_report(), notice)
        self.assertEqual(leave.state, "confirm")

    def test_source_sync_imports_existing_pending_without_historical_falta(self):
        self.company.coir_meal_control_enabled = False
        leave = self._leave(day="2026-11-16", now="2026-11-20 18:00:00")
        self.assertFalse(self._record("2026-11-16"))
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 15)):
            self.company.coir_meal_control_enabled = True
            self.Absence._sync_approved_leaves("2026-11-16", "2026-11-20", [self.company.id])
        notice = self._record("2026-11-16")
        self.assertEqual(notice.leave_label, leave.holiday_status_id.name)
        self.assertEqual(notice.leave_hours, 0)
        self.assertFalse(notice.was_automatic_absence)
        self.assertFalse(self._record("2026-11-17"))

    def test_mapping_configuration_is_hidden_and_no_longer_required(self):
        self.assertFalse(self.env.ref("coirtech_attendance_meal_control.coir_leave_type_menu").active)
        view = self.env.ref("coirtech_attendance_meal_control.coir_leave_type_list")
        self.assertNotIn('name="coir_attendance_category"', view.arch_db)
        leave = self._leave(self._type("Nuevo permiso sin configuración"))
        self.assertEqual(self._record().report_label, leave.holiday_status_id.name)
