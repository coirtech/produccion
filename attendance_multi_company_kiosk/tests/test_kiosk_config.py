from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMultiCompanyKioskConfiguration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.companies = cls.env["res.company"].create([
            {"name": "Shared kiosk company %s" % index,
             "coir_meal_control_enabled": True, "auto_check_out": False}
            for index in range(1, 5)
        ])
        cls.manager = new_test_user(
            cls.env, login="multi_kiosk_manager", groups="base.group_user,hr_attendance.group_hr_attendance_manager",
            company_id=cls.companies[0].id, company_ids=[Command.set(cls.companies.ids)],
        )
        cls.officer = new_test_user(
            cls.env, login="multi_kiosk_officer", groups="base.group_user,hr_attendance.group_hr_attendance_user",
            company_id=cls.companies[0].id, company_ids=[Command.set(cls.companies.ids)],
        )
        cls.Kiosk = cls.env["attendance.multi.company.kiosk"].with_user(cls.manager).with_context(
            allowed_company_ids=cls.companies.ids,
        )

    def _kiosk(self, companies=None, **extra):
        values = {"name": "Control de asistencia", "company_ids": [Command.set((companies or self.companies[:3]).ids)]}
        values.update(extra)
        return self.Kiosk.create(values)

    def test_companies_can_be_added_removed_with_same_url_and_history(self):
        kiosk = self._kiosk()
        token, url, revision = kiosk.access_token, kiosk.kiosk_url, kiosk.config_revision
        company = self.companies[1]
        employee = self.env["hr.employee"].with_company(company).create({"name": "Historical employee", "company_id": company.id})
        attendance = self.env["hr.attendance"].with_company(company).create({
            "employee_id": employee.id, "check_in": "2026-11-16 08:00:00", "check_out": "2026-11-16 17:00:00",
        })
        before = (attendance.check_in, attendance.check_out, attendance.worked_hours, attendance.employee_id.id)
        kiosk.write({"company_ids": [Command.link(self.companies[3].id)]})
        self.assertEqual(kiosk.company_ids, self.companies)
        self.assertGreater(kiosk.config_revision, revision)
        revision = kiosk.config_revision
        kiosk.write({"company_ids": [Command.unlink(company.id)]})
        self.assertNotIn(company, kiosk.company_ids)
        self.assertGreater(kiosk.config_revision, revision)
        self.assertEqual(kiosk.access_token, token)
        self.assertEqual(kiosk.kiosk_url, url)
        attendance.invalidate_recordset()
        self.assertTrue(attendance.exists())
        self.assertEqual((attendance.check_in, attendance.check_out, attendance.worked_hours, attendance.employee_id.id), before)

    def test_active_kiosk_needs_enabled_participant_and_can_be_deactivated(self):
        with self.assertRaises(ValidationError):
            self.Kiosk.create({"company_ids": [Command.clear()]})
        self.companies[3].write({"coir_meal_control_enabled": False})
        with self.assertRaises(ValidationError):
            self._kiosk(self.companies[3])
        kiosk = self._kiosk()
        revision = kiosk.config_revision
        kiosk.write({"active": False, "company_ids": [Command.clear()]})
        self.assertFalse(kiosk.active)
        self.assertFalse(kiosk.company_ids)
        self.assertGreater(kiosk.config_revision, revision)
        with self.assertRaises(UserError):
            kiosk.action_open_kiosk()
        with self.assertRaises(ValidationError):
            kiosk.write({"active": True})

    def test_only_managers_can_configure_or_read_tokens(self):
        kiosk = self._kiosk()
        officer_model = self.Kiosk.with_user(self.officer)
        with self.assertRaises(AccessError):
            officer_model.create({"company_ids": [Command.set(self.companies[:1].ids)]})
        with self.assertRaises(AccessError):
            officer_model.browse(kiosk.id).read(["name", "access_token"])
        with self.assertRaises(AccessError):
            officer_model.browse(kiosk.id).write({"name": "Edited"})
        with self.assertRaises(AccessError):
            officer_model.browse(kiosk.id).action_regenerate_token()
        with self.assertRaises(AccessError):
            self.Kiosk.with_user(self.env.ref("base.public_user")).browse(kiosk.id).read(["access_token"])

    def test_company_rule_requires_every_participant_in_active_context(self):
        kiosk = self._kiosk(self.companies[:2])
        only_first = self.Kiosk.with_context(allowed_company_ids=self.companies[:1].ids)
        self.assertNotIn(kiosk.id, only_first.search([]).ids)
        with self.assertRaises(AccessError):
            only_first.browse(kiosk.id).read(["access_token"])
        with self.assertRaises(AccessError):
            only_first.browse(kiosk.id).action_regenerate_token()
        self.assertEqual(self.Kiosk.browse(kiosk.id).read(["name"])[0]["name"], "Control de asistencia")
        with self.assertRaises(AccessError):
            only_first.create({"company_ids": [Command.set(self.companies[:2].ids)]})

    def test_company_commands_cannot_create_modify_or_delete_company(self):
        kiosk = self._kiosk()
        for command in (
            Command.create({"name": "Unexpected company"}),
            Command.update(self.companies[0].id, {"name": "Unexpected rename"}),
            Command.delete(self.companies[0].id),
        ):
            with self.assertRaises(AccessError):
                kiosk.write({"company_ids": [command]})
        self.assertEqual(self.companies[0].name, "Shared kiosk company 1")
        self.assertTrue(self.companies[0].exists())

    def test_server_owns_tokens_revision_and_copy_gets_another_token(self):
        for values in ({"access_token": "forged"}, {"config_revision": 5000}):
            with self.assertRaises(AccessError):
                self._kiosk(**values)
        kiosk = self.Kiosk.with_context(default_access_token="forged", default_config_revision=5000).create({
            "company_ids": [Command.set(self.companies[:3].ids)],
        })
        self.assertNotEqual(kiosk.access_token, "forged")
        self.assertEqual(kiosk.config_revision, 1)
        self.assertGreaterEqual(len(kiosk.access_token), 40)
        for values in ({"access_token": "forged"}, {"config_revision": 0}):
            with self.assertRaises(AccessError):
                kiosk.write(values)
        duplicate = kiosk.copy()
        self.assertNotEqual(duplicate.access_token, kiosk.access_token)
        self.assertEqual(duplicate.config_revision, 1)
        self.assertEqual(duplicate.company_ids, kiosk.company_ids)

    def test_membership_defaults_do_not_bypass_access_check(self):
        model = self.Kiosk.with_context(
            allowed_company_ids=self.companies[:1].ids,
            default_company_ids=[Command.set(self.companies[1:2].ids)],
        )
        with self.assertRaises(AccessError):
            model.create({"name": "Injected defaults"})

    def test_rotation_invalidates_link_and_lock_does_not_change_revision(self):
        kiosk = self._kiosk()
        token, revision = kiosk.access_token, kiosk.config_revision
        kiosk.sudo()._lock_for_action()
        self.assertEqual(kiosk.config_revision, revision)
        kiosk.action_regenerate_token()
        self.assertNotEqual(kiosk.access_token, token)
        self.assertEqual(kiosk.config_revision, revision + 1)
        self.assertNotIn(token, kiosk.kiosk_url)
        self.assertEqual(kiosk.action_open_kiosk()["url"], kiosk.kiosk_url)
        with self.assertRaises(UserError):
            kiosk.unlink()

    def test_administration_form_can_create_without_server_fields(self):
        with Form(self.Kiosk, view="attendance_multi_company_kiosk.kiosk_form_view") as form:
            form.name = "Nuevo quiosco"
            form.company_ids.add(self.companies[1])
        kiosk = form.record
        self.assertTrue(kiosk.access_token)
        self.assertEqual(kiosk.config_revision, 1)
        self.assertEqual(set(kiosk.company_ids.ids), set(self.companies[:2].ids))
        self.assertEqual(kiosk.barcode_source, "company")

    def test_default_scan_source_follows_first_eligible_company(self):
        self.companies[0].attendance_barcode_source = "back"
        self.companies[1].attendance_barcode_source = "scanner"
        self.companies[2].attendance_barcode_source = "front"
        kiosk = self._kiosk()
        self.assertEqual(kiosk.barcode_source, "company")
        self.assertEqual(kiosk._get_barcode_source(), "back")
        # The inherited setting stays live, as in an individual company kiosk.
        self.companies[0].attendance_barcode_source = "front"
        self.assertEqual(kiosk._get_barcode_source(), "front")
        self.companies[0].coir_meal_control_enabled = False
        self.assertEqual(kiosk._get_barcode_source(), "scanner")
        self.companies[1].active = False
        self.assertEqual(kiosk._get_barcode_source(), "front")

    def test_scan_source_override_preserves_link_membership_and_mode(self):
        kiosk = self._kiosk(identification_mode="barcode")
        token, url = kiosk.access_token, kiosk.kiosk_url
        participants = kiosk.company_ids
        self.companies.write({"attendance_barcode_source": "back"})
        for source in ("scanner", "front", "back", "company"):
            revision = kiosk.config_revision
            kiosk.write({"barcode_source": source})
            self.assertEqual(kiosk.config_revision, revision + 1)
            self.assertEqual(kiosk._get_barcode_source(), "back" if source == "company" else source)
            self.assertEqual(kiosk.access_token, token)
            self.assertEqual(kiosk.kiosk_url, url)
            self.assertEqual(kiosk.company_ids, participants)
            self.assertEqual(kiosk.identification_mode, "barcode")

    def test_inherited_scan_source_with_no_eligible_company_has_native_default(self):
        kiosk = self.Kiosk.create({"name": "Inactivo", "active": False, "company_ids": [Command.clear()]})
        self.assertEqual(kiosk._get_barcode_source(), "front")
        kiosk.write({"company_ids": [Command.set(self.companies[:1].ids)]})
        self.companies[0].write({"coir_meal_control_enabled": False, "auto_check_out": True})
        self.assertEqual(kiosk._get_barcode_source(), "front")
