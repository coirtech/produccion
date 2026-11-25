"""V4 native-source projection, exclusion boundary and neutral leave display."""
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV4Day(TransactionCase):
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
            'name': 'COIRTECH V4 day schedule', 'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'V4 day employee', 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id, 'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        cls.reader = new_test_user(
            cls.env, login='coir_v4_day_reader',
            groups='base.group_user,hr_attendance.group_hr_attendance_user', company_id=cls.company.id,
        )

    def setUp(self):
        super().setUp()
        clock = patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime('2026-11-24 00:00:00'))
        clock.start()
        self.addCleanup(clock.stop)

    def _leave(self, hours=None, approval='no_validation', category='vacation'):
        leave_type = self.env['hr.leave.type'].create({
            'name': 'V4 day native leave', 'requires_allocation': False,
            'leave_validation_type': approval, 'request_unit': 'hour' if hours else 'day',
            'coir_attendance_category': category,
        })
        values = {
            'employee_id': self.employee.id, 'holiday_status_id': leave_type.id,
            'request_date_from': '2026-11-23', 'request_date_to': '2026-11-23',
        }
        if hours:
            values.update(request_hour_from=hours[0], request_hour_to=hours[1])
        return self.env['hr.leave'].create(values)

    def _rows(self, user=None):
        model = self.env['coir.attendance.day']
        return (model.with_user(user) if user else model).search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23'),
        ])

    def _attendance(self):
        return self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-11-23 19:00:00', 'check_out': '2026-11-23 23:00:00',
            'in_mode': 'manual', 'out_mode': 'manual',
        })

    def test_approved_leave_has_own_readonly_row_without_a_fake_clock_time(self):
        self._leave()
        row = self._rows()
        self.assertEqual(len(row), 1)
        self.assertTrue(row.is_indicator)
        self.assertFalse(row.is_absence)
        self.assertEqual(row.indicator_state, 'approved')
        self.assertEqual(row.report_label, 'VACACIONES')
        self.assertFalse(row.entry_display)
        self.assertFalse(row.check_in)
        self.assertFalse(row.attendance_id)
        self.assertEqual(row.leave_hours, 9)
        self.assertEqual(row.id, row.absence_id.id * 2 + 1)
        self.assertEqual(row.action_open_source()['res_model'], 'coir.attendance.absence')

    def test_real_entry_and_partial_permission_coexist_without_duplicate_worked_hours(self):
        self._leave(hours=(8, 13))
        attendance = self._attendance()
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        real = rows.filtered('attendance_id')
        permission = rows.filtered('is_indicator')
        self.assertEqual(real.attendance_id, attendance)
        self.assertEqual(real.entry_display, '13:00:00')
        self.assertEqual(permission.indicator_state, 'partial')
        self.assertFalse(permission.entry_display)
        self.assertFalse(permission.is_absence)
        grouped = self.env['coir.attendance.day']._read_group(
            [('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23')], [],
            ['worked_hours:sum', 'leave_hours:sum'],
        )
        self.assertAlmostEqual(grouped[0][0], attendance.worked_hours)
        self.assertEqual(grouped[0][1], 5)

    def test_exclusion_applies_to_cached_ids_search_grouping_and_sudo(self):
        self._leave(hours=(8, 13))
        attendance = self._attendance()
        rows = self._rows()
        rows.read(['entry_display', 'report_label'])
        self.employee.coir_attendance_report_excluded = True
        self.assertFalse(self._rows())
        self.assertFalse(self._rows(self.reader))
        # Native SQL-view reads omit rows which no longer exist in the view.
        # The requirement is an empty response, including cached and sudo IDs.
        self.assertEqual(rows.read(['entry_display', 'report_label']), [])
        self.assertEqual(rows.sudo().read(['entry_display', 'report_label']), [])
        self.assertEqual(rows.sudo().read(['id']), [])
        self.assertEqual(rows.with_user(self.reader).read(['entry_display', 'report_label']), [])
        grouped = self.env['coir.attendance.day']._read_group(
            [('employee_id', '=', self.employee.id)], ['employee_id'], ['__count'],
        )
        self.assertFalse(grouped)
        self.assertTrue(attendance.exists())
        self.assertEqual(attendance.check_in, fields.Datetime.to_datetime('2026-11-23 19:00:00'))
        self.employee.coir_attendance_report_excluded = False
        self.assertEqual(len(self._rows()), 2)

    def test_notice_source_rule_cannot_be_bypassed_by_access_to_real_journey(self):
        self._leave(hours=(8, 13))
        attendance = self._attendance()
        before = self._rows(self.reader)
        self.assertEqual(len(before), 2)
        notice_row = before.filtered('is_indicator')
        self.env['ir.rule'].create({
            'name': 'Block original V4 permission row',
            'model_id': self.env['ir.model']._get_id('coir.attendance.absence'),
            'domain_force': "[('id', '!=', %s)]" % notice_row.absence_id.id,
        })
        after = self._rows(self.reader)
        self.assertEqual(after.attendance_id.ids, attendance.ids)
        self.assertFalse(after.is_indicator)
        with self.assertRaises(AccessError):
            notice_row.read(['report_label', 'leave_periods'])

    def test_pending_request_is_not_justification_until_final_approval(self):
        leave = self._leave(approval='hr')
        self.assertEqual(leave.state, 'confirm')
        self.env['coir.attendance.absence']._generate_for_day(
            self.company, fields.Date.to_date('2026-11-23'),
            now=fields.Datetime.to_datetime('2026-11-23 15:00:00'),
        )
        row = self._rows()
        self.assertTrue(row.is_absence)
        self.assertEqual(row.entry_display, 'FALTA')
        row_id = row.id
        leave.action_approve()
        row = self._rows()
        self.assertEqual(row.id, row_id)
        self.assertEqual(row.indicator_state, 'approved')
        self.assertFalse(row.is_absence)
        self.assertFalse(row.entry_display)
        self.assertEqual(row.report_label, 'VACACIONES')

    def test_approved_and_review_columns_have_no_custom_red_or_green_decoration(self):
        view = self.env.ref('coirtech_attendance_meal_control.attendance_day_list')
        arch = etree.fromstring(view.arch_db.encode())
        for name in ('report_label', 'leave_periods', 'leave_hours', 'review_reason'):
            node = arch.xpath("//field[@name='%s']" % name)[0]
            self.assertFalse(any(key.startswith('decoration-') for key in node.attrib))
        self.assertEqual(arch.xpath("//field[@name='entry_display']")[0].get('decoration-danger'), 'is_absence')
        for name in ('coir_meal_status', 'coir_work_status'):
            node = arch.xpath("//field[@name='%s']" % name)[0]
            self.assertIn('open', node.get('decoration-danger'))
            self.assertIn('returned', node.get('decoration-success'))
