from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirV2Workflow(TransactionCase):
    """Real ORM workflow and cross-channel daily entry protection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"auto_check_out": False, "coir_meal_control_enabled": True})
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "COIRTECH V2 paid interval test", "company_id": cls.company.id, "tz": "UTC",
            "attendance_ids": [Command.clear()] + [Command.create({
                "name": label, "dayofweek": "0", "day_period": period, "hour_from": start, "hour_to": end,
            }) for label, period, start, end in [
                ("Morning", "morning", 8, 12), ("Lunch", "lunch", 12, 13), ("Afternoon", "afternoon", 13, 17),
            ]],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "COIRTECH V2 Employee", "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id, "tz": "UTC", "ruleset_id": False,
        })
        cls.officer = new_test_user(
            cls.env, login="coir_v2_officer", groups="base.group_user,hr_attendance.group_hr_attendance_user",
            company_id=cls.company.id,
        )

    def _act(self, action, stamp):
        employee = self.employee.sudo()
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(stamp)):
            snapshot = employee._coir_meal_state()
            return employee._coir_apply_meal_action(
                action, snapshot["attendance_id"], snapshot["state"], expected_revision=snapshot["revision"],
            )

    def _state(self, stamp):
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(stamp)):
            return self.employee.sudo()._coir_meal_state()

    def _closed_day(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("check_out", "2026-11-16 17:00:00")
        return attendance

    def _grant(self, date="2026-11-16"):
        return self.env["coir.reentry.authorization"].create({
            "employee_id": self.employee.id, "valid_date": date,
            "reason": "Jornada extraordinaria confirmada por Recursos Humanos.",
        })

    def test_paid_multiple_outings_and_meal_keep_nine_hours(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("work_exit", "2026-11-16 10:00:00")
        self.assertFalse(attendance.check_out)
        self._act("work_return", "2026-11-16 11:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        self._act("meal_return", "2026-11-16 13:00:00")
        self._act("work_exit", "2026-11-16 15:00:00")
        self._act("work_return", "2026-11-16 15:30:00")
        self._act("check_out", "2026-11-16 17:00:00")
        self.assertEqual(len(attendance.coir_work_outing_ids), 2)
        self.assertEqual(attendance.worked_hours, 9.0)
        self.assertEqual(attendance.coir_work_hours, 1.5)
        self.assertEqual(attendance.coir_meal_hours, 1.0)
        self.assertEqual(attendance.coir_work_status, "returned")
        self.assertEqual(self._state("2026-11-16 17:01:00")["state"], "closed")

    def test_open_outing_only_accepts_its_return(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("work_exit", "2026-11-16 10:00:00")
        self.assertEqual(self._state("2026-11-16 10:01:00")["allowed_actions"], ["work_return"])
        for action in ("check_in", "work_exit", "meal_start", "meal_return", "check_out"):
            with self.assertRaises(UserError):
                self._act(action, "2026-11-16 10:01:00")
        self.assertFalse(attendance.check_out)
        self.assertFalse(attendance.coir_open_work_outing_id.end)
        self.assertEqual(attendance.coir_work_hours, 0.0)
        with self.assertRaises(UserError):
            attendance.sudo().write({"check_out": "2026-11-16 11:00:00"})
        self._act("work_return", "2026-11-16 11:00:00")
        self.assertFalse(attendance.coir_open_work_outing_id)

    def test_open_meal_cannot_overlap_outing_or_close_day(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        self.assertEqual(self._state("2026-11-16 12:01:00")["allowed_actions"], ["meal_return"])
        for action in ("work_exit", "work_return", "meal_start", "check_out"):
            with self.assertRaises(UserError):
                self._act(action, "2026-11-16 12:01:00")
        self.assertFalse(attendance.check_out)
        self.assertFalse(attendance.coir_meal_end)

    def test_new_entry_block_is_enforced_by_native_create_even_with_sudo(self):
        self._closed_day()
        for model in (self.env["hr.attendance"].with_user(self.officer), self.env["hr.attendance"].sudo()):
            with self.assertRaises(UserError):
                model.with_context(coir_write_token="fake", coir_allow_reentry=True).create({
                    "employee_id": self.employee.id, "check_in": "2026-11-16 18:00:00",
                })
            with self.assertRaises(UserError):
                model.create({
                    "employee_id": self.employee.id, "check_in": "2026-11-16 18:00:00",
                    "check_out": "2026-11-16 18:00:01", "in_mode": "technical", "out_mode": "technical",
                })

    def test_block_uses_effective_local_day_not_utc_midnight(self):
        self.calendar.tz = "America/Mexico_City"
        self._act("check_in", "2026-11-16 14:00:00")  # 08:00 local.
        self._act("check_out", "2026-11-16 23:00:00")  # 17:00 local.
        snapshot = self._state("2026-11-17 01:00:00")  # Still November 16 locally.
        self.assertEqual(snapshot["state"], "closed")
        self.assertEqual(snapshot["blocked_until"], "2026-11-17T06:00:00Z")
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-17 01:00:00")
        self._act("check_in", "2026-11-17 06:00:00")

    def test_default_employee_and_checkin_cannot_bypass_daily_guard(self):
        self._closed_day()
        with self.assertRaises(UserError):
            self.env["hr.attendance"].with_context(
                default_employee_id=self.employee.id, default_check_in="2026-11-16 18:00:00",
            ).create({})

    def test_default_context_cannot_forge_managed_policy_or_meal(self):
        with self.assertRaises(AccessError):
            self.env["hr.attendance"].sudo().with_context(
                default_employee_id=self.employee.id, default_check_in="2026-11-16 08:00:00",
                default_coir_managed=True, default_coir_meal_start="2026-11-16 12:00:00",
            ).create({})

    def test_overnight_open_stays_open_and_final_exit_blocks_its_local_day(self):
        self.calendar.tz = "America/Mexico_City"
        attendance = self._act("check_in", "2026-11-17 05:00:00")  # Nov 16 23:00 local.
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-17 07:00:00")
        self._act("work_exit", "2026-11-17 08:00:00")
        self._act("work_return", "2026-11-17 09:00:00")
        self._act("check_out", "2026-11-17 13:00:00")  # Nov 17 07:00 local.
        self.assertEqual(attendance.worked_hours, 8.0)
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-18 05:00:00")  # Nov 17 23:00 requires RH.
        self._grant("2026-11-17")
        self._act("check_in", "2026-11-18 05:00:00")

    def test_authorization_is_consumed_once_across_native_and_kiosk_channels(self):
        self._closed_day()
        authorization = self._grant()
        self.assertEqual(self._state("2026-11-16 18:00:00")["allowed_actions"], ["check_in"])
        extra = self.env["hr.attendance"].create({
            "employee_id": self.employee.id, "check_in": "2026-11-16 18:00:00", "check_out": "2026-11-16 19:00:00",
        })
        self.assertEqual(authorization.state, "used")
        self.assertEqual(authorization.consumed_attendance_id, extra)
        self.assertTrue(extra.message_ids)
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-16 20:00:00")
        with self.assertRaises(AccessError):
            authorization.write({"consumed_attendance_id": False})
        with self.assertRaises(UserError):
            authorization.action_revoke()

    def test_wrong_date_or_revoked_authorization_does_not_unlock(self):
        self._closed_day()
        self._grant("2026-11-17")
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-16 18:00:00")
        authorization = self._grant()
        authorization.action_revoke()
        self.assertEqual(authorization.state, "revoked")
        self.assertEqual(authorization.revoked_by, self.env.user)
        with self.assertRaises(UserError):
            self._act("check_in", "2026-11-16 18:00:00")

    def test_authorizations_require_manager_reason_and_server_audit(self):
        values = {"employee_id": self.employee.id, "valid_date": "2026-11-16", "reason": "Extra shift"}
        with self.assertRaises(AccessError):
            self.env["coir.reentry.authorization"].with_user(self.officer).create(values)
        with self.assertRaises(ValidationError):
            self.env["coir.reentry.authorization"].create({**values, "reason": "  "})
        with self.assertRaises(AccessError):
            self.env["coir.reentry.authorization"].create({**values, "authorized_by": self.officer.id})
        authorization = self._grant()
        self.assertEqual(authorization.authorized_by, self.env.user)
        self.assertEqual(authorization.company_id, self.company)
        with self.assertRaises(UserError):
            authorization.unlink()

    def test_revision_detects_stale_ticket_after_complete_outing_cycle(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        snapshot = self._state("2026-11-16 08:01:00")
        self._act("work_exit", "2026-11-16 09:00:00")
        self._act("work_return", "2026-11-16 10:00:00")
        self.assertEqual(self._state("2026-11-16 10:01:00")["state"], snapshot["state"])
        self.assertGreater(attendance.coir_revision, snapshot["revision"])
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime("2026-11-16 10:01:00")):
            with self.assertRaises(UserError):
                self.employee.sudo()._coir_apply_meal_action("meal_start", attendance.id, snapshot["state"], expected_revision=snapshot["revision"])

    def test_outing_correction_checks_overlap_and_keeps_audit(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self._act("work_exit", "2026-11-16 10:00:00")
        self._act("work_return", "2026-11-16 11:00:00")
        self._act("meal_start", "2026-11-16 12:00:00")
        self._act("meal_return", "2026-11-16 13:00:00")
        self._act("check_out", "2026-11-16 17:00:00")
        outing = attendance.coir_work_outing_ids
        before_messages = len(attendance.message_ids)
        wizard = self.env["coir.work.correction"].create({
            "outing_id": outing.id, "start": "2026-11-16 10:15:00", "end": "2026-11-16 11:15:00",
            "reason": "RH verificó los horarios reales.",
        })
        wizard.action_apply()
        self.assertEqual(outing.duration_hours, 1.0)
        self.assertEqual(attendance.worked_hours, 9.0)
        self.assertEqual(outing.review_note, wizard.reason)
        self.assertEqual(attendance.coir_review_note, wizard.reason)
        self.assertGreater(len(attendance.message_ids), before_messages)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            outing._coir_correct(fields.Datetime.to_datetime("2026-11-16 11:30:00"), fields.Datetime.to_datetime("2026-11-16 12:30:00"), "Overlap")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            attendance._coir_correct_meal(fields.Datetime.to_datetime("2026-11-16 10:30:00"), fields.Datetime.to_datetime("2026-11-16 13:00:00"), "Overlap")

    def test_outings_cannot_be_forged_reassigned_or_deleted(self):
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        with self.assertRaises(AccessError):
            self.env["coir.work.outing"].sudo().with_context(coir_write_token="fake").create({
                "attendance_id": attendance.id, "start": "2026-11-16 09:00:00",
            })
        self._act("work_exit", "2026-11-16 10:00:00")
        outing = attendance.coir_work_outing_ids
        with self.assertRaises(AccessError):
            attendance.with_user(self.officer).write({"coir_open_work_outing_id": False})
        with self.assertRaises(AccessError):
            outing.sudo().write({"end": "2026-11-16 11:00:00"})
        with self.assertRaises(UserError):
            outing.unlink()
        with self.assertRaises(UserError):
            attendance.unlink()

    def test_native_absence_placeholder_does_not_block_actual_first_entry(self):
        technical = self.env["hr.attendance"].create({
            "employee_id": self.employee.id, "check_in": "2026-11-16 00:00:00",
            "check_out": "2026-11-16 00:00:01", "in_mode": "technical", "out_mode": "technical",
        })
        self.assertFalse(technical.coir_managed)
        attendance = self._act("check_in", "2026-11-16 08:00:00")
        self.assertTrue(attendance.coir_managed)

    def test_batch_create_cannot_bypass_daily_block(self):
        rows = [
            {"employee_id": self.employee.id, "check_in": "2026-11-16 08:00:00", "check_out": "2026-11-16 12:00:00"},
            {"employee_id": self.employee.id, "check_in": "2026-11-16 13:00:00", "check_out": "2026-11-16 17:00:00"},
        ]
        for batch in (rows, list(reversed(rows))):
            with self.assertRaises(UserError), self.cr.savepoint():
                self.env["hr.attendance"].create(batch)

    def test_disabled_company_retains_native_multiple_intervals(self):
        self.company.coir_meal_control_enabled = False
        records = self.env["hr.attendance"].create([
            {"employee_id": self.employee.id, "check_in": "2026-11-16 08:00:00", "check_out": "2026-11-16 12:00:00"},
            {"employee_id": self.employee.id, "check_in": "2026-11-16 13:00:00", "check_out": "2026-11-16 17:00:00"},
        ])
        self.assertEqual(len(records), 2)
        self.assertFalse(any(records.mapped("coir_managed")))
