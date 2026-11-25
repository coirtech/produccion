"""Real ORM/SQL tests. They do not install or emulate Enterprise Gantt."""
from datetime import datetime

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirGanttProjection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"coir_meal_control_enabled": False, "auto_check_out": False})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Gantt real employee", "company_id": cls.company.id,
            "tz": "America/Mexico_City", "ruleset_id": False,
        })
        cls.absent_employee = cls.env["hr.employee"].create({
            "name": "Gantt absent employee", "company_id": cls.company.id,
            "tz": "America/Mexico_City", "ruleset_id": False,
        })
        cls.Attendance = cls.env["hr.attendance"]
        cls.Projection = cls.env["coir.attendance.gantt"]
        cls.real = cls.Attendance.create({
            "employee_id": cls.employee.id,
            "check_in": "2026-11-20 14:00:00", "check_out": "2026-11-20 22:00:00",
        })
        cls.absence = cls.env["coir.attendance.absence"]._service().create({
            "employee_id": cls.absent_employee.id, "company_id": cls.company.id,
            "date": "2026-11-23", "timezone": "America/Mexico_City",
            "generated_at": "2026-11-23 15:00:00",
            "start_datetime": "2026-11-23 14:00:00", "end_datetime": "2026-11-23 23:00:00",
            "state": "absent",
        })
        cls.reader = new_test_user(
            cls.env, login="coir_gantt_all_reader", company_id=cls.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_user",
        )
        cls.officer = new_test_user(
            cls.env, login="coir_gantt_assigned_officer", company_id=cls.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_officer",
        )

    def test_union_changes_no_attendance_rows_and_uses_zero_work_hours(self):
        actual_before = self.Attendance.search_count([])
        visual = self.Projection.browse(-self.absence.id)
        self.assertEqual(visual.employee_id, self.absent_employee)
        self.assertEqual(visual.coir_absence_id, self.absence)
        self.assertEqual(visual.display_name, "FALTA")
        self.assertEqual(visual.color, 1)
        self.assertEqual(visual.worked_hours, 0.0)
        self.assertEqual(visual.expected_hours, 0.0)
        self.assertEqual(visual.overtime_hours, 0.0)
        self.assertEqual(visual.validated_overtime_hours, 0.0)
        self.assertFalse(visual.linked_overtime_ids)
        self.assertFalse(visual.is_manager)
        self.assertEqual(visual._get_worked_hours_in_range(visual.check_in, visual.check_out), 0.0)
        self.assertEqual(self.Attendance.search_count([]), actual_before)
        self.assertFalse(self.Attendance.search([("id", "<", 0)]))
        self.assertFalse(self.Attendance.search([("employee_id", "=", self.absent_employee.id)]))

    def test_real_values_label_and_color_remain_native(self):
        source_fields = ["employee_id", "date", "check_in", "check_out", "worked_hours",
                         "expected_hours", "overtime_hours", "display_name", "color"]
        visual = self.Projection.browse(self.real.id)
        self.assertEqual(self.real.read(source_fields), visual.read(source_fields))
        opened = self.Attendance.create({
            "employee_id": self.employee.id, "check_in": fields.Datetime.now(),
        })
        projected_open = self.Projection.browse(opened.id)
        self.assertEqual(opened.display_name, projected_open.display_name)
        self.assertEqual(opened.color, projected_open.color)
        self.assertFalse(projected_open.check_out)

    def test_resolving_absence_removes_virtual_row_only(self):
        self.assertTrue(self.Projection.search([("id", "=", -self.absence.id)]))
        self.absence._set_state("resolved", datetime(2026, 11, 23, 16, 30))
        self.Projection.invalidate_model()
        self.assertFalse(self.Projection.search([("id", "=", -self.absence.id)]))
        self.assertTrue(self.absence.exists())
        self.assertTrue(self.Projection.search([("id", "=", self.real.id)]))

    def test_projection_is_not_mutable_even_under_sudo(self):
        visual = self.Projection.browse(-self.absence.id)
        with self.assertRaises(UserError):
            visual.write({"check_out": "2026-11-23 18:00:00"})
        with self.assertRaises(UserError):
            visual.unlink()
        with self.assertRaises(UserError):
            self.Projection.create({"employee_id": self.employee.id})
        with self.assertRaises(UserError):
            self.Projection.browse(self.real.id).action_approve_overtime()

    def test_original_record_rules_are_enforced_on_both_sources(self):
        projection = self.Projection.with_user(self.reader)
        domain = [("id", "in", [self.real.id, -self.absence.id])]
        self.assertEqual(set(projection.search(domain).ids), {self.real.id, -self.absence.id})
        self.env["ir.rule"].create({
            "name": "Test extra restriction of original attendance",
            "model_id": self.env["ir.model"]._get_id("hr.attendance"),
            "domain_force": "[('id', '!=', %s)]" % self.real.id,
        })
        self.assertEqual(projection.search(domain).ids, [-self.absence.id])
        self.env["ir.rule"].create({
            "name": "Test extra restriction of original absence",
            "model_id": self.env["ir.model"]._get_id("coir.attendance.absence"),
            "domain_force": "[('id', '!=', %s)]" % self.absence.id,
        })
        self.assertFalse(projection.search(domain))
        with self.assertRaises(AccessError):
            projection.browse(-self.absence.id).read(["employee_id", "worked_hours"])

    def test_officer_does_not_gain_access_to_unassigned_employees(self):
        projection = self.Projection.with_user(self.officer)
        domain = [("id", "in", [self.real.id, -self.absence.id])]
        self.assertFalse(projection.search(domain))
        with self.assertRaises(AccessError):
            projection.browse(self.real.id).read(["employee_id", "worked_hours"])
        self.absent_employee.attendance_manager_id = self.officer
        self.assertEqual(projection.search(domain).ids, [-self.absence.id])

    def test_projection_stored_fields_do_not_schedule_recomputation(self):
        field_names = ["date", "worked_hours", "overtime_hours", "expected_hours",
                       "validated_overtime_hours", "coir_company_id", "coir_meal_hours",
                       "coir_meal_status", "coir_work_hours", "coir_work_status"]
        for name in field_names:
            self.assertFalse(self.Projection._fields[name].compute, name)
        self.Projection.browse(self.real.id).read(field_names)
        self.employee.name = "Gantt renamed employee"
        self.env.flush_all()
        self.Projection.invalidate_model()
        self.assertEqual(self.Projection.browse(self.real.id).worked_hours, self.real.worked_hours)

    def test_original_and_absence_form_actions_use_actual_models(self):
        actual_action = self.Projection.browse(self.real.id).get_formview_action()
        absent_action = self.Projection.browse(-self.absence.id).get_formview_action()
        self.assertEqual(actual_action["res_model"], "hr.attendance")
        self.assertEqual(actual_action["res_id"], self.real.id)
        self.assertEqual(absent_action["res_model"], "coir.attendance.absence")
        self.assertEqual(absent_action["res_id"], self.absence.id)

    def test_attendance_roles_can_read_without_inherited_own_reader(self):
        """Regression: native attendance access must also open its projection.

        Some installations customize the internal-user implied groups.  Drop
        only that implication in this transaction to reproduce the reported
        projection ACL failure while native attendance remains authorized.
        """
        own_reader = self.env.ref("hr_attendance.group_hr_attendance_own_reader")
        self.env.ref("base.group_user").write({
            "implied_ids": [Command.unlink(own_reader.id)],
        })
        expected_ids = {self.real.id, -self.absence.id}
        for role in ("officer", "user", "manager"):
            with self.subTest(role=role):
                user = new_test_user(
                    self.env, login="coir_gantt_without_own_" + role,
                    company_id=self.company.id,
                    groups="base.group_user,hr_attendance.group_hr_attendance_" + role,
                )
                self.assertFalse(user.has_group("hr_attendance.group_hr_attendance_own_reader"))
                (self.employee | self.absent_employee).attendance_manager_id = user
                self.assertTrue(self.Attendance.with_user(user).has_access("read"))
                projection = self.Projection.with_user(user)
                projection.check_access("read")
                visible = projection.search([("id", "in", list(expected_ids))])
                self.assertEqual(set(visible.ids), expected_ids)
                self.assertEqual(len(visible.read(["check_in", "check_out", "worked_hours"])), 2)
                for operation in ("create", "write", "unlink"):
                    self.assertFalse(projection.has_access(operation))

    def test_own_reader_sees_only_own_real_records(self):
        user = new_test_user(
            self.env, login="coir_gantt_own_only", company_id=self.company.id,
            groups="base.group_user,hr_attendance.group_hr_attendance_own_reader",
        )
        self.employee.user_id = user
        projection = self.Projection.with_user(user)
        self.assertEqual(
            projection.search([("id", "in", [self.real.id, -self.absence.id])]).ids,
            [self.real.id],
        )
        # Warm the shared cache before proving that direct reads are still
        # checked against the original absence model under the restricted user.
        self.Projection.browse(-self.absence.id).read(["check_in", "worked_hours"])
        with self.assertRaises(AccessError):
            projection.browse(-self.absence.id).read(["check_in", "worked_hours"])

    def test_projection_acl_does_not_open_portal_access(self):
        portal = new_test_user(
            self.env, login="coir_gantt_portal", company_id=self.company.id,
            groups="base.group_portal",
        )
        projection = self.Projection.with_user(portal)
        self.assertFalse(projection.has_access("read"))
        with self.assertRaises(AccessError):
            projection.search([("id", "=", self.real.id)])

    def test_all_attendance_reader_remains_limited_to_selected_companies(self):
        other_company = self.env["res.company"].create({"name": "Gantt second company"})
        other_employee = self.env["hr.employee"].create({
            "name": "Gantt other-company employee", "company_id": other_company.id,
            "tz": "America/Mexico_City", "ruleset_id": False,
        })
        other_attendance = self.Attendance.create({
            "employee_id": other_employee.id,
            "check_in": "2026-11-20 14:00:00", "check_out": "2026-11-20 22:00:00",
        })
        other_absence = self.env["coir.attendance.absence"]._service().create({
            "employee_id": other_employee.id, "company_id": other_company.id,
            "date": "2026-11-23", "timezone": "America/Mexico_City",
            "generated_at": "2026-11-23 15:00:00",
            "start_datetime": "2026-11-23 14:00:00", "end_datetime": "2026-11-23 23:00:00",
            "state": "absent",
        })
        self.reader.write({"company_ids": [Command.link(other_company.id)]})
        projection = self.Projection.with_user(self.reader).with_context(
            allowed_company_ids=[self.company.id],
        )
        first_company_ids = {self.real.id, -self.absence.id}
        second_company_ids = {other_attendance.id, -other_absence.id}
        domain = [("id", "in", list(first_company_ids | second_company_ids))]
        self.assertEqual(set(projection.search(domain).ids), first_company_ids)
        for record_id in second_company_ids:
            with self.assertRaises(AccessError):
                projection.browse(record_id).read(["check_in", "worked_hours"])
        self.assertEqual(
            set(projection.with_context(
                allowed_company_ids=[self.company.id, other_company.id],
            ).search(domain).ids),
            first_company_ids | second_company_ids,
        )
