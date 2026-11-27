"""V4.3: native Time Off names in real Excel/PDF output, without fake hours."""
import base64
import io
from datetime import timedelta
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from lxml import html as html_parser

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'coir_v43')
class TestCoirV43Reports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False, 'coir_meal_control_enabled': True,
            'coir_absence_enabled': True, 'coir_absence_tz': 'UTC',
            'coir_absence_tracking_started_at': '2026-11-01 00:00:00',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'V4.3 report calendar', 'company_id': cls.company.id, 'tz': 'UTC',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'V4.3 report employee', 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id, 'tz': 'UTC', 'ruleset_id': False,
        })
        cls.report = cls.env['report.coirtech_attendance_meal_control.report_meal_journeys']
        # These checks deliberately inspect the default column coordinates.
        # Isolate that fixture from layouts already saved on an upgrade DB;
        # TransactionCase rolls these changes back with the class savepoint.
        for layout in cls.env['coir.attendance.report.layout'].search([('company_id', '=', cls.company.id)]):
            layout.action_reset_defaults()

    def setUp(self):
        super().setUp()
        clock = patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime('2026-11-24 12:00:00'))
        clock.start()
        self.addCleanup(clock.stop)

    def _leave(self, name='Permiso personal especial', approval='hr', hours=None,
               employee=None, day='2026-11-23'):
        leave_type = self.env['hr.leave.type'].create({
            'name': name, 'requires_allocation': False,
            'leave_validation_type': approval, 'request_unit': 'hour' if hours else 'day',
        })
        values = {
            'employee_id': (employee or self.employee).id, 'holiday_status_id': leave_type.id,
            'request_date_from': day, 'request_date_to': day,
            'name': 'V43_PRIVATE_REQUEST_DESCRIPTION_NOT_FOR_REPORT',
        }
        if hours:
            values.update(request_hour_from=hours[0], request_hour_to=hours[1])
        return self.env['hr.leave'].create(values)

    def _wizard(self, employee=None, **extra):
        return self.env['coir.attendance.report.wizard'].create({
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set((employee or self.employee).ids)], **extra,
        })

    @staticmethod
    def _xlsx(content):
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(content)) as archive:
            strings_doc = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(item.itertext()) for item in strings_doc.findall('s:si', ns)]
            sheets = [ElementTree.fromstring(archive.read('xl/worksheets/sheet%s.xml' % number))
                      for number in (1, 2)]
        return ns, strings, sheets

    def _assert_report_output(self, wizard, label, authorized_hours=None):
        records, notices = wizard._get_report_records()
        dataset = self.report._coir_dataset(records, notices)
        row = dataset['summary'][0]
        self.assertEqual(row['leave_label'], label)
        self.assertEqual(row['notice_label'], label)
        self.assertEqual(row['status'], label)
        self.assertTrue(row['leave_periods'])
        self.assertFalse(row['is_absence'])
        self.assertIsNone(row['paid_seconds'])
        self.assertIsNone(row['first_entry'])
        self.assertEqual(row['leave_seconds'], authorized_hours * 3600 if authorized_hours else None)
        wizard.action_export_xlsx()
        ns, strings, sheets = self._xlsx(base64.b64decode(wizard.report_file))
        self.assertIn(label, strings)
        self.assertIn('Periodo de ausencia', strings)
        self.assertNotIn('Periodo autorizado', strings)
        self.assertFalse(any('Pendiente de aprobación' in value for value in strings))
        self.assertFalse(any('V43_PRIVATE_REQUEST_DESCRIPTION_NOT_FOR_REPORT' in value for value in strings))
        for sheet in sheets:
            self.assertFalse(sheet.findall('.//s:f', ns), 'User labels must remain text, never formulas')
        summary = {cell.attrib['r']: cell for cell in sheets[0].findall('.//s:c', ns)}
        value = summary['T6'].find('s:v', ns)
        if authorized_hours:
            self.assertAlmostEqual(float(value.text), authorized_hours / 24)
        else:
            self.assertIsNone(value)
        for coordinate in ('F6', 'G6', 'K6'):
            self.assertIsNone(summary[coordinate].find('s:v', ns))
        action = wizard.with_context(discard_logo_check=True).action_print_pdf()
        rendered, _kind = self.env['ir.actions.report']._render_qweb_html(
            'coirtech_attendance_meal_control.action_report_meal', [], data=action['data'],
        )
        text = ' '.join(html_parser.fromstring(rendered).itertext())
        self.assertIn(label, text)
        self.assertNotIn('Pendiente de aprobación', text)
        self.assertNotIn('Ausencia aprobada', text)
        self.assertNotIn('V43_PRIVATE_REQUEST_DESCRIPTION_NOT_FOR_REPORT', text)
        return notices

    def test_submitted_and_first_approval_show_native_type_without_approval_banner(self):
        for approval, state, label in (
                ('hr', 'confirm', 'Permiso por trámite personal'),
                ('both', 'validate1', 'Permiso de estudios <especial>')):
            with self.subTest(state=state):
                employee = self.env['hr.employee'].create({
                    'name': 'V43 pending %s' % state, 'company_id': self.company.id,
                    'resource_calendar_id': self.calendar.id, 'tz': 'UTC', 'ruleset_id': False,
                })
                leave = self._leave(name=label, approval=approval, employee=employee)
                if state == 'validate1':
                    # The test superuser can validate both levels at once.
                    # Exercise the native first-approval path explicitly.
                    leave.action_approve(check_state=False)
                self.assertEqual(leave.state, state)
                notices = self._assert_report_output(self._wizard(employee=employee), label)
                self.assertEqual(leave.state, state)
                self.assertFalse(notices.leave_hours)
                day_row = self.env['coir.attendance.day'].search([('absence_id', 'in', notices.ids)])
                self.assertEqual(day_row.report_label, label)
                self.assertFalse(day_row.worked_hours)
                self.assertFalse(day_row.check_in)
                self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', employee.id)]))

    def test_approval_only_changes_authorized_hours_and_keeps_original_indicator(self):
        leave = self._leave()
        wizard = self._wizard()
        before = self._assert_report_output(wizard, leave.holiday_status_id.name)
        leave.action_approve()
        self.assertEqual(leave.state, 'validate')
        after = self._assert_report_output(wizard, leave.holiday_status_id.name, authorized_hours=9)
        self.assertEqual(before, after)
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))

    def test_adjacent_approved_and_submitted_intervals_only_count_approved_hours(self):
        approved = self._leave(name='Permiso médico', approval='no_validation', hours=(8, 12))
        pending = self._leave(name='Permiso familiar', approval='hr', hours=(12, 17))
        wizard = self._wizard()
        labels = '%s + %s' % (approved.holiday_status_id.name, pending.holiday_status_id.name)
        self._assert_report_output(wizard, labels, authorized_hours=4)
        self.assertEqual(approved.state, 'validate')
        self.assertEqual(pending.state, 'confirm')

    def test_native_type_rename_refreshes_exports_and_legacy_mapping_is_ignored(self):
        leave = self._leave()
        old_name = leave.holiday_status_id.name
        new_name = '=Permiso especial & familiar'
        leave.holiday_status_id.write({'name': new_name, 'coir_attendance_category': 'disability'})
        notices = self._assert_report_output(self._wizard(), new_name)
        self.assertNotIn(old_name, notices.leave_periods)
        self.assertNotIn('INCAPACIDAD', notices.report_label)
        self.assertEqual(leave.state, 'confirm')

    def test_company_language_keeps_native_translation_stable_across_sync_contexts(self):
        # Activate only the language record; this does not import module-wide
        # translations. Give this actual native type two explicit translations.
        self.assertTrue(self.env['res.lang']._activate_lang('es_MX'))
        self.company.partner_id.lang = 'es_MX'
        leave = self._leave(name='Study leave')
        leave_type = leave.holiday_status_id
        leave_type.with_context(lang='es_MX').write({'name': 'Permiso de estudios'})
        self.assertEqual(leave_type.with_context(lang='en_US').name, 'Study leave')
        self.assertEqual(leave_type.with_context(lang='es_MX').name, 'Permiso de estudios')
        for sync_lang in ('en_US', 'es_MX', 'en_US'):
            with self.subTest(sync_lang=sync_lang):
                self.env['coir.attendance.absence'].with_context(lang=sync_lang)._sync_approved_leaves(
                    '2026-11-23', '2026-11-23', self.company.ids,
                )
                notice = self.env['coir.attendance.absence'].search([
                    ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23'),
                ])
                self.assertEqual(notice.leave_label, 'Permiso de estudios')
                self.assertEqual(notice.report_label, 'Permiso de estudios')
                self.assertIn('Permiso de estudios', notice.leave_periods)
                self.assertNotIn('Study leave', notice.leave_periods)
        self._assert_report_output(self._wizard(), 'Permiso de estudios')
        self.assertEqual(leave.state, 'confirm')
        # An empty company language has a deterministic original-name fallback,
        # even if the caller is using Spanish for its own interface.
        self.company.partner_id.lang = False
        self.env['coir.attendance.absence'].with_context(lang='es_MX')._sync_approved_leaves(
            '2026-11-23', '2026-11-23', self.company.ids,
        )
        self.assertEqual(notice.leave_label, 'Study leave')
        self.assertEqual(leave.state, 'confirm')

    def test_refused_request_disappears_while_real_hours_remain(self):
        leave = self._leave(hours=(8, 12))
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-11-23 12:00:00', 'check_out': '2026-11-23 17:00:00',
            'in_mode': 'manual', 'out_mode': 'manual',
        })
        wizard = self._wizard()
        before = self.report._coir_dataset(*wizard._get_report_records())
        self.assertIn(leave.holiday_status_id.name, before['summary'][0]['notice_label'])
        self.assertEqual(before['summary'][0]['paid_seconds'], attendance.worked_hours * 3600)
        leave.action_refuse()
        after = self.report._coir_dataset(*wizard._get_report_records())
        self.assertFalse(after['absences'])
        self.assertFalse(after['summary'][0]['notice_label'])
        self.assertEqual(after['summary'][0]['paid_seconds'], before['summary'][0]['paid_seconds'])
        self.assertEqual(after['docs'], attendance)

    def test_future_submitted_request_stays_hidden_from_reports(self):
        # The SQL projection uses the database clock, so this fixture must stay
        # future relative to both real time and the source-hook test clock.
        day = max(fields.Date.today(), fields.Date.to_date('2026-11-24')) + timedelta(days=30)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        leave = self._leave(day=day)
        self.assertEqual(leave.state, 'confirm')
        wizard = self._wizard(date_from=day, date_to=day)
        with self.assertRaises(UserError):
            wizard._get_report_records()
        self.assertFalse(self.env['coir.attendance.day'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', day),
        ]))
        self.assertEqual(leave.state, 'confirm')
