import base64
import io
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV2Reports(TransactionCase):
    """Render the actual report and inspect real XLSX cells, not mocked output."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'auto_check_out': False, 'coir_meal_control_enabled': True})
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'COIRTECH report UTC calendar', 'company_id': cls.company.id, 'tz': 'UTC',
        })
        cls.department = cls.env['hr.department'].create({'name': 'Report department', 'company_id': cls.company.id})
        cls.employee = cls.env['hr.employee'].create({
            'name': '=SUM(1,2)', 'company_id': cls.company.id, 'department_id': cls.department.id,
            'resource_calendar_id': cls.calendar.id, 'tz': 'UTC', 'ruleset_id': False,
        })
        cls.officer = new_test_user(
            cls.env, login='coir_v2_report_officer',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
            company_id=cls.company.id,
        )
        cls.basic_user = new_test_user(
            cls.env, login='coir_v2_report_basic_user', groups='base.group_user', company_id=cls.company.id,
        )

    def _act(self, employee, action, stamp):
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime(stamp)):
            employee = employee.sudo()
            state = employee._coir_meal_state()
            return employee._coir_apply_meal_action(
                action, state['attendance_id'], state['state'], expected_revision=state['revision'],
            )

    def _complete_day(self):
        record = self._act(self.employee, 'check_in', '2026-11-16 08:00:00')
        for action, stamp in [
            ('work_exit', '2026-11-16 10:00:00'), ('work_return', '2026-11-16 10:45:00'),
            ('meal_start', '2026-11-16 13:00:00'), ('meal_return', '2026-11-16 14:00:00'),
            ('work_exit', '2026-11-16 15:00:00'), ('work_return', '2026-11-16 15:30:00'),
            ('check_out', '2026-11-16 17:00:00'),
        ]:
            self._act(self.employee, action, stamp)
        return record

    def _wizard(self, **extra):
        values = {
            'date_from': '2026-11-16', 'date_to': '2026-11-16',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(self.employee.ids)],
        }
        values.update(extra)
        return self.env['coir.attendance.report.wizard'].create(values)

    @staticmethod
    def _xlsx_parts(content):
        with ZipFile(io.BytesIO(content)) as archive:
            return {name: ElementTree.fromstring(archive.read(name)) for name in [
                'xl/workbook.xml', 'xl/sharedStrings.xml', 'xl/styles.xml',
                'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml',
            ]}

    def test_real_xlsx_contains_all_movements_and_numeric_paid_hours(self):
        record = self._complete_day()
        wizard = self._wizard()
        result = wizard.action_export_xlsx()
        self.assertIn('/web/content/coir.attendance.report.wizard/%s/' % wizard.id, result['url'])
        content = base64.b64decode(wizard.report_file)
        self.assertTrue(content.startswith(b'PK'))
        parts = self._xlsx_parts(content)
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        self.assertEqual([n.attrib['name'] for n in parts['xl/workbook.xml'].findall('s:sheets/s:sheet', ns)], ['Resumen', 'Detalle'])
        summary = parts['xl/worksheets/sheet1.xml']
        detail = parts['xl/worksheets/sheet2.xml']
        cells = {cell.attrib['r']: cell for cell in summary.findall('.//s:c', ns)}
        self.assertAlmostEqual(float(cells['K6'].find('s:v', ns).text), 9 / 24)
        self.assertAlmostEqual(float(cells['L6'].find('s:v', ns).text), 1 / 24)
        self.assertAlmostEqual(float(cells['M6'].find('s:v', ns).text), 1.25 / 24)
        self.assertNotEqual(cells['D6'].attrib.get('t'), 's')
        self.assertFalse(summary.findall('.//s:f', ns))
        self.assertFalse(detail.findall('.//s:f', ns))
        strings = [''.join(item.itertext()) for item in parts['xl/sharedStrings.xml'].findall('s:si', ns)]
        self.assertIn('=SUM(1,2)', strings)
        movements = []
        for cell in detail.findall('.//s:c', ns):
            if cell.attrib['r'].startswith('F') and int(cell.attrib['r'][1:]) >= 6:
                movements.append(strings[int(cell.find('s:v', ns).text)])
        self.assertEqual(movements, [
            'Entrada', 'Salida de trabajo', 'Regreso al trabajo', 'Salir a comer',
            'Regresar de comida', 'Salida de trabajo', 'Regreso al trabajo', 'Salida final',
        ])
        formats = [row.attrib.get('formatCode') for row in parts['xl/styles.xml'].findall('s:numFmts/s:numFmt', ns)]
        self.assertIn('[h]:mm', formats)
        self.assertEqual(record.worked_hours, 9.0)

    def test_open_journey_and_missing_return_keep_unconfirmed_hours_blank(self):
        record = self._act(self.employee, 'check_in', '2026-11-16 08:00:00')
        self._act(self.employee, 'work_exit', '2026-11-16 10:00:00')
        wizard = self._wizard()
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(record)
        row = dataset['summary'][0]
        self.assertIsNone(row['paid_seconds'])
        self.assertIsNone(row['work_seconds'])
        self.assertEqual(row['work_pending'], 1)
        self.assertEqual(row['open'], 1)
        wizard.action_export_xlsx()
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        parts = self._xlsx_parts(base64.b64decode(wizard.report_file))
        cells = {cell.attrib['r']: cell for cell in parts['xl/worksheets/sheet1.xml'].findall('.//s:c', ns)}
        self.assertIsNone(cells['K6'].find('s:v', ns))
        self.assertIsNone(cells['M6'].find('s:v', ns))

    def test_summary_adds_closed_journeys_without_counting_gap_or_open_hours(self):
        completed = self._complete_day()
        self.env['coir.reentry.authorization'].create({
            'employee_id': self.employee.id, 'valid_date': '2026-11-16', 'reason': 'Authorized extra shift for report test',
        })
        open_record = self._act(self.employee, 'check_in', '2026-11-16 20:00:00')
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(completed | open_record)
        row = dataset['summary'][0]
        self.assertEqual(row['paid_seconds'], 9 * 3600)
        self.assertEqual(row['closed'], 1)
        self.assertEqual(row['open'], 1)
        self.assertIn('Parcial', row['status'])
        self._act(self.employee, 'check_out', '2026-11-16 22:00:00')
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(completed | open_record)
        self.assertEqual(dataset['summary'][0]['paid_seconds'], 11 * 3600)

    def test_pdf_template_renders_complete_and_open_journeys(self):
        complete = self._complete_day()
        another = self.env['hr.employee'].create({
            'name': 'Report open employee', 'company_id': self.company.id,
            'resource_calendar_id': self.calendar.id, 'tz': 'UTC', 'ruleset_id': False,
        })
        open_record = self._act(another, 'check_in', '2026-11-16 09:00:00')
        self._act(another, 'meal_start', '2026-11-16 13:00:00')
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'coirtech_attendance_meal_control.action_report_meal', (complete | open_record).ids,
        )
        text = html.decode()
        self.assertIn('Salida de trabajo', text)
        self.assertIn('Regreso al trabajo', text)
        self.assertIn('09:00', text)
        self.assertIn('01:15', text)
        self.assertIn('Regreso pendiente', text)
        self.assertIn('Pendiente', text)

    def test_filters_dates_companies_and_native_officer_rules(self):
        record = self._complete_day()
        record.employee_id.attendance_manager_id = self.officer
        wizard = self._wizard(department_ids=[Command.set(self.department.ids)])
        self.assertEqual(wizard._get_attendances(), record)
        wizard.date_from = '2026-11-15'
        wizard.date_to = '2026-11-15'
        with self.assertRaises(UserError):
            wizard._get_attendances()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.date_from = '2026-11-17'

        other_company = self.env['res.company'].create({'name': 'Report forbidden company'})
        forbidden = self._wizard(company_ids=[Command.set(other_company.ids)], employee_ids=[Command.clear()])
        # The company field's domain also hides a selection outside this session.
        with self.assertRaises(UserError):
            forbidden.with_context(allowed_company_ids=self.company.ids)._get_attendances()

        restricted = self.env['coir.attendance.report.wizard'].with_user(self.officer).create({
            'date_from': '2026-11-16', 'date_to': '2026-11-16',
            'company_ids': [Command.set(self.company.ids)],
        })
        self.assertEqual(restricted._get_attendances(), record)
        restricted.action_export_xlsx()
        self.assertTrue(base64.b64decode(restricted.report_file).startswith(b'PK'))
        record.employee_id.attendance_manager_id = False
        with self.assertRaises(UserError):
            restricted._get_attendances()
        with self.assertRaises(AccessError):
            self.env['report.coirtech_attendance_meal_control.report_meal_journeys'].with_user(self.basic_user)._coir_dataset(record.with_user(self.basic_user))
