"""Exercise the actual export wizard entry point for shared column settings."""
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV42LayoutWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other = cls.env['res.company'].create({'name': 'V4.2 wizard second company'})
        cls.env.user.company_ids = [Command.link(cls.other.id)]
        cls.context = {'allowed_company_ids': (cls.company | cls.other).ids}
        cls.Wizard = cls.env['coir.attendance.report.wizard'].with_context(**cls.context)
        cls.officer = new_test_user(
            cls.env, login='coir_v42_columns_officer', company_id=cls.company.id,
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )

    def _wizard(self, companies=None):
        return self.Wizard.create({
            'date_from': '2026-11-16', 'date_to': '2026-11-16',
            'company_ids': [Command.set((companies or self.company).ids)],
        })

    def test_editor_opens_selected_company_and_format_and_reuses_saved_layout(self):
        wizard = self._wizard(self.company | self.other)
        wizard.write({'layout_company_id': self.other.id, 'layout_output_format': 'pdf'})
        action = wizard.action_customize_columns()
        self.assertEqual(action['res_model'], 'coir.attendance.report.layout')
        self.assertEqual(action['target'], 'new')
        layout = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(layout.company_id, self.other)
        self.assertEqual(layout.output_format, 'pdf')
        line = layout.summary_line_ids.filtered(lambda row: row.column_key == 'employee_name')
        line.label = 'Colaborador'
        self.assertEqual(wizard.action_customize_columns()['res_id'], layout.id)
        self.assertEqual(line.label, 'Colaborador')

    def test_company_selection_recomputes_editor_company_and_rejects_outside_selection(self):
        wizard = self._wizard(self.other)
        self.assertEqual(wizard.layout_company_id, self.other)
        wizard.company_ids = [Command.set(self.company.ids)]
        self.assertEqual(wizard.layout_company_id, self.company)
        wizard.layout_company_id = self.other
        with self.assertRaises(ValidationError):
            wizard.action_customize_columns()

    def test_export_officer_cannot_change_shared_columns_through_wizard(self):
        wizard = self.Wizard.with_user(self.officer).with_context(
            allowed_company_ids=self.company.ids,
        ).create({
            'date_from': '2026-11-16', 'date_to': '2026-11-16',
            'company_ids': [Command.set(self.company.ids)],
        })
        with self.assertRaises(AccessError):
            wizard.action_customize_columns()
