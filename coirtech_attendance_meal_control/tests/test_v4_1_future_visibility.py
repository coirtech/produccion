"""V4.1: future approved time off is not projected in COIRTECH reports.

This suite is intended to run under Odoo 19 with --test-enable.  The timezone
cutoff is deliberately compared to the real database clock: SQL views and the
ORM must agree even when an export is driven directly from stored source IDs.
"""
import base64
import io
from datetime import datetime, time, timedelta
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

import pytz

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV41NoFutureTimeOff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False,
            'coir_meal_control_enabled': True,
            'coir_absence_enabled': True,
            'coir_absence_tz': 'America/Mexico_City',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'COIRTECH V4.1 future visibility schedule',
            'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day),
                'day_period': 'morning', 'hour_from': 8, 'hour_to': 17,
            # This fixture works on every weekday so the visibility contract
            # can be checked on any real test date.  It does not change the
            # production rule forbidding automatic FALTA on Saturday/Sunday.
            }) for day in range(7)],
        })

    def setUp(self):
        super().setUp()
        # SQL CURRENT_TIMESTAMP is fixed at transaction start.  Use that same
        # instant for the Python guard instead of freezing an unrelated date.
        self.env.cr.execute("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")
        self.database_now = self.env.cr.fetchone()[0]
        clock = patch.object(fields.Datetime, 'now', return_value=self.database_now)
        clock.start()
        self.addCleanup(clock.stop)

    def _next_workday(self):
        utc_now = fields.Datetime.to_datetime(fields.Datetime.now())
        local_today = pytz.UTC.localize(utc_now).astimezone(
            pytz.timezone('America/Mexico_City'),
        ).date()
        future = local_today + timedelta(days=1)
        while future.weekday() >= 5:
            future += timedelta(days=1)
        return local_today, future

    def _approved_source(self, category, day, end_day=None):
        employee = self.env['hr.employee'].create({
            'name': 'V4.1 future employee %s' % category,
            'company_id': self.company.id,
            'resource_calendar_id': self.calendar.id,
            'tz': 'America/Mexico_City',
            'ruleset_id': False,
        })
        leave_type = self.env['hr.leave.type'].create({
            'name': 'V4.1 future category %s' % category,
            'requires_allocation': False,
            'leave_validation_type': 'no_validation',
            'request_unit': 'day',
            'coir_attendance_category': category,
        })
        leave = self.env['hr.leave'].create({
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': day,
            'request_date_to': end_day or day,
        })
        self.assertEqual(leave.state, 'validate')
        self.env['coir.attendance.absence']._sync_approved_leaves(
            date_from=day, date_to=end_day or day, company_ids=[self.company.id],
        )
        source = self.env['coir.attendance.absence'].search([
            ('employee_id', '=', employee.id), ('date', '>=', day),
            ('date', '<=', end_day or day),
        ], order='date')
        self.assertTrue(source, 'Keep the approved source even while hidden from report')
        self.assertTrue(set(source.mapped('state')).issubset({'approved', 'partial', 'review'}))
        return employee, leave, source

    def _wizard(self, employee, start, end, **values):
        return self.env['coir.attendance.report.wizard'].create({
            'date_from': start, 'date_to': end,
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(employee.ids)],
            **values,
        })

    def _report(self):
        return self.env['report.coirtech_attendance_meal_control.report_meal_journeys']

    def _assert_not_projected(self, source):
        day_model = self.env['coir.attendance.day']
        domain = [('absence_id', 'in', source.ids)]
        self.assertFalse(day_model.search(domain))
        self.assertEqual(day_model.search_count(domain), 0)
        self.assertFalse(day_model._read_group(domain, ['employee_id'], ['__count', 'leave_hours:sum']))
        known = day_model.browse([notice.id * 2 + 1 for notice in source])
        self.assertEqual(known.read(['id', 'report_label', 'leave_hours']), [])
        self.assertEqual(known.sudo().read(['id']), [])
        self.assertFalse(source._coir_visible_in_report())

    def test_four_future_categories_hidden_in_list_search_grouping_and_exports(self):
        _today, future = self._next_workday()
        for category in ('vacation', 'paid_absence', 'unpaid_absence', 'disability'):
            with self.subTest(category=category):
                employee, leave, source = self._approved_source(category, future)
                self._assert_not_projected(source)
                for wizard in (
                    self._wizard(employee, future, future),
                    self._wizard(employee, future, future, selection_only=True,
                                 absence_ids=[Command.set(source.ids)]),
                ):
                    self.assertFalse(wizard._get_absences())
                    with self.assertRaises(UserError):
                        wizard._get_report_records()
                    with self.assertRaises(UserError):
                        wizard.action_export_xlsx()
                    with self.assertRaises(UserError):
                        wizard.action_print_pdf()
                with self.assertRaises(UserError):
                    self._report()._coir_dataset(self.env['hr.attendance'], source)
                with self.assertRaises(UserError):
                    self._report()._get_report_values([], data={
                        'coir_attendance_ids': [], 'coir_absence_ids': source.ids,
                    })
                self.assertEqual(leave.state, 'validate')
                self.assertTrue(source.exists())

    def test_today_is_not_hidden(self):
        today, _future = self._next_workday()
        employee, leave, source = self._approved_source('disability', today)
        self.assertEqual(source._coir_visible_in_report(), source)
        rows = self.env['coir.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', today),
        ])
        self.assertEqual(rows.absence_id, source)
        self.assertEqual(len(rows.read(['date', 'report_label'])), 1)
        self.assertFalse(rows.check_in)
        self.assertEqual(leave.state, 'validate')

    def test_spanning_approved_leave_exports_past_and_today_only(self):
        today, _future = self._next_workday()
        start, end = today - timedelta(days=2), today + timedelta(days=2)
        employee, leave, source = self._approved_source('disability', start, end)
        self.assertEqual(len(source), 5)
        visible = source.filtered(lambda notice: notice.date <= today)
        future = source - visible
        self.assertEqual(len(visible), 3)
        self._assert_not_projected(future)
        # Viewer timezone cannot move the company/snapshot date boundary.
        for viewer_timezone in ('Pacific/Kiritimati', 'Pacific/Pago_Pago'):
            self.assertEqual(source.with_context(tz=viewer_timezone)._coir_visible_in_report(), visible)
        rows = self.env['coir.attendance.day'].search([('employee_id', '=', employee.id)])
        self.assertEqual(set(rows.absence_id.ids), set(visible.ids))
        grouped = self.env['coir.attendance.day']._read_group(
            [('employee_id', '=', employee.id)], ['employee_id'], ['__count', 'leave_hours:sum'],
        )
        self.assertEqual(grouped[0][1], 3)
        self.assertAlmostEqual(grouped[0][2], sum(visible.mapped('leave_hours')))
        wizard = self._wizard(employee, start, end)
        attendances, notices = wizard._get_report_records()
        self.assertFalse(attendances)
        self.assertEqual(set(notices.ids), set(visible.ids))
        dataset = self._report()._coir_dataset(attendances, source)
        self.assertEqual({row['date'] for row in dataset['summary']}, set(visible.mapped('date')))
        pdf = self._report()._get_report_values([], data={
            'coir_attendance_ids': [], 'coir_absence_ids': source.ids,
        })
        self.assertEqual(
            {row['date'] for batch in pdf['batches'] for row in batch['summary']},
            set(visible.mapped('date')),
        )
        wizard.action_export_xlsx()
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(base64.b64decode(wizard.report_file))) as archive:
            workbook = ElementTree.fromstring(archive.read('xl/workbook.xml'))
            properties = workbook.find('s:workbookPr', ns)
            date_1904 = properties is not None and properties.attrib.get('date1904') in ('1', 'true')
            epoch = datetime(1904, 1, 1) if date_1904 else datetime(1899, 12, 30)
            for sheet in ('xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml'):
                tree = ElementTree.fromstring(archive.read(sheet))
                date_values = [
                    float(cell.find('s:v', ns).text)
                    for row in tree.findall('.//s:sheetData/s:row', ns) if int(row.attrib['r']) >= 6
                    for cell in row.findall('s:c', ns)
                    if cell.attrib['r'].startswith('D') and cell.find('s:v', ns) is not None
                ]
                dates = {(epoch + timedelta(days=value)).date() for value in date_values}
                self.assertEqual(dates, set(visible.mapped('date')))
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.request_date_to, end)
        self.assertEqual(len(source.exists()), 5)
        self.assertEqual(set(source.mapped('state')), {'approved'})
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', employee.id)]))

    def test_saved_timezones_control_visibility_across_the_date_line(self):
        # Opposite sides of the international date line always have different
        # local dates at the same database instant.  The stored snapshot must
        # win over the viewer and over a later company-timezone change.
        zones = ('Pacific/Kiritimati', 'Etc/GMT+12')
        now = pytz.UTC.localize(self.database_now)
        local_dates = {zone: now.astimezone(pytz.timezone(zone)).date() for zone in zones}
        target_date = max(local_dates.values())
        self.assertGreater(target_date, min(local_dates.values()))
        sources = self.env['coir.attendance.absence']
        for zone in zones:
            employee = self.env['hr.employee'].create({
                'name': 'V4.1 timezone snapshot %s' % zone,
                'company_id': self.company.id, 'resource_calendar_id': self.calendar.id,
                'tz': 'UTC', 'ruleset_id': False,
            })
            begin = pytz.timezone(zone).localize(datetime.combine(target_date, time(8)))
            source = self.env['coir.attendance.absence']._service().create({
                'employee_id': employee.id, 'company_id': self.company.id,
                'date': target_date, 'timezone': zone, 'state': 'approved',
                'leave_label': 'INCAPACIDAD', 'leave_hours': 9,
                'was_automatic_absence': False, 'generated_at': self.database_now,
                'start_datetime': begin.astimezone(pytz.UTC).replace(tzinfo=None),
                'end_datetime': (begin + timedelta(hours=9)).astimezone(pytz.UTC).replace(tzinfo=None),
            })
            sources |= source
        self.company.coir_absence_tz = 'UTC'
        visible = sources.filtered(lambda notice: notice.date <= local_dates[notice.timezone])
        future = sources - visible
        self.assertEqual(len(visible), 1)
        self._assert_not_projected(future)
        self.assertEqual(sources.with_context(tz='Pacific/Pago_Pago')._coir_visible_in_report(), visible)
        rows = self.env['coir.attendance.day'].search([('absence_id', 'in', sources.ids)])
        self.assertEqual(rows.absence_id, visible)
        dataset = self._report()._coir_dataset(self.env['hr.attendance'], sources)
        self.assertEqual(dataset['absences'], visible)
        self.assertEqual(len(sources.exists()), 2)

    def test_future_unmapped_partial_and_review_indicators_are_also_hidden(self):
        _today, future = self._next_workday()
        _employee, leave, source = self._approved_source(False, future)
        self.assertEqual(source.report_label, leave.holiday_status_id.name)
        self._assert_not_projected(source)
        for state in ('partial', 'review'):
            source._service().write({'state': state, 'review_reason': 'Review fixture'})
            self._assert_not_projected(source)
            with self.assertRaises(UserError):
                self._report()._get_report_values([], data={'coir_absence_ids': source.ids})
        self.assertEqual(leave.state, 'validate')
        self.assertTrue(source.exists())
