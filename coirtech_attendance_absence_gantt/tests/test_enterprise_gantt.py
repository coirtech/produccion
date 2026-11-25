"""Acceptance checks for an actual Odoo 19 Enterprise installation only."""
import json

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoirEnterpriseGantt(TransactionCase):
    def test_native_gantt_pipeline_accepts_projection(self):
        stored_computations = [
            name for name, field in self.env["coir.attendance.gantt"]._fields.items()
            if field.store and field.compute
        ]
        self.assertFalse(
            stored_computations,
            "Una extensión instalada añadió campos almacenados calculados: "
            "deben declararse como columnas de solo lectura en la proyección.",
        )
        employee = self.env["hr.employee"].create({
            "name": "Enterprise absence indicator", "company_id": self.env.company.id,
            "tz": "America/Mexico_City", "ruleset_id": False,
        })
        absence = self.env["coir.attendance.absence"]._service().create({
            "employee_id": employee.id, "company_id": employee.company_id.id,
            "date": "2026-11-23", "timezone": "America/Mexico_City",
            "generated_at": "2026-11-23 15:00:00",
            "start_datetime": "2026-11-23 14:00:00", "end_datetime": "2026-11-23 23:00:00",
            "state": "absent",
        })
        request_args = (
            [("employee_id", "=", employee.id)],
            ["employee_id"],
            {
                "employee_id": {"fields": {"display_name": {}}},
                "check_in": {}, "check_out": {}, "display_name": {},
                "worked_hours": {}, "color": {},
            },
        )
        request_kwargs = {
            "start_date": "2026-11-23 00:00:00", "stop_date": "2026-11-24 00:00:00",
            "scale": "day", "unavailability_fields": [], "progress_bar_fields": [],
        }
        response = self.env["hr.attendance"].get_gantt_data(*request_args, **request_kwargs)
        # The schema itself belongs to the installed Enterprise implementation.
        # Only assert the intended observable data, not an invented group schema.
        self.assertIsInstance(response, dict)
        self.assertIn("FALTA", json.dumps(response, default=str))
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", employee.id)]))

        # Exercise the actual Enterprise RPC pipeline as each native attendance
        # role, even when internal users no longer imply the own-reader group.
        # This deliberately uses no sudo to mask projection ACL failures.
        own_reader = self.env.ref("hr_attendance.group_hr_attendance_own_reader")
        self.env.ref("base.group_user").write({
            "implied_ids": [Command.unlink(own_reader.id)],
        })
        for role in ("officer", "user", "manager"):
            with self.subTest(role=role):
                user = new_test_user(
                    self.env, login="coir_enterprise_gantt_" + role,
                    company_id=employee.company_id.id,
                    groups="base.group_user,hr_attendance.group_hr_attendance_" + role,
                )
                self.assertFalse(user.has_group("hr_attendance.group_hr_attendance_own_reader"))
                employee.attendance_manager_id = user
                response = self.env["hr.attendance"].with_user(user).get_gantt_data(
                    *request_args, **request_kwargs,
                )
                self.assertIsInstance(response, dict)
                self.assertIn("FALTA", json.dumps(response, default=str))

        with self.assertRaises(UserError):
            self.env["hr.attendance"].browse(-absence.id).web_read({"check_in": {}, "check_out": {}})
