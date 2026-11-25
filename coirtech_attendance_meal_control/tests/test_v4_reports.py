"""V4 outputs against real approved hr.leave sources and actual attendance."""
import base64
import io
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV4Reports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False, 'coir_meal_control_enabled': True,
            'coir_absence_enabled': True, 'coir_absence_tz': 'America/Mexico_City',
            'coir_absence_tracking_started_at': '2026-11-01 00:00:00',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'COIRTECH V4 report schedule', 'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'V4 report employee', 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id, 'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        cls.report = cls.env['report.coirtech_attendance_meal_control.report_meal_journeys']

    def setUp(self):
        super().setUp()
        clock = patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime('2026-11-24 00:00:00'))
        clock.start()
        self.addCleanup(clock.stop)

    def _leave(self, category='vacation', hours=None, employee=None, day='2026-11-23', approval='no_validation'):
        employee = employee or self.employee
        leave_type = self.env['hr.leave.type'].create({
            'name': 'Mapped V4 test category', 'requires_allocation': False,
            'leave_validation_type': approval, 'request_unit': 'hour' if hours else 'day',
            'coir_attendance_category': category,
        })
        values = {
            'employee_id': employee.id, 'holiday_status_id': leave_type.id,
            'request_date_from': day, 'request_date_to': day,
            'name': 'PRIVATE_MEDICAL_NOTE_DO_NOT_EXPORT',
        }
        if hours:
            values.update(request_hour_from=hours[0], request_hour_to=hours[1])
        leave = self.env['hr.leave'].create(values)
        if approval == 'no_validation':
            self.assertEqual(leave.state, 'validate')
        return leave

    def _attendance(self, employee=None, check_in='2026-11-23 19:00:00', check_out='2026-11-23 23:00:00'):
        return self.env['hr.attendance'].create({
            'employee_id': (employee or self.employee).id,
            'check_in': check_in, 'check_out': check_out,
            'in_mode': 'manual', 'out_mode': 'manual',
        })

    def _wizard(self, **extra):
        values = {
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(self.employee.ids)],
        }
        values.update(extra)
        return self.env['coir.attendance.report.wizard'].create(values)

    @staticmethod
    def _xlsx(content):
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(content)) as archive:
            parts = {name: ElementTree.fromstring(archive.read(name)) for name in (
                'xl/sharedStrings.xml', 'xl/styles.xml',
                'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml',
            )}
        strings = [''.join(item.itertext()) for item in parts['xl/sharedStrings.xml'].findall('s:si', ns)]
        sheets = [
            {cell.attrib['r']: cell for cell in parts['xl/worksheets/sheet%s.xml' % n].findall('.//s:c', ns)}
            for n in (1, 2)
        ]
        return parts, ns, strings, sheets

    def test_approved_only_xlsx_and_pdf_have_label_without_fake_work_or_private_notes(self):
        leave = self._leave()
        wizard = self._wizard()
        records, notices = wizard._get_report_records()
        self.assertFalse(records)
        self.assertEqual(notices.state, 'approved')
        dataset = self.report._coir_dataset(records, notices)
        row = dataset['summary'][0]
        self.assertEqual(row['notice_label'], 'VACACIONES')
        self.assertFalse(row['is_absence'])
        self.assertIsNone(row['first_entry'])
        self.assertIsNone(row['paid_seconds'])
        self.assertEqual(row['leave_seconds'], 9 * 3600)
        self.assertEqual(row['journeys'], 0)
        self.assertEqual(len(dataset['events']), 1)
        self.assertIsNone(dataset['events'][0]['stamp'])
        self.assertIsNone(dataset['events'][0]['journey_id'])
        wizard.action_export_xlsx()
        parts, ns, strings, (summary, detail) = self._xlsx(base64.b64decode(wizard.report_file))
        self.assertEqual(strings[int(summary['R6'].find('s:v', ns).text)], 'VACACIONES')
        self.assertAlmostEqual(float(summary['T6'].find('s:v', ns).text), 9 / 24)
        for coordinate in ('F6', 'G6', 'K6', 'L6', 'M6'):
            self.assertIsNone(summary[coordinate].find('s:v', ns), coordinate)
        for coordinate in ('E6', 'G6', 'I6', 'K6', 'L6'):
            self.assertIsNone(detail[coordinate].find('s:v', ns), coordinate)
        fmt = parts['xl/styles.xml'].findall('s:cellXfs/s:xf', ns)[int(summary['R6'].attrib['s'])]
        font = parts['xl/styles.xml'].findall('s:fonts/s:font', ns)[int(fmt.attrib['fontId'])]
        color = font.find('s:color', ns)
        self.assertFalse(color is not None and color.attrib.get('rgb') == 'FF9C0006')
        self.assertFalse(any('PRIVATE_MEDICAL_NOTE_DO_NOT_EXPORT' in string for string in strings))
        action = wizard.with_context(discard_logo_check=True).action_print_pdf()
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'coirtech_attendance_meal_control.action_report_meal', [], data=action['data'],
        )
        self.assertIn('VACACIONES', html.decode())
        self.assertNotIn('PRIVATE_MEDICAL_NOTE_DO_NOT_EXPORT', html.decode())
        self.assertNotIn('Jornada None', html.decode())
        self.assertEqual(leave.state, 'validate')
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))

    def test_partial_leave_with_actual_entry_merges_summary_without_adding_authorised_hours(self):
        self._leave(category='paid_absence', hours=(8, 13))
        attendance = self._attendance()
        wizard = self._wizard()
        records, notices = wizard._get_report_records()
        self.assertEqual(records, attendance)
        self.assertEqual(notices.state, 'partial')
        dataset = self.report._coir_dataset(records, notices)
        self.assertEqual(len(dataset['summary']), 1)
        row = dataset['summary'][0]
        self.assertEqual(row['first_entry'].hour, 13)
        self.assertEqual(row['journeys'], 1)
        self.assertAlmostEqual(row['paid_seconds'], attendance.worked_hours * 3600)
        self.assertEqual(row['leave_seconds'], 5 * 3600)
        self.assertIn('FALTA CON SUELDO', row['notice_label'])
        self.assertFalse(row['review_reason'])
        self.assertFalse(any(event['label'] in ('FALTA', 'PRESENTE') for event in dataset['events']))
        self.assertEqual(sum(event['journey_seconds'] or 0 for event in dataset['events']), row['paid_seconds'])
        self.assertEqual(sum(event['leave_seconds'] or 0 for event in dataset['events']), 5 * 3600)
        direct = self.report._coir_dataset(attendance)
        self.assertEqual(direct['summary'][0]['leave_seconds'], 5 * 3600)
        selected = self._wizard(attendance_ids=[Command.set(attendance.ids)], selection_only=True)
        self.assertEqual(selected._get_report_records()[1], notices)

    def test_partial_without_entry_is_rh_review_and_never_red_full_day_falta(self):
        self._leave(category='unpaid_absence', hours=(8, 13))
        records, notices = self._wizard()._get_report_records()
        self.assertFalse(records)
        self.assertEqual(notices.state, 'review')
        dataset = self.report._coir_dataset(records, notices)
        row = dataset['summary'][0]
        self.assertFalse(row['is_absence'])
        self.assertIn('REVISAR RH', row['notice_label'])
        self.assertTrue(row['review_reason'])
        self.assertEqual(row['leave_seconds'], 5 * 3600)
        self.assertIsNone(row['paid_seconds'])
        self.assertFalse(any(event['is_absence'] for event in dataset['events']))

    def test_attendance_during_approved_leave_preserves_both_and_flags_overlap(self):
        self._leave(category='disability')
        attendance = self._attendance(check_in='2026-11-23 14:00:00', check_out='2026-11-23 15:00:00')
        records, notices = self._wizard()._get_report_records()
        self.assertEqual(notices.state, 'review')
        dataset = self.report._coir_dataset(records, notices)
        self.assertEqual(len(dataset['summary']), 1)
        self.assertEqual(dataset['summary'][0]['first_entry'].hour, 8)
        self.assertTrue(dataset['summary'][0]['review_reason'])
        self.assertIn('INCAPACIDAD', dataset['summary'][0]['notice_label'])
        self.assertAlmostEqual(dataset['summary'][0]['paid_seconds'], attendance.worked_hours * 3600)

    def test_exclusion_removes_all_periods_from_exports_but_keeps_original_sources(self):
        leave = self._leave()
        historical = self._attendance(check_in='2025-11-03 14:00:00', check_out='2025-11-03 23:00:00')
        self.employee.coir_attendance_report_excluded = True
        self.assertEqual(leave.state, 'validate')
        self.assertTrue(historical.exists())
        self.assertFalse(self.env['coir.attendance.day'].search([('employee_id', '=', self.employee.id)]))
        for wizard in (self._wizard(), self._wizard(date_from='2025-11-01', date_to='2026-11-30')):
            with self.assertRaises(UserError):
                wizard._get_report_records()
        with self.assertRaises(UserError):
            self.report._coir_dataset(historical)
        self.employee.coir_attendance_report_excluded = False
        records, notices = self._wizard(date_from='2025-11-01', date_to='2026-11-30')._get_report_records()
        self.assertIn(historical, records)
        self.assertIn('VACACIONES', notices.mapped('leave_label'))

    def test_all_excluded_native_selection_never_falls_back_to_unrestricted_report(self):
        hidden = self._attendance()
        other = self.env['hr.employee'].create({
            'name': 'V4 visible employee', 'company_id': self.company.id,
            'resource_calendar_id': self.calendar.id, 'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        visible = self._attendance(employee=other)
        self.employee.coir_attendance_report_excluded = True
        wizard = self.env['coir.attendance.report.wizard'].with_context(
            active_model='hr.attendance', active_ids=hidden.ids,
        ).create({
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
        })
        self.assertTrue(wizard.selection_only)
        self.assertFalse(wizard.attendance_ids)
        with self.assertRaises(UserError):
            wizard.action_export_xlsx()
        self.assertTrue(visible.exists())
        mixed = self.report._coir_dataset(hidden | visible)
        self.assertEqual(mixed['docs'], visible)
        self.assertEqual(len(mixed['summary']), 1)

    def test_source_notice_rule_does_not_leak_through_real_attendance_selection(self):
        self._leave(hours=(8, 13))
        attendance = self._attendance()
        notice = self._wizard()._get_report_records()[1]
        reader = new_test_user(
            self.env, login='coir_v4_reports_reader',
            groups='base.group_user,hr_attendance.group_hr_attendance_user',
            company_id=self.company.id,
        )
        self.env['ir.rule'].create({
            'name': 'V4 block original notice',
            'model_id': self.env['ir.model']._get_id('coir.attendance.absence'),
            'domain_force': "[('id', '!=', %s)]" % notice.id,
        })
        dataset = self.report.with_user(reader)._coir_dataset(attendance)
        self.assertEqual(dataset['docs'].ids, attendance.ids)
        self.assertFalse(dataset['absences'])
        self.assertEqual(dataset['summary'][0]['notice_label'], '')
        with self.assertRaises(AccessError):
            self.report.with_user(reader)._coir_dataset(attendance, notice)

    def test_assigned_attendance_officer_without_private_hr_rights_can_filter_and_export(self):
        self._leave()
        officer = new_test_user(
            self.env, login='coir_v4_reports_officer',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
            company_id=self.company.id,
        )
        self.assertFalse(officer.has_group('hr.group_hr_user'))
        self.employee.attendance_manager_id = officer
        self.env.invalidate_all()
        matches = self.env['hr.employee'].with_user(officer).search_read([
            ('id', '=', self.employee.id), ('coir_attendance_report_excluded', '=', False),
        ], ['name', 'coir_attendance_report_excluded'])
        self.assertEqual([match['id'] for match in matches], self.employee.ids)
        wizard = self.env['coir.attendance.report.wizard'].with_user(officer).create({
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(self.employee.ids)],
        })
        self.assertEqual(wizard.employee_ids.ids, self.employee.ids)
        records, notices = wizard._get_report_records()
        self.assertFalse(records)
        self.assertEqual(notices.employee_id.ids, self.employee.ids)
        wizard.action_export_xlsx()
        self.assertTrue(wizard.report_file)
        wizard.write({'employee_ids': [Command.clear()]})
        wizard.write({'employee_ids': [Command.set(self.employee.ids)]})
        self.assertEqual(wizard.employee_ids.ids, self.employee.ids)
        wizard.action_export_xlsx()
        self.employee.coir_attendance_report_excluded = True
        self.env.invalidate_all()
        self.assertFalse(self.env['hr.employee'].with_user(officer).search([
            ('id', '=', self.employee.id), ('coir_attendance_report_excluded', '=', False),
        ]))
        with self.assertRaises(UserError):
            wizard._get_report_records()
