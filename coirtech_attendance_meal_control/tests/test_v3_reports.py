import base64
import io
from datetime import date
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV3Reports(TransactionCase):
    """Real XLSX/QWeb outputs for absence-only, late entry, and selected rows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False, 'coir_meal_control_enabled': True,
            'coir_absence_enabled': True, 'coir_absence_tz': 'America/Mexico_City',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'COIRTECH absence report calendar', 'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [
                Command.create({
                    'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                    'hour_from': 8, 'hour_to': 17,
                }) for day in range(5)
            ],
        })
        cls.department = cls.env['hr.department'].create({
            'name': 'Absence report department', 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Report absent employee', 'company_id': cls.company.id,
            'department_id': cls.department.id, 'resource_calendar_id': cls.calendar.id,
            'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        cls.officer = new_test_user(
            cls.env, login='coir_v3_report_officer',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
            company_id=cls.company.id,
        )

    def _absence(self):
        self.env['coir.attendance.absence']._generate_for_day(
            self.company, date(2026, 11, 23), now=fields.Datetime.to_datetime('2026-11-23 15:00:00'),
        )
        record = self.env['coir.attendance.absence'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23'),
        ])
        self.assertEqual(len(record), 1)
        self.assertEqual(record.state, 'absent')
        return record

    def _wizard(self, user=None, **extra):
        vals = {
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(self.employee.ids)],
        }
        vals.update(extra)
        if user and vals.get('employee_ids') == [Command.clear()]:
            # Do not write an unnecessary employee M2M for an attendance officer
            # who intentionally has no private hr.employee model permissions.
            vals.pop('employee_ids')
        model = self.env['coir.attendance.report.wizard']
        return model.with_user(user).create(vals) if user else model.create(vals)

    @staticmethod
    def _xlsx(content):
        with ZipFile(io.BytesIO(content)) as archive:
            parts = {name: ElementTree.fromstring(archive.read(name)) for name in [
                'xl/sharedStrings.xml', 'xl/styles.xml',
                'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml',
            ]}
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        strings = [''.join(item.itertext()) for item in parts['xl/sharedStrings.xml'].findall('s:si', ns)]
        sheets = [
            {cell.attrib['r']: cell for cell in parts['xl/worksheets/sheet%s.xml' % n].findall('.//s:c', ns)}
            for n in (1, 2)
        ]
        return parts, ns, strings, sheets

    def test_absence_only_xlsx_red_text_and_no_fictitious_hours(self):
        self._absence()
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))
        wizard = self._wizard()
        with self.assertRaises(UserError):
            wizard._get_attendances()
        wizard.action_export_xlsx()
        parts, ns, strings, (summary, detail) = self._xlsx(base64.b64decode(wizard.report_file))
        for cells, coordinate in [(summary, 'F6'), (summary, 'P6'), (detail, 'F6'), (detail, 'M6')]:
            cell = cells[coordinate]
            self.assertEqual(strings[int(cell.find('s:v', ns).text)], 'FALTA')
            styles = parts['xl/styles.xml']
            fmt = styles.findall('s:cellXfs/s:xf', ns)[int(cell.attrib['s'])]
            font = styles.findall('s:fonts/s:font', ns)[int(fmt.attrib['fontId'])]
            fill = styles.findall('s:fills/s:fill', ns)[int(fmt.attrib['fillId'])]
            self.assertEqual(font.find('s:color', ns).attrib['rgb'], 'FF9C0006')
            self.assertEqual(fill.find('s:patternFill/s:fgColor', ns).attrib['rgb'], 'FFFFC7CE')
        for cells, coordinates in [
            (summary, ['G6', 'K6', 'L6', 'M6']),
            (detail, ['E6', 'G6', 'I6', 'K6', 'L6']),
        ]:
            for coordinate in coordinates:
                self.assertIsNone(cells[coordinate].find('s:v', ns), coordinate)
        self.assertNotEqual(summary['B6'].attrib['s'], summary['F6'].attrib['s'])
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))

    def test_late_native_attendance_replaces_falta_with_actual_time(self):
        absence = self._absence()
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime('2026-11-23 23:00:00')):
            attendance = self.env['hr.attendance'].create({
                'employee_id': self.employee.id, 'check_in': '2026-11-23 16:30:00',
                'check_out': '2026-11-23 23:00:00', 'in_mode': 'manual', 'out_mode': 'manual',
            })
        self.assertEqual(absence.state, 'resolved')
        wizard = self._wizard()
        records, absences = wizard._get_report_records()
        self.assertEqual(records, attendance)
        self.assertFalse(absences)
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(records, absences)
        self.assertEqual(len(dataset['summary']), 1)
        row = dataset['summary'][0]
        self.assertFalse(row['is_absence'])
        self.assertEqual((row['first_entry'].hour, row['first_entry'].minute), (10, 30))
        self.assertAlmostEqual(row['paid_seconds'], attendance.worked_hours * 3600)
        self.assertFalse(any(event['label'] in ('FALTA', 'PRESENTE') for event in dataset['events']))
        wizard.action_export_xlsx()
        _, ns, _, (summary, _) = self._xlsx(base64.b64decode(wizard.report_file))
        self.assertNotEqual(summary['F6'].attrib.get('t'), 's')
        self.assertIsNotNone(summary['F6'].find('s:v', ns))

    def test_absence_only_pdf_renders_without_attendance(self):
        absence = self._absence()
        action = self._wizard().with_context(discard_logo_check=True).action_print_pdf()
        self.assertEqual(action['data']['coir_absence_ids'], absence.ids)
        self.assertEqual(action['data']['coir_attendance_ids'], [])
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'coirtech_attendance_meal_control.action_report_meal', [], data=action['data'],
        )
        rendered = html.decode()
        self.assertIn('FALTA', rendered)
        self.assertIn('#9c0006', rendered)
        self.assertIn(self.employee.name, rendered)
        self.assertNotIn('23/11/2026 09:00', rendered)

    def test_absence_filters_and_officer_assignment_are_respected(self):
        absence = self._absence()
        wizard = self._wizard(department_ids=[Command.set(self.department.ids)])
        self.assertEqual(wizard._get_absences(), absence)
        wizard.write({'date_from': '2026-11-24', 'date_to': '2026-11-24'})
        with self.assertRaises(UserError):
            wizard._get_report_records()
        self.employee.attendance_manager_id = self.officer
        restricted = self._wizard(user=self.officer, employee_ids=[Command.clear()])
        self.assertEqual(restricted._get_absences(), absence.with_user(self.officer))
        restricted.action_export_xlsx()
        self.employee.attendance_manager_id = False
        with self.assertRaises(AccessError):
            restricted._get_absences()
        with self.assertRaises(AccessError):
            self.env['report.coirtech_attendance_meal_control.report_meal_journeys'].with_user(self.officer)._coir_dataset(
                self.env['hr.attendance'].with_user(self.officer), absence.with_user(self.officer),
            )

    def test_explicit_selected_journeys_do_not_include_other_absences(self):
        absence = self._absence()
        other = self.env['hr.employee'].create({
            'name': 'Report selected present', 'company_id': self.company.id,
            'resource_calendar_id': self.calendar.id, 'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        attendance = self.env['hr.attendance'].create({
            'employee_id': other.id, 'check_in': '2026-11-23 14:00:00',
            'check_out': '2026-11-23 23:00:00',
        })
        wizard = self._wizard(
            employee_ids=[Command.clear()], attendance_ids=[Command.set(attendance.ids)], selection_only=True,
        )
        records, absences = wizard._get_report_records()
        self.assertEqual(records, attendance)
        self.assertFalse(absences)
        self.assertEqual(absence.state, 'absent')

    def test_selected_absence_row_keeps_selection_when_no_journey_exists(self):
        absence = self._absence()
        rows = self.env['coir.attendance.day'].search([('absence_id', '=', absence.id)])
        self.assertEqual(len(rows), 1)
        wizard = self.env['coir.attendance.report.wizard'].with_context(
            active_model='coir.attendance.day', active_ids=rows.ids,
        ).create({})
        self.assertTrue(wizard.selection_only)
        self.assertEqual(wizard.absence_ids, absence)
        self.assertFalse(wizard.attendance_ids)
        records, absences = wizard._get_report_records()
        self.assertFalse(records)
        self.assertEqual(absences, absence)
