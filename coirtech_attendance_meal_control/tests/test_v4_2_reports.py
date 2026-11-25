"""V4.2: real report layouts, native overtime and data visibility boundaries."""
import base64
import io
from datetime import date, datetime
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from lxml import html as html_parser

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV42Reports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False, 'coir_meal_control_enabled': True,
            'coir_absence_enabled': False, 'coir_absence_tz': 'UTC',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'V4.2 UTC report calendar', 'company_id': cls.company.id, 'tz': 'UTC',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.department = cls.env['hr.department'].create({
            'name': 'HIDDEN_DEPARTMENT_V42', 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': '=SUM(1,2)', 'company_id': cls.company.id,
            'department_id': cls.department.id, 'resource_calendar_id': cls.calendar.id,
            'tz': 'UTC', 'ruleset_id': False,
        })
        cls.report = cls.env['report.coirtech_attendance_meal_control.report_meal_journeys']

    def _act(self, action, stamp, employee=None):
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime(stamp)):
            employee = (employee or self.employee).sudo()
            state = employee._coir_meal_state()
            return employee._coir_apply_meal_action(
                action, state['attendance_id'], state['state'], expected_revision=state['revision'],
            )

    def _complete_day(self):
        attendance = self._act('check_in', '2026-11-16 08:00:00')
        for action, stamp in (
                ('work_exit', '2026-11-16 10:00:00'), ('work_return', '2026-11-16 10:30:00'),
                ('meal_start', '2026-11-16 13:00:00'), ('meal_return', '2026-11-16 14:00:00'),
                ('work_exit', '2026-11-16 15:00:00'), ('work_return', '2026-11-16 15:45:00'),
                ('check_out', '2026-11-16 17:00:00')):
            self._act(action, stamp)
        return attendance

    def _wizard(self, company_ids=None, employee_ids=None, **extra):
        company_ids = company_ids or self.company.ids
        values = {
            'date_from': '2026-11-16', 'date_to': '2026-11-16',
            'company_ids': [Command.set(company_ids)],
            'employee_ids': [Command.set(self.employee.ids if employee_ids is None else employee_ids)],
        }
        values.update(extra)
        return self.env['coir.attendance.report.wizard'].with_context(allowed_company_ids=company_ids).create(values)

    def _layout(self, output_format='xlsx', company=None, summary=None, detail=None):
        company = company or self.company
        model = self.env['coir.attendance.report.layout'].with_context(
            allowed_company_ids=list(set(self.company.ids + company.ids)),
        )
        layout = model.search([('company_id', '=', company.id), ('output_format', '=', output_format)], limit=1)
        if not layout:
            layout = model.create({'company_id': company.id, 'output_format': output_format})
        commands = []
        for section, chosen in (('summary', summary), ('detail', detail)):
            if chosen is None:
                continue
            chosen = [(item, item) if isinstance(item, str) else item for item in chosen]
            selected = {key: (index * 10, label) for index, (key, label) in enumerate(chosen, 1)}
            for line in layout.line_ids.filtered(lambda row: row.section == section):
                values = {'visible': line.column_key in selected}
                if line.column_key in selected:
                    values.update(sequence=selected[line.column_key][0], label=selected[line.column_key][1])
                commands.append(Command.update(line.id, values))
        if commands:
            layout.write({'line_ids': commands})
        return layout

    @staticmethod
    def _xlsx(content):
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(content)) as archive:
            paths = ['xl/workbook.xml', 'xl/sharedStrings.xml', 'xl/styles.xml']
            paths += sorted(name for name in archive.namelist() if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'))
            parts = {name: ElementTree.fromstring(archive.read(name)) for name in paths}
        strings = [''.join(item.itertext()) for item in parts['xl/sharedStrings.xml'].findall('s:si', ns)]
        sheets = []
        for path in paths[3:]:
            sheets.append({cell.attrib['r']: cell for cell in parts[path].findall('.//s:c', ns)})
        return parts, ns, strings, sheets

    @staticmethod
    def _text(cell, strings, ns):
        value = cell.find('s:v', ns)
        if value is None:
            return None
        return strings[int(value.text)] if cell.attrib.get('t') == 's' else value.text

    def _render_html(self, attendance):
        rendered, _kind = self.env['ir.actions.report']._render_qweb_html(
            'coirtech_attendance_meal_control.action_report_meal', attendance.ids,
        )
        return rendered.decode()

    def test_xlsx_hide_rename_reorder_and_numeric_dates_with_1904_epoch(self):
        attendance = self._complete_day()
        self._layout(summary=[('employee_name', '=HEADER(1,2)'), ('paid_seconds', 'Total pagado'), ('date', 'Día')],
                     detail=[('label', 'Movimiento elegido')])
        wizard = self._wizard()
        wizard.action_export_xlsx()
        parts, ns, strings, (summary, detail) = self._xlsx(base64.b64decode(wizard.report_file))
        self.assertEqual([self._text(summary[coordinate], strings, ns) for coordinate in ('A5', 'B5', 'C5')],
                         ['=HEADER(1,2)', 'Total pagado', 'Día'])
        self.assertEqual(self._text(summary['A6'], strings, ns), self.employee.name)
        self.assertAlmostEqual(float(summary['B6'].find('s:v', ns).text), 9 / 24)
        self.assertEqual(parts['xl/workbook.xml'].find('s:workbookPr', ns).attrib['date1904'], '1')
        self.assertEqual(float(summary['C6'].find('s:v', ns).text), (date(2026, 11, 16) - date(1904, 1, 1)).days)
        self.assertEqual(self._text(detail['A5'], strings, ns), 'Movimiento elegido')
        self.assertNotIn('B5', detail)
        self.assertNotIn(self.department.name, strings)
        for path, root in parts.items():
            self.assertFalse(root.findall('.//s:f', ns), path)
        self.assertEqual(attendance.worked_hours, 9)

    def test_pdf_column_selection_is_independent_and_headers_are_escaped(self):
        attendance = self._complete_day()
        self._layout('xlsx', summary=[('employee_name', 'EXCEL_ONLY_HEADER')], detail=['label'])
        self._layout('pdf', summary=[('paid_seconds', '<b>PDF total</b>'), ('date', 'PDF date')],
                     detail=[('label', 'PDF movement')])
        rendered = self._render_html(attendance)
        self.assertIn('&lt;b&gt;PDF total&lt;/b&gt;', rendered)
        self.assertNotIn('<b>PDF total</b>', rendered)
        self.assertNotIn('EXCEL_ONLY_HEADER', rendered)
        self.assertNotIn(self.department.name, rendered)
        self.assertNotIn(self.employee.name, rendered)
        root = html_parser.fromstring(rendered)
        headers = [node.text_content().strip() for node in root.xpath('//table[contains(@class, "coir-summary")]/thead/tr/th')]
        self.assertEqual(headers, ['<b>PDF total</b>', 'PDF date'])
        self.assertIn('09:00', rendered)

    def test_multiple_companies_use_separate_layouts_and_safe_unique_sheet_names(self):
        attendance = self._complete_day()
        other = self.env['res.company'].create({
            'name': 'V42 [Company]/with:very?long*name for Excel',
            'auto_check_out': False, 'coir_meal_control_enabled': True,
        })
        self.env.user.write({'company_ids': [Command.link(other.id)]})
        other_employee = self.env['hr.employee'].with_company(other).create({
            'name': 'ONLY_SECOND_COMPANY_V42', 'company_id': other.id, 'tz': 'UTC', 'ruleset_id': False,
        })
        second = self.env['hr.attendance'].with_company(other).create({
            'employee_id': other_employee.id, 'check_in': '2026-11-16 08:00:00', 'check_out': '2026-11-16 10:00:00',
        })
        self._layout(summary=[('employee_name', 'FIRST COMPANY PERSON')], detail=['label'])
        self._layout(company=other, summary=[('paid_seconds', 'SECOND COMPANY HOURS'), ('employee_name', 'SECOND COMPANY PERSON')], detail=['label'])
        wizard = self._wizard(company_ids=(self.company | other).ids, employee_ids=[])
        wizard.action_export_xlsx()
        parts, ns, strings, sheets = self._xlsx(base64.b64decode(wizard.report_file))
        names = [node.attrib['name'] for node in parts['xl/workbook.xml'].findall('s:sheets/s:sheet', ns)]
        self.assertEqual(len(names), 4)
        self.assertEqual(len(set(names)), 4)
        self.assertTrue(all(len(name) <= 31 and not any(char in name for char in '[]:*?/\\') for name in names))
        self.assertEqual(self._text(sheets[0]['A5'], strings, ns), 'FIRST COMPANY PERSON')
        self.assertEqual(self._text(sheets[0]['A6'], strings, ns), self.employee.name)
        self.assertEqual(self._text(sheets[2]['A5'], strings, ns), 'SECOND COMPANY HOURS')
        self.assertEqual(self._text(sheets[2]['B6'], strings, ns), other_employee.name)
        self.assertTrue(attendance.exists() and second.exists())

    def test_latest_open_work_interval_never_inherits_previous_return(self):
        attendance = self._act('check_in', '2026-11-16 08:00:00')
        self._act('work_exit', '2026-11-16 10:00:00')
        self._act('work_return', '2026-11-16 10:30:00')
        self._act('work_exit', '2026-11-16 15:00:00')
        row = self.report._coir_dataset(attendance)['summary'][0]
        self.assertEqual(row['work_start'], datetime(2026, 11, 16, 15))
        self.assertIsNone(row['work_end'])
        self.assertEqual(row['work_state'], 'Regreso pendiente')
        self.assertEqual(row['work_seconds'], 1800)
        self.assertIsNone(row['paid_seconds'])

    def test_newer_open_meal_pair_replaces_old_closed_pair_across_journeys(self):
        complete = self._complete_day()
        self.env['coir.reentry.authorization'].create({
            'employee_id': self.employee.id, 'valid_date': '2026-11-16', 'reason': 'V42 extra authorized shift',
        })
        extra = self._act('check_in', '2026-11-16 20:00:00')
        self._act('meal_start', '2026-11-16 20:30:00')
        row = self.report._coir_dataset(complete | extra)['summary'][0]
        self.assertEqual(row['meal_start'], datetime(2026, 11, 16, 20, 30))
        self.assertIsNone(row['meal_end'])
        self.assertEqual(row['meal_state'], 'Regreso pendiente')
        self.assertEqual(row['meal_seconds'], 3600)
        self.assertEqual(row['paid_seconds'], 9 * 3600)

    def _native_overtime(self, attendance, duration, approved=True):
        line = self.env['hr.attendance.overtime.line'].create({
            'employee_id': self.employee.id, 'date': attendance.date,
            'time_start': attendance.check_in, 'time_stop': attendance.check_out,
            'duration': duration, 'manual_duration': duration, 'status': 'to_approve',
        })
        attendance.invalidate_recordset(['linked_overtime_ids'])
        # Native writes schedule native recomputations; the report never writes
        # overtime or simulates the validated attendance field.
        line.write({'status': 'approved' if approved else 'to_approve', 'manual_duration': duration})
        return line

    def test_native_approved_overtime_is_not_added_to_paid_hours_or_repeated(self):
        attendance = self._complete_day()
        self._native_overtime(attendance, 1.5)
        self._native_overtime(attendance, 2, approved=False)
        dataset = self.report._coir_dataset(attendance)
        self.assertEqual(attendance.validated_overtime_hours, 1.5)
        self.assertEqual(dataset['summary'][0]['overtime_seconds'], 5400)
        self.assertEqual(dataset['summary'][0]['paid_seconds'], 9 * 3600)
        overtime_events = [event for event in dataset['events'] if event['overtime_seconds'] is not None]
        self.assertEqual(len(overtime_events), 1)
        self.assertEqual(overtime_events[0]['label'], 'Salida final')
        self.assertEqual(overtime_events[0]['overtime_seconds'], 5400)

    def test_signed_native_overtime_remains_numeric_in_excel_and_correct_in_pdf(self):
        attendance = self._complete_day()
        self._native_overtime(attendance, -0.5)
        self._layout(summary=[('overtime_seconds', 'Horas extra aprobadas')], detail=['overtime_seconds'])
        self._layout('pdf', summary=[('overtime_seconds', 'Horas extra aprobadas')], detail=['label'])
        wizard = self._wizard()
        wizard.action_export_xlsx()
        parts, ns, strings, (summary, _detail) = self._xlsx(base64.b64decode(wizard.report_file))
        self.assertNotEqual(summary['A6'].attrib.get('t'), 's')
        self.assertAlmostEqual(float(summary['A6'].find('s:v', ns).text), -0.5 / 24)
        self.assertEqual(parts['xl/workbook.xml'].find('s:workbookPr', ns).attrib['date1904'], '1')
        self.assertEqual(self.report._format_seconds(-1800), '-00:30')
        self.assertIn('-00:30', self._render_html(attendance))

    def test_wide_pdf_uses_blocks_of_eight_and_never_adds_unselected_columns(self):
        attendance = self._complete_day()
        layout = self._layout('pdf')
        summary_keys = [line.column_key for line in layout.line_ids.filtered(lambda line: line.section == 'summary')]
        layout = self._layout('pdf', summary=summary_keys, detail=['label'])
        columns = self.env['coir.attendance.report.layout']._coir_get_columns(self.company, 'pdf', 'summary')
        blocks = self.report._coir_pdf_blocks(columns)
        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(len(block['columns']) <= 8 for block in blocks))
        self.assertEqual({column['key'] for block in blocks for column in block['columns']}, set(summary_keys))
        first_occurrences = []
        for block in blocks:
            for column in block['columns']:
                if column['key'] not in first_occurrences:
                    first_occurrences.append(column['key'])
        self.assertEqual(first_occurrences, [column['key'] for column in columns])
        rendered = self._render_html(attendance)
        root = html_parser.fromstring(rendered)
        self.assertEqual(len(root.xpath('//table[contains(@class, "coir-summary")]')), len(blocks))
        self.assertEqual(len(root.xpath('//table[contains(@class, "coir-detail")]/thead/tr/th')), 1)

    def test_copy_layout_to_other_format_is_applied_to_real_pdf(self):
        attendance = self._complete_day()
        layout = self._layout(summary=[('date', 'COPIED_DAY_V42')], detail=[('label', 'COPIED_MOVEMENT_V42')])
        layout.action_apply_to_other_format()
        rendered = self._render_html(attendance)
        self.assertIn('COPIED_DAY_V42', rendered)
        self.assertIn('COPIED_MOVEMENT_V42', rendered)
        self.assertNotIn(self.employee.name, rendered)
        self.assertNotIn(self.department.name, rendered)

    def test_custom_columns_never_restore_excluded_employee(self):
        attendance = self._complete_day()
        self._layout(summary=['employee_name'], detail=['label'])
        self._layout('pdf', summary=['employee_name'], detail=['label'])
        self.employee.coir_attendance_report_excluded = True
        with self.assertRaises(UserError):
            self._wizard().action_export_xlsx()
        with self.assertRaises(UserError):
            self.report._get_report_values(attendance.ids)
        self.assertTrue(attendance.exists())

    def test_falta_remains_red_when_all_status_columns_are_hidden(self):
        self.company.write({'coir_absence_enabled': True})
        self.env['coir.attendance.absence']._generate_for_day(
            self.company, date(2026, 11, 16), now=datetime(2026, 11, 16, 9),
        )
        notice = self.env['coir.attendance.absence'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-16'), ('state', '=', 'absent'),
        ])
        self.assertTrue(notice)
        self._layout(summary=['employee_name'], detail=['employee_name'])
        wizard = self._wizard()
        wizard.action_export_xlsx()
        parts, ns, strings, (summary, _detail) = self._xlsx(base64.b64decode(wizard.report_file))
        style = parts['xl/styles.xml'].findall('s:cellXfs/s:xf', ns)[int(summary['A6'].attrib['s'])]
        font = parts['xl/styles.xml'].findall('s:fonts/s:font', ns)[int(style.attrib['fontId'])]
        self.assertEqual(font.find('s:color', ns).attrib['rgb'], 'FF9C0006')
        self.assertEqual(self._text(summary['A6'], strings, ns), self.employee.name)
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))
