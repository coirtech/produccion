"""V4.2: persisted layouts are isolated, safe and presentation-only."""
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV42Layouts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].create({'name': 'COIRTECH V4.2 other layout company'})
        cls.layout_model = cls.env['coir.attendance.report.layout']
        cls.manager = new_test_user(
            cls.env, login='coir_v42_layout_manager',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )
        cls.officer = new_test_user(
            cls.env, login='coir_v42_layout_officer',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )
        cls.employee_user = new_test_user(
            cls.env, login='coir_v42_layout_employee', groups='base.group_user',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )

    def _layout(self, output_format='xlsx', company=None):
        company = company or self.company
        return self.layout_model.with_context(allowed_company_ids=(self.company | company).ids).create({
            'company_id': company.id, 'output_format': output_format,
        })

    def _line(self, layout, key, section='summary'):
        return layout.line_ids.filtered(lambda line: line.column_key == key and line.section == section)

    def test_default_read_does_not_create_layout_and_preserves_excel_column_positions(self):
        model = self.layout_model.with_user(self.officer)
        before = model.search_count([])
        summary = model._coir_get_columns(self.company, 'xlsx', 'summary')
        detail = model._coir_get_columns(self.company, 'xlsx', 'detail')
        self.assertEqual(len(summary), 21)
        self.assertEqual(len(detail), 18)
        self.assertEqual(summary[5]['key'], 'first_entry')
        self.assertEqual(summary[17]['key'], 'notice_label')
        self.assertEqual(summary[19]['key'], 'leave_seconds')
        self.assertEqual(detail[10]['key'], 'interval_seconds')
        self.assertEqual(model.search_count([]), before)
        pdf = model._coir_get_columns(self.company, 'pdf', 'detail')
        self.assertEqual([item['key'] for item in pdf], [
            'employee_name', 'date', 'label', 'local_stamp', 'reference',
            'interval_seconds', 'journey_seconds', 'interval_state',
        ])

    def test_open_editor_once_seeds_complete_catalogue_and_reuses_company_format(self):
        model = self.layout_model.with_user(self.manager)
        first = model._coir_open_editor(self.company, 'xlsx')
        second = model._coir_open_editor(self.company, 'xlsx')
        self.assertEqual(first['res_id'], second['res_id'])
        self.assertEqual(first['target'], 'new')
        layout = model.browse(first['res_id'])
        self.assertEqual(len(layout.summary_line_ids), 32)
        self.assertEqual(len(layout.detail_line_ids), 20)
        self.assertEqual(len(layout.summary_line_ids.filtered('visible')), 21)
        self.assertEqual(len(layout.detail_line_ids.filtered('visible')), 18)

    def test_order_visibility_and_trimmed_header_persist_without_changing_other_format(self):
        layout = self._layout().with_user(self.manager)
        self._line(layout, 'employee_name').write({'sequence': -10, 'label': '  Colaborador  '})
        self._line(layout, 'company_name').visible = False
        self._line(layout, 'overtime_seconds').write({'visible': True, 'sequence': -5})
        columns = self.layout_model.with_user(self.officer)._coir_get_columns(self.company, 'xlsx', 'summary')
        self.assertEqual(columns[0]['key'], 'employee_name')
        self.assertEqual(columns[0]['label'], 'Colaborador')
        self.assertEqual(columns[1]['key'], 'overtime_seconds')
        self.assertNotIn('company_name', [column['key'] for column in columns])
        pdf = self.layout_model._coir_get_columns(self.company, 'pdf', 'summary')
        self.assertEqual(pdf[0]['key'], 'date')
        self.assertEqual(pdf[1]['label'], 'Empleado')

    def test_copy_to_other_format_and_restore_only_target(self):
        layout = self._layout()
        self._line(layout, 'employee_name').write({'sequence': -10, 'label': 'Colaborador'})
        self._line(layout, 'company_name').visible = False
        self._line(layout, 'review_reason', 'detail').visible = False
        before = self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary')
        layout.with_user(self.manager).action_apply_to_other_format()
        self.assertEqual(before, self.layout_model._coir_get_columns(self.company, 'pdf', 'summary'))
        target = self.layout_model.search([('company_id', '=', self.company.id), ('output_format', '=', 'pdf')])
        self.assertFalse(self._line(target, 'review_reason', 'detail').visible)
        target.with_user(self.manager).action_reset_defaults()
        self.assertEqual(before, self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary'))
        self.assertEqual(self.layout_model._coir_get_columns(self.company, 'pdf', 'summary')[0]['key'], 'date')
        self.assertEqual(len(self.layout_model._coir_get_columns(self.company, 'pdf', 'summary')), 10)

    def test_hiding_last_column_rejected_but_atomic_replacement_allowed(self):
        layout = self._layout()
        keep = self._line(layout, 'employee_name')
        layout.write({'line_ids': [
            Command.update(line.id, {'visible': line == keep}) for line in layout.summary_line_ids
        ]})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            keep.visible = False
        replacement = self._line(layout, 'date')
        # Order deliberately hides the old last column before enabling the new
        # one; validating an intermediate child command would reject this.
        layout.write({'line_ids': [
            Command.update(keep.id, {'visible': False}),
            Command.update(replacement.id, {'visible': True}),
        ]})
        columns = self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary')
        self.assertEqual([column['key'] for column in columns], ['date'])
        self.assertTrue(layout.detail_line_ids.filtered('visible'))

    def test_empty_or_overlong_headers_rejected_and_markup_kept_as_literal_text(self):
        line = self._line(self._layout(), 'employee_name')
        for label in ('   ', False, 'x' * 81):
            with self.subTest(label=label), self.assertRaises(ValidationError), self.env.cr.savepoint():
                line.write({'label': label})
        line.label = '<b>Personal</b> =1+1'
        columns = self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary')
        self.assertEqual(next(column['label'] for column in columns if column['key'] == 'employee_name'), '<b>Personal</b> =1+1')

    def test_officer_can_read_layout_but_cannot_edit_create_reset_or_copy(self):
        layout = self._layout()
        officer_model = self.layout_model.with_user(self.officer)
        self.assertTrue(officer_model._coir_get_columns(self.company, 'xlsx', 'summary'))
        actions = (
            lambda: officer_model._coir_open_editor(self.company, 'pdf'),
            lambda: officer_model.create({'company_id': self.company.id, 'output_format': 'pdf'}),
            lambda: self._line(layout.with_user(self.officer), 'employee_name').write({'label': 'Denied'}),
            lambda: layout.with_user(self.officer).action_reset_defaults(),
            lambda: layout.with_user(self.officer).action_apply_to_other_format(),
        )
        for action in actions:
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                action()
        with self.assertRaises(AccessError):
            self.layout_model.with_user(self.employee_user)._coir_get_columns(self.company, 'xlsx', 'summary')

    def test_company_isolation_known_ids_and_disabled_company(self):
        local = self._layout()
        other = self._layout(company=self.other_company)
        self._line(other, 'employee_name').label = 'Other company only'
        model = self.layout_model.with_user(self.manager).with_context(allowed_company_ids=self.company.ids)
        self.assertEqual(model.search([]), local.with_env(model.env))
        with self.assertRaises(AccessError):
            model._coir_get_columns(self.other_company, 'xlsx', 'summary')
        with self.assertRaises(AccessError):
            model.browse(other.id).read(['line_ids'])
        with self.assertRaises(AccessError):
            self._line(other, 'employee_name').with_user(self.manager).read(['label'])
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            model.create({'company_id': self.other_company.id, 'output_format': 'pdf'})

    def test_forged_context_and_column_identity_changes_cannot_escape_catalogue(self):
        layout = self._layout()
        line = self._line(layout, 'employee_name')
        model = self.env['coir.attendance.report.layout.line'].with_context(_coir_report_layout_mutation=True)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            model.create({'layout_id': layout.id, 'section': 'summary', 'column_key': 'employee_name', 'label': 'Injected'})
        for values in ({'column_key': 'review_reason'}, {'section': 'detail'}, {'layout_id': layout.id}, {'company_id': self.other_company.id}):
            with self.subTest(values=values), self.assertRaises(ValidationError), self.env.cr.savepoint():
                line.write(values)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            line.unlink()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            layout.write({'line_ids': [Command.clear()]})

    def test_relation_commands_cannot_move_or_edit_other_layout_lines(self):
        layout = self._layout()
        other_format = self._layout(output_format='pdf')
        other_line = self._line(other_format, 'employee_name')
        for command in (Command.link(other_line.id), Command.update(other_line.id, {'label': 'Injected'}), Command.unlink(self._line(layout, 'date').id)):
            with self.subTest(command=command), self.assertRaises(ValidationError), self.env.cr.savepoint():
                layout.write({'line_ids': [command]})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            layout.write({'summary_line_ids': [Command.update(self._line(layout, 'label', 'detail').id, {'label': 'Wrong section'})]})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            layout.write({'company_id': self.other_company.id})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            layout.write({'output_format': 'pdf'})

    def test_wrong_format_section_and_incomplete_catalogue_rejected(self):
        for output_format, section in (('csv', 'summary'), ('xlsx', 'private_fields')):
            with self.assertRaises(ValidationError):
                self.layout_model._coir_get_columns(self.company, output_format, section)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.layout_model.create({
                'company_id': self.company.id, 'output_format': 'xlsx',
                'line_ids': [Command.create({
                    'section': 'summary', 'column_key': 'employee_name', 'label': 'Empleado', 'visible': True,
                })],
            })

    def test_new_configuration_form_initializes_both_tabs_on_first_save(self):
        # Native form create/default_get/onchange/web_save flow, including the
        # empty one2many values submitted before the catalogue exists.
        model = self.layout_model.with_user(self.manager)
        with Form(model, view='coirtech_attendance_meal_control.report_layout_form') as form:
            form.company_id = self.company.with_env(model.env)
            form.output_format = 'pdf'
        layout = form.record
        self.assertEqual(layout.output_format, 'pdf')
        self.assertEqual(len(layout.summary_line_ids), 32)
        self.assertEqual(len(layout.detail_line_ids), 20)
        self.assertEqual(len(layout.summary_line_ids.filtered('visible')), 10)
        self.assertEqual(len(layout.detail_line_ids.filtered('visible')), 8)
        reopened = Form(layout, view='coirtech_attendance_meal_control.report_layout_form')
        self.assertEqual(len(reopened.summary_line_ids), 32)
        self.assertEqual(len(reopened.detail_line_ids), 20)

    def test_editable_form_hides_renames_and_reorders_summary_and_detail(self):
        layout = self._layout().with_user(self.manager)
        employee_line = self._line(layout, 'employee_name')
        company_line = self._line(layout, 'company_name')
        movement_line = self._line(layout, 'label', 'detail')
        with Form(layout, view='coirtech_attendance_meal_control.report_layout_form') as form:
            with form.summary_line_ids.edit(form.summary_line_ids.ids.index(employee_line.id)) as line:
                line.label = 'Colaborador en el resumen'
                # The handle persists this sequence when dragging a row.
                line.sequence = -20
            with form.summary_line_ids.edit(form.summary_line_ids.ids.index(company_line.id)) as line:
                line.visible = False
            with form.detail_line_ids.edit(form.detail_line_ids.ids.index(movement_line.id)) as line:
                line.label = 'Movimiento registrado'
                line.sequence = -10
        summary = self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary')
        detail = self.layout_model._coir_get_columns(self.company, 'xlsx', 'detail')
        self.assertEqual(summary[0]['key'], 'employee_name')
        self.assertEqual(summary[0]['label'], 'Colaborador en el resumen')
        self.assertNotIn('company_name', [item['key'] for item in summary])
        self.assertEqual(detail[0]['key'], 'label')
        self.assertEqual(detail[0]['label'], 'Movimiento registrado')
        self.assertEqual(self._line(layout, 'employee_name', 'detail').label, 'Empleado')

    def test_form_can_replace_the_last_visible_column_in_one_save(self):
        layout = self._layout().with_user(self.manager)
        employee_line = self._line(layout, 'employee_name')
        date_line = self._line(layout, 'date')
        layout.write({'summary_line_ids': [
            Command.update(line.id, {'visible': line == employee_line}) for line in layout.summary_line_ids
        ]})
        with Form(layout, view='coirtech_attendance_meal_control.report_layout_form') as form:
            with form.summary_line_ids.edit(form.summary_line_ids.ids.index(employee_line.id)) as line:
                line.visible = False
            with form.summary_line_ids.edit(form.summary_line_ids.ids.index(date_line.id)) as line:
                line.visible = True
                line.label = 'Día de asistencia'
        columns = self.layout_model._coir_get_columns(self.company, 'xlsx', 'summary')
        self.assertEqual([(column['key'], column['label']) for column in columns], [('date', 'Día de asistencia')])

    def test_export_wizard_merged_form_compiles_for_manager_and_officer(self):
        view_id = self.env.ref('coirtech_attendance_meal_control.attendance_report_wizard_form').id
        for user, can_configure in ((self.manager, True), (self.officer, False)):
            with self.subTest(user=user.login):
                model = self.env['coir.attendance.report.wizard'].with_user(user)
                views = model.get_views([(view_id, 'form')])
                arch = etree.fromstring(views['views']['form']['arch'])
                self.assertEqual(bool(arch.xpath("//button[@name='action_customize_columns']")), can_configure)
                self.assertEqual(bool(arch.xpath("//field[@name='layout_company_id']")), can_configure)
                self.assertTrue(arch.xpath("//button[@name='action_export_xlsx']"))
                self.assertTrue(arch.xpath("//button[@name='action_print_pdf']"))
                # Default fields and onchanges must also work for an officer
                # without access to private hr.employee records.
                form = Form(model, view=view_id)
                self.assertIn(self.company.id, form.company_ids.ids)
