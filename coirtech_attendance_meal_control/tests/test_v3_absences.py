from datetime import datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirV3Absences(TransactionCase):
    """Real ORM checks: dates, effective calendar, attendance hooks and isolation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            "auto_check_out": False, "coir_meal_control_enabled": True,
            "coir_absence_enabled": True, "coir_absence_tz": "America/Mexico_City",
        })
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "COIRTECH V3 weekdays", "company_id": cls.company.id,
            "tz": "America/Mexico_City",
            "attendance_ids": [Command.clear()] + [Command.create({
                "name": "Weekday", "dayofweek": str(day), "day_period": "morning",
                "hour_from": 8, "hour_to": 17,
            }) for day in range(5)],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "COIRTECH V3 absence employee", "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id, "tz": "America/Mexico_City", "ruleset_id": False,
        })
        cls.Absence = cls.env["coir.attendance.absence"]
        cls.officer = new_test_user(
            cls.env, login="coir_v3_absence_officer", company_id=cls.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_officer",
        )
        cls.all_reader = new_test_user(
            cls.env, login="coir_v3_absence_reader", company_id=cls.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_user",
        )

    def _run(self, stamp="2026-11-23 15:00:00", day="2026-11-23"):
        now = fields.Datetime.to_datetime(stamp)
        with patch.object(fields.Datetime, "now", return_value=now):
            self.Absence._generate_for_day(self.company, day, now=now)
        return self.Absence.search([("employee_id", "=", self.employee.id), ("date", "=", day)])

    def _attendance(self, check_in="2026-11-23 16:30:00", check_out=False, **extra):
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(check_in)):
            return self.env["hr.attendance"].create({
                "employee_id": self.employee.id, "check_in": check_in,
                "check_out": check_out, **extra,
            })

    def test_no_falta_before_nine_then_one_at_nine_without_fake_attendance(self):
        self.assertFalse(self._run("2026-11-23 14:59:59"))
        before = self.env["hr.attendance"].search_count([("employee_id", "=", self.employee.id)])
        absence = self._run()
        self.assertEqual(len(absence), 1)
        self.assertEqual(absence.state, "absent")
        self.assertEqual(absence.date, datetime(2026, 11, 23).date())
        self.assertEqual(absence.start_datetime, datetime(2026, 11, 23, 14))
        self.assertEqual(absence.end_datetime, datetime(2026, 11, 23, 23))
        self.assertEqual(self.env["hr.attendance"].search_count([("employee_id", "=", self.employee.id)]), before)
        self.assertEqual(self._run("2026-11-23 17:00:00"), absence)

    def test_saturday_and_sunday_excluded_even_when_calendar_contains_work(self):
        self.calendar.write({"attendance_ids": [Command.create({
            "name": "Weekend", "dayofweek": str(day), "day_period": "morning", "hour_from": 8, "hour_to": 17,
        }) for day in (5, 6)]})
        for day in ("2026-11-28", "2026-11-29"):
            self.assertFalse(self._run(day + " 15:00:00", day))

    def test_nonworking_weekday_and_full_day_public_holiday_are_excluded(self):
        self.calendar.attendance_ids.filtered(lambda row: row.dayofweek == "1").unlink()
        self.assertFalse(self._run("2026-11-24 15:00:00", "2026-11-24"))
        self.env["resource.calendar.leaves"].create({
            "name": "Public holiday", "calendar_id": self.calendar.id,
            "date_from": "2026-11-23 06:00:00", "date_to": "2026-11-24 06:00:00",
        })
        self.assertFalse(self._run())

    def test_approved_calendar_leave_excludes_only_the_absent_employee(self):
        other = self.env["hr.employee"].create({
            "name": "Still scheduled", "company_id": self.company.id,
            "resource_calendar_id": self.calendar.id,
            "tz": "America/Mexico_City", "ruleset_id": False,
        })
        self.env["resource.calendar.leaves"].create({
            "name": "Approved leave", "resource_id": self.employee.resource_id.id,
            "calendar_id": self.calendar.id,
            "date_from": "2026-11-23 06:00:00", "date_to": "2026-11-24 06:00:00",
        })
        self.assertFalse(self._run())
        self.assertEqual(self.Absence.search([
            ("employee_id", "=", other.id), ("date", "=", "2026-11-23"),
        ]).state, "absent")

    def test_present_on_time_has_no_absence(self):
        attendance = self._attendance("2026-11-23 14:00:00")
        self.assertFalse(self._run())
        self.assertEqual(attendance.check_in, datetime(2026, 11, 23, 14))

    def test_late_native_entry_resolves_same_absence_and_preserves_real_time(self):
        absence = self._run()
        attendance = self._attendance()
        self.assertEqual(absence.state, "resolved")
        self.assertEqual(absence.attendance_id, attendance)
        self.assertEqual(attendance.check_in, datetime(2026, 11, 23, 16, 30))
        self.assertEqual(absence.resolved_at, attendance.check_in)
        self.assertEqual(self._run("2026-11-23 17:00:00"), absence)
        self.assertEqual(absence.state, "resolved")

    def test_late_kiosk_entry_resolves_absence_and_keeps_paid_policy(self):
        absence = self._run()
        stamp = datetime(2026, 11, 23, 16, 30)
        with patch.object(fields.Datetime, "now", return_value=stamp):
            state = self.employee._coir_meal_state()
            attendance = self.employee._coir_apply_meal_action(
                "check_in", state["attendance_id"], state["state"], expected_revision=state["revision"],
            )
        self.assertEqual(absence.state, "resolved")
        self.assertTrue(attendance.coir_managed)
        self.assertEqual(attendance.check_in, stamp)

    def test_overnight_real_attendance_counts_as_present(self):
        self._attendance("2026-11-23 05:00:00", "2026-11-23 13:00:00")
        self.assertFalse(self._run())

    def test_old_unclosed_attendance_does_not_hide_absences_forever(self):
        self._attendance("2026-11-20 14:00:00")
        self.assertEqual(self._run().state, "absent")

    def test_native_technical_placeholder_does_not_resolve_falta(self):
        self._attendance("2026-11-23 06:00:00", "2026-11-23 06:00:01",
                         in_mode="technical", out_mode="technical")
        absence = self._run()
        self.assertEqual(absence.state, "absent")
        self.assertFalse(absence.attendance_id)

    def test_deleting_attendance_reactivates_existing_falta_only(self):
        absence = self._run()
        attendance = self._attendance()
        self.assertEqual(absence.state, "resolved")
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 17)):
            attendance.unlink()
        self.assertEqual(absence.state, "absent")
        self.assertFalse(absence.attendance_id)
        self.assertEqual(self.Absence.search_count([("employee_id", "=", self.employee.id)]), 1)

    def test_correcting_attendance_date_reactivates_the_original_absence(self):
        absence = self._run()
        attendance = self._attendance()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 25, 17)):
            attendance.write({"check_in": "2026-11-25 16:00:00"})
        self.assertEqual(absence.state, "absent")
        self.assertFalse(absence.attendance_id)
        self.assertEqual(self.Absence.search_count([("employee_id", "=", self.employee.id)]), 1)

    def test_fixed_nine_cutoff_is_not_moved_to_an_afternoon_shift(self):
        self.calendar.attendance_ids.write({"hour_from": 14, "hour_to": 20})
        self.assertEqual(self._run().state, "absent")

    def test_company_timezone_and_no_historical_generation(self):
        self.company.coir_absence_tz = "UTC"
        self.assertFalse(self._run("2026-11-23 08:59:59"))
        self.assertEqual(self._run("2026-11-23 09:00:00").state, "absent")
        self.assertFalse(self._run("2026-11-24 15:00:00", "2026-11-16"))

    def test_archived_and_disabled_are_not_generated(self):
        self.employee.active = False
        self.assertFalse(self._run())
        self.employee.active = True
        self.company.coir_absence_enabled = False
        self.assertFalse(self._run())
        self.company.write({"coir_absence_enabled": True, "coir_meal_control_enabled": False})
        self.assertFalse(self._run())

    def test_future_or_ended_explicit_contract_is_not_a_required_day(self):
        version = self.employee.version_id
        version.write({"contract_date_start": "2026-12-01", "date_version": "2026-12-01"})
        self.assertFalse(self._run())
        version.write({
            "contract_date_start": "2026-11-01", "contract_date_end": "2026-11-20",
            "date_version": "2026-11-01",
        })
        self.assertFalse(self._run())

    def test_today_badge_disappears_after_entry(self):
        self._run()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 15)):
            self.employee.invalidate_recordset(["coir_absent_today", "coir_absence_label"])
            self.assertTrue(self.employee.coir_absent_today)
            self.assertEqual(self.employee.coir_absence_label, "FALTA")
        self._attendance()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 17)):
            self.employee.invalidate_recordset(["coir_absent_today", "coir_absence_label"])
            self.assertFalse(self.employee.coir_absent_today)
            self.assertFalse(self.employee.coir_absence_label)

    def test_read_scope_and_service_only_mutations(self):
        absence = self._run()
        self.assertFalse(self.Absence.with_user(self.officer).search([("id", "=", absence.id)]))
        self.employee.attendance_manager_id = self.officer
        self.assertEqual(self.Absence.with_user(self.officer).search([("id", "=", absence.id)]).ids, absence.ids)
        self.assertEqual(self.Absence.with_user(self.all_reader).search([("id", "=", absence.id)]).ids, absence.ids)
        for target in (absence.with_user(self.officer), absence.sudo()):
            with self.assertRaises(AccessError):
                target.with_context(coir_absence_write_token="forged").write({"state": "resolved"})
            with self.assertRaises(UserError):
                target.unlink()
        with self.assertRaises(AccessError):
            self.Absence.sudo().create({"employee_id": self.employee.id})

    def test_public_leave_added_after_detection_cancels_indicator(self):
        absence = self._run()
        self.env["resource.calendar.leaves"].create({
            "name": "Approved after detection", "calendar_id": self.calendar.id,
            "resource_id": self.employee.resource_id.id,
            "date_from": "2026-11-23 06:00:00", "date_to": "2026-11-24 06:00:00",
        })
        self._run("2026-11-23 17:00:00")
        self.assertEqual(absence.state, "cancelled")

    def test_cron_checks_current_company_local_date(self):
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 23, 15)):
            self.Absence._cron_generate_absences()
        self.assertEqual(self.Absence.search([
            ("employee_id", "=", self.employee.id), ("date", "=", "2026-11-23"),
        ]).state, "absent")

    def test_company_isolation_in_generation_and_read_access(self):
        company = self.env["res.company"].create({
            "name": "COIRTECH second absence test company", "auto_check_out": False,
            "coir_meal_control_enabled": True, "coir_absence_enabled": True,
            "coir_absence_tz": "America/Mexico_City",
        })
        calendar = self.calendar.copy({"company_id": company.id})
        employee = self.env["hr.employee"].create({
            "name": "Other company absence employee", "company_id": company.id,
            "resource_calendar_id": calendar.id, "tz": "America/Mexico_City", "ruleset_id": False,
        })
        self._run()
        self.assertFalse(self.Absence.search([("employee_id", "=", employee.id)]))
        self.Absence._generate_for_day(company, "2026-11-23", now=datetime(2026, 11, 23, 15))
        other = self.Absence.search([("employee_id", "=", employee.id)])
        self.assertEqual(other.company_id, company)
        self.assertEqual(other.state, "absent")
        self.assertFalse(self.Absence.with_user(self.all_reader).search([("id", "=", other.id)]))

    def test_retroactive_leave_updates_existing_history_and_removal_restores_falta(self):
        absence = self._run()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 11, 26, 16)):
            leave = self.env["resource.calendar.leaves"].create({
                "name": "Retroactively approved", "calendar_id": self.calendar.id,
                "resource_id": self.employee.resource_id.id,
                "date_from": "2026-11-23 06:00:00", "date_to": "2026-11-24 06:00:00",
            })
            self.assertEqual(absence.state, "cancelled")
            leave.unlink()
        self.assertEqual(absence.state, "absent")
        self.assertFalse(absence.attendance_id)
