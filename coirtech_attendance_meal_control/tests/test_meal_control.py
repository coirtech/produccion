from datetime import datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirMealControl(TransactionCase):
    """Exercise real attendance records, calendar calculations and access checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"auto_check_out": False, "coir_meal_control_enabled": True})
        cls.section = cls.env["coir.meal.section"].create({
            "name": "Sección 1", "company_id": cls.company.id,
        })
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "COIRTECH test calendar with native lunch",
            "company_id": cls.company.id,
            "tz": "UTC",
            "attendance_ids": [Command.clear()] + [
                Command.create({
                    "name": name, "dayofweek": "0", "day_period": period,
                    "hour_from": start, "hour_to": end,
                }) for name, period, start, end in [
                    ("Morning", "morning", 8, 12),
                    ("Lunch", "lunch", 12, 13),
                    ("Afternoon", "afternoon", 13, 17),
                ]
            ],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "COIRTECH Test Employee", "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id, "tz": "UTC",
            "ruleset_id": False, "coir_meal_section_id": cls.section.id,
        })
        cls.officer = new_test_user(
            cls.env, login="coir_meal_officer_test",
            groups="base.group_user,hr_attendance.group_hr_attendance_user",
            company_id=cls.company.id,
        )

    def _act(self, action, when, **kwargs):
        employee = self.employee.sudo()
        state = employee._coir_meal_state()
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(when)):
            return employee._coir_apply_meal_action(
                action, state["attendance_id"], state["state"], **kwargs
            )

    def test_complete_day_paid_meal_and_native_calendar(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self.assertTrue(attendance.coir_managed)
        self._act("meal_start", "2026-11-16 12:00:00")
        self.assertFalse(attendance.check_out)
        self.assertEqual(self.employee._coir_meal_state()["state"], "eating")
        self._act("meal_return", "2026-11-16 13:00:00")
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.coir_meal_hours, 1.0)
        self._act("check_out", "2026-11-16 17:00:00")
        self.assertEqual(attendance.worked_hours, 9.0)
        self.assertEqual(attendance.coir_meal_status, "returned")
        self.assertEqual(attendance.in_mode, "kiosk")
        self.assertEqual(attendance.out_mode, "kiosk")
        self.assertEqual(self.employee._coir_meal_state()["state"], "absent")

    def test_legacy_attendance_keeps_native_lunch_calculation(self):
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": "2026-11-16 08:00:00", "check_out": "2026-11-16 17:00:00",
        })
        self.assertFalse(attendance.coir_managed)
        self.assertEqual(attendance.worked_hours, 8.0)
        with self.assertRaises(AccessError):
            attendance.write({"coir_managed": True})

    def test_bad_sequence_and_stale_duplicate_are_blocked(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-16 08:00:01")
        with self.assertRaises(UserError):
            self._act("meal_return", "2026-11-16 10:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        with self.assertRaises(UserError):
            self.employee.sudo()._coir_apply_meal_action("meal_start", attendance.id, "working")
        self._act("meal_return", "2026-11-16 13:00:00")
        with self.assertRaises(UserError):
            self._act("meal_start", "2026-11-16 14:00:00")

    def test_final_exit_during_meal_requires_a_return_in_v2(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        with self.assertRaises(UserError):
            self._act("check_out", "2026-11-16 13:00:00")
        self.assertFalse(attendance.check_out)
        with self.assertRaises(UserError):
            self._act("check_out", "2026-11-16 13:00:00", confirm_without_return=True)
        self.assertFalse(attendance.coir_meal_end)
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.coir_meal_status, "open")
        self.assertEqual(attendance.coir_meal_hours, 0.0)
        self._act("meal_return", "2026-11-16 14:00:00")
        self._act("check_out", "2026-11-16 17:00:00")
        self.assertEqual(attendance.worked_hours, 9.0)

    def test_overnight_meal_is_one_attendance(self):
        attendance = self._act("check_in", "2026-11-16 23:00:00")
        self._act("meal_start", "2026-11-17 02:00:00")
        self._act("meal_return", "2026-11-17 03:00:00")
        self._act("check_out", "2026-11-17 07:00:00")
        self.assertEqual(attendance.date, datetime(2026, 11, 16).date())
        self.assertEqual(attendance.worked_hours, 8.0)
        self.assertEqual(attendance.coir_meal_hours, 1.0)

    def test_legacy_open_attendance_has_checkout_only(self):
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id, "check_in": "2026-11-16 08:00:00",
        })
        self.assertEqual(self.employee._coir_meal_state()["allowed_actions"], ["check_out"])
        with self.assertRaises(UserError):
            self._act("meal_start", "2026-11-16 12:00:00")
        self._act("check_out", "2026-11-16 17:00:00")
        self.assertFalse(attendance.coir_managed)
        self.assertEqual(attendance.worked_hours, 8.0)

    def test_section_snapshot_survives_employee_reassignment(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        section_2 = self.env["coir.meal.section"].create({
            "name": "Sección 2", "company_id": self.company.id,
        })
        self.employee.coir_meal_section_id = section_2
        self.section.name = "Nueva etiqueta"
        self.assertEqual(attendance.coir_section_id, self.section)
        self.assertEqual(attendance.coir_section_name, "Sección 1")

    def test_manager_correction_validates_and_keeps_audit(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        self._act("meal_return", "2026-11-16 13:00:00")
        self._act("check_out", "2026-11-16 17:00:00")
        attendance._coir_correct_meal(attendance.coir_meal_start, False, "RH revisa el regreso antes de confirmar su hora.")
        messages_before = len(attendance.message_ids)
        wizard = self.env["coir.meal.correction"].create({
            "attendance_id": attendance.id,
            "meal_start": "2026-11-16 12:00:00", "meal_end": "2026-11-16 13:00:00",
            "reason": "RH confirmó el regreso omitido.",
        })
        wizard.action_apply()
        self.assertEqual(attendance.coir_meal_status, "returned")
        self.assertEqual(attendance.coir_meal_hours, 1.0)
        self.assertEqual(attendance.worked_hours, 9.0)
        self.assertGreater(len(attendance.message_ids), messages_before)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            attendance._coir_correct_meal(
                fields.Datetime.to_datetime("2026-11-16 12:00:00"),
                fields.Datetime.to_datetime("2026-11-16 18:00:00"), "Invalid correction",
            )
        with self.assertRaises(ValidationError):
            attendance._coir_correct_meal(attendance.coir_meal_start, attendance.coir_meal_end, " ")

    def test_correction_defaults_keep_existing_meal_timestamps(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        self._act("meal_return", "2026-11-16 13:00:00")
        defaults = self.env["coir.meal.correction"].with_context(
            default_attendance_id=attendance.id,
        ).default_get(["attendance_id", "meal_start", "meal_end", "reason"])
        self.assertEqual(defaults["attendance_id"], attendance.id)
        self.assertEqual(defaults["meal_start"], attendance.coir_meal_start)
        self.assertEqual(defaults["meal_end"], attendance.coir_meal_end)

    def test_direct_correction_and_policy_forgery_are_blocked(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        as_officer = attendance.with_user(self.officer)
        with self.assertRaises(AccessError):
            as_officer.with_context(coir_write_token="fake").write({
                "coir_meal_start": "2026-11-16 12:00:00",
            })
        with self.assertRaises(AccessError):
            as_officer._coir_correct_meal(False, False, "Unauthorized")
        with self.assertRaises(AccessError):
            as_officer.write({"check_out": "2026-11-16 17:00:00"})

    def test_auto_checkout_cannot_conflict_with_manual_mode(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.company.auto_check_out = True

    def test_section_cannot_be_assigned_across_companies(self):
        company_2 = self.env["res.company"].create({"name": "COIRTECH Second Test Company"})
        section_2 = self.env["coir.meal.section"].create({
            "name": "Other Company Section", "company_id": company_2.id,
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            self.employee.coir_meal_section_id = section_2

    def test_meal_records_cannot_be_silently_deleted(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        with self.assertRaises(UserError):
            attendance.unlink()
