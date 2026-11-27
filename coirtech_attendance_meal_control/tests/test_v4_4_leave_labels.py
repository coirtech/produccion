"""V4.4 regressions: native type identity vs translated labels."""
from datetime import datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'coir_v44')
class TestCoirV44TypeLabels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.country_mx = cls.env['res.country'].search([('code', '=', 'MX')], limit=1)
        assert cls.country_mx
        cls.env['res.lang']._activate_lang('es_MX')
        cls.company.write({
            'country_id': cls.country_mx.id,
            'auto_check_out': False,
            'coir_meal_control_enabled': True,
            'coir_absence_enabled': True,
            'coir_absence_tz': 'America/Mexico_City',
            'coir_absence_tracking_started_at': '2026-11-01 00:00:00',
        })
        # This was the root of the language mismatch: the company contact may
        # still use English while Time Off types are renamed in Spanish.
        cls.company.partner_id.lang = 'en_US'
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'V4.4 work calendar', 'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day),
                'day_period': 'morning', 'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.employee = cls._employee('V4.4 employee A')
        cls.employee2 = cls._employee('V4.4 employee B')
        cls.Absence = cls.env['coir.attendance.absence']

    @classmethod
    def _employee(cls, name):
        return cls.env['hr.employee'].create({
            'name': name, 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id, 'ruleset_id': False,
            'tz': 'America/Mexico_City',
        })

    def _type(self, name):
        return self.env['hr.leave.type'].with_context(lang='en_US').create({
            'name': name, 'company_id': self.company.id,
            'requires_allocation': False, 'leave_validation_type': 'hr',
            'request_unit': 'day',
        })

    def _leave(self, employee, leave_type):
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 11, 23, 16, 0, 0)):
            return self.env['hr.leave'].create({
                'employee_id': employee.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': '2026-11-23',
                'request_date_to': '2026-11-23',
            })

    def _notice(self, employee):
        return self.Absence.search([
            ('employee_id', '=', employee.id),
            ('date', '=', '2026-11-23'),
        ], limit=1)

    def _sync(self):
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 11, 24, 16)):
            # Simulate the scheduler running as a user whose UI is English.
            self.Absence.with_context(lang='en_US')._sync_approved_leaves(
                '2026-11-23', '2026-11-23', self.company.ids,
            )

    def test_translated_vacation_not_english_home_office(self):
        leave_type = self._type('Home Office')
        leave_type.with_context(lang='es_MX').write({'name': 'Vacaciones'})
        self.assertEqual(leave_type.with_context(lang='en_US').name, 'Home Office')
        self.assertEqual(leave_type.with_context(lang='es_MX').name, 'Vacaciones')
        leave = self._leave(self.employee, leave_type)
        self._sync()
        notice = self._notice(self.employee)
        self.assertEqual(notice.leave_ids, leave)
        self.assertEqual(leave.holiday_status_id.id, leave_type.id)
        self.assertEqual(notice.leave_label, 'Vacaciones')
        self.assertEqual(notice.report_label, 'Vacaciones')
        self.assertEqual(notice.leave_hours, 0)  # Still pending.
        self.assertNotIn('Home Office', notice.leave_periods)
        self.assertIn('Vacaciones', notice.leave_periods)

        # Reconcile an already materialized old V4.3 wrong label.
        notice._service().write({
            'leave_label': 'Home Office',
            'leave_periods': '08:00–17:00 (Home Office)',
        })
        self.assertEqual(notice.report_label, 'Home Office')
        self._sync()
        self.assertEqual(notice.leave_label, 'Vacaciones')
        self.assertEqual(notice.report_label, 'Vacaciones')
        day = self.env['coir.attendance.day'].search([('absence_id', '=', notice.id)])
        self.assertEqual(day.report_label, 'Vacaciones')

        wizard = self.env['coir.attendance.report.wizard'].create({
            'date_from': '2026-11-23', 'date_to': '2026-11-23',
            'company_ids': [Command.set(self.company.ids)],
            'employee_ids': [Command.set(self.employee.ids)],
        })
        docs, notices = wizard._get_report_records()
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(docs, notices)
        self.assertEqual(dataset['summary'][0]['notice_label'], 'Vacaciones')
        self.assertEqual(dataset['summary'][0]['leave_label'], 'Vacaciones')

    def test_two_case_distinct_vacation_types_do_not_mix_employees(self):
        upper = self._type('Vacaciones')
        lower = self._type('vacaciones')
        home = self._type('Home Office')
        self.assertNotEqual(upper.id, lower.id)
        self.assertNotEqual(upper.id, home.id)
        first = self._leave(self.employee, upper)
        second = self._leave(self.employee2, lower)
        self._sync()
        notice_a = self._notice(self.employee)
        notice_b = self._notice(self.employee2)
        self.assertEqual(notice_a.leave_ids, first)
        self.assertEqual(notice_b.leave_ids, second)
        self.assertEqual(notice_a.leave_label, 'Vacaciones')
        self.assertEqual(notice_b.leave_label, 'vacaciones')
        self.assertNotIn('Home Office', notice_a.report_label)
        self.assertNotIn('Home Office', notice_b.report_label)

        # Changing the actual Time Off type ID updates the correct employee,
        # and cannot carry the other employee's label across.
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 11, 23, 17)):
            second.write({'holiday_status_id': upper.id})
        self._sync()
        self.assertEqual(self._notice(self.employee2).leave_label, 'Vacaciones')
        self.assertEqual(self._notice(self.employee).leave_label, 'Vacaciones')
        self.assertEqual(self._notice(self.employee2).leave_ids, second)

    def test_non_mexico_uses_configured_company_language(self):
        company = self.company
        country = self.env['res.country'].search([('code', '=', 'US')], limit=1)
        company.country_id = country.id
        company.partner_id.lang = 'en_US'
        self.assertEqual(self.Absence._coir_leave_type_report_language(company), 'en_US')
        company.partner_id.lang = 'es_MX'
        self.assertEqual(self.Absence._coir_leave_type_report_language(company), 'es_MX')
