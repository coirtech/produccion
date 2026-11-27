"""V4.3: public employee reads stay usable without private HR permissions."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirV43EmployeePermissions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            "auto_check_out": False,
            "coir_meal_control_enabled": True,
            "coir_absence_enabled": False,
        })
        cls.section = cls.env["coir.meal.section"].create({
            "name": "V4.3 section retained", "company_id": cls.company.id,
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "V4.3 employee public profile",
            "company_id": cls.company.id,
            "coir_meal_section_id": cls.section.id,
            "private_phone": "PRIVATE-HR-ONLY",
            "tz": "UTC", "ruleset_id": False,
        })
        # The addon does not depend on Manufacturing. When present in the
        # integration database, exercise the exact combined role that failed.
        manufacturing = ",mrp.group_mrp_user" if cls.env.ref(
            "mrp.group_mrp_user", raise_if_not_found=False,
        ) else ""
        cls.internal = new_test_user(
            cls.env, login="coir_v43_internal",
            groups="base.group_user" + manufacturing,
            company_id=cls.company.id,
        )
        cls.officer = new_test_user(
            cls.env, login="coir_v43_attendance_officer",
            groups="base.group_user,hr_attendance.group_hr_attendance_user" + manufacturing,
            company_id=cls.company.id,
        )
        cls.attendance_manager = new_test_user(
            cls.env, login="coir_v43_attendance_manager",
            groups="base.group_user,hr_attendance.group_hr_attendance_manager" + manufacturing,
            company_id=cls.company.id,
        )
        cls.hr_user = new_test_user(
            cls.env, login="coir_v43_hr_user",
            groups="base.group_user,hr.group_hr_user",
            company_id=cls.company.id,
        )

    def test_native_employee_prefetch_without_private_hr_access(self):
        """A name/company read must not fetch a private section into public HR."""
        for user in self.internal | self.officer | self.attendance_manager:
            with self.subTest(user=user.login):
                employees = self.env["hr.employee"].with_user(user)
                self.assertFalse(user.has_group("hr.group_hr_user"))
                self.assertFalse(employees.has_access("read"))
                # No sudo-populated cache may mask the actual fallback path.
                self.env.invalidate_all()
                public_fallback = employees.search_fetch([
                    ("id", "=", self.employee.id),
                ])
                self.assertEqual(public_fallback.ids, self.employee.ids)
                self.assertEqual(public_fallback.name, "V4.3 employee public profile")
                self.assertEqual(public_fallback.company_id.id, self.company.id)
                self.assertFalse(public_fallback.coir_attendance_report_excluded)
                self.employee.invalidate_recordset()
                self.assertEqual(employees.browse(self.employee.id).name,
                                 "V4.3 employee public profile")

    def test_public_roles_keep_private_fields_restricted(self):
        for user in self.internal | self.officer | self.attendance_manager:
            with self.subTest(user=user.login):
                employee = self.employee.with_user(user)
                self.assertNotIn("coir_meal_section_id", employee.fields_get())
                self.env.invalidate_all()
                with self.assertRaises(AccessError):
                    employee.read(["private_phone"])
                with self.assertRaises(AccessError):
                    employee.read(["coir_meal_section_id"])
                self.assertFalse(employee.has_access("write"))

    def test_hr_edit_and_kiosk_section_snapshot_still_work(self):
        replacement = self.env["coir.meal.section"].create({
            "name": "V4.3 replacement section", "company_id": self.company.id,
        })
        self.employee.with_user(self.hr_user).write({"coir_meal_section_id": replacement.id})
        self.assertEqual(self.employee.coir_meal_section_id, replacement)
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.to_datetime(
                "2026-11-16 08:00:00")):
            employee = self.employee.sudo()
            current = employee._coir_meal_state()
            self.assertEqual(current["section_name"], replacement.name)
            attendance = employee._coir_apply_meal_action(
                "check_in", current["attendance_id"], current["state"],
                expected_revision=current["revision"],
            )
        self.employee.with_user(self.hr_user).write({"coir_meal_section_id": self.section.id})
        self.assertEqual(attendance.coir_section_id, replacement)
        self.assertEqual(attendance.with_user(self.officer).coir_section_name, replacement.name)
        self.assertEqual(self.employee.coir_meal_section_id, self.section)
