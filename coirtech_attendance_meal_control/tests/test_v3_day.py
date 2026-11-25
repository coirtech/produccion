from datetime import date
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCoirV3Day(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'auto_check_out': False, 'coir_meal_control_enabled': True,
            'coir_absence_enabled': True, 'coir_absence_tz': 'America/Mexico_City',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'COIRTECH daily projection calendar', 'company_id': cls.company.id,
            'tz': 'America/Mexico_City',
            'attendance_ids': [Command.clear()] + [Command.create({
                'name': 'Workday', 'dayofweek': str(day), 'day_period': 'morning',
                'hour_from': 8, 'hour_to': 17,
            }) for day in range(5)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Daily projection employee', 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id, 'tz': 'America/Mexico_City', 'ruleset_id': False,
        })
        cls.reader = new_test_user(
            cls.env, login='coir_v3_day_reader',
            groups='base.group_user,hr_attendance.group_hr_attendance_user',
            company_id=cls.company.id,
        )

    def _absence(self):
        self.env['coir.attendance.absence']._generate_for_day(
            self.company, date(2026, 11, 23), now=fields.Datetime.to_datetime('2026-11-23 15:00:00'),
        )
        return self.env['coir.attendance.absence'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23'),
        ])

    def _rows(self, user=None):
        model = self.env['coir.attendance.day']
        if user:
            model = model.with_user(user)
        return model.search([('employee_id', '=', self.employee.id), ('date', '=', '2026-11-23')])

    def _act(self, action, stamp):
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.to_datetime(stamp)):
            employee = self.employee.sudo()
            state = employee._coir_meal_state()
            return employee._coir_apply_meal_action(
                action, state['attendance_id'], state['state'], expected_revision=state['revision'],
            )

    def test_absence_is_visible_without_false_attendance_then_actual_entry_replaces_it(self):
        absence = self._absence()
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.id, absence.id * 2 + 1)
        self.assertTrue(rows.is_absence)
        self.assertEqual(rows.entry_display, 'FALTA')
        self.assertFalse(rows.attendance_id)
        self.assertFalse(rows.check_in)
        self.assertFalse(rows.check_out)
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)]))
        attendance = self._act('check_in', '2026-11-23 16:30:00')
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.is_absence)
        self.assertEqual(rows.id, attendance.id * 2)
        self.assertEqual(rows.attendance_id, attendance)
        self.assertFalse(rows.absence_id)
        self.assertEqual(rows.entry_display, '10:30:00')
        self.assertEqual(rows.action_open_source()['res_id'], attendance.id)

    def test_work_columns_are_the_last_pair_and_keep_return_empty_while_away(self):
        self._act('check_in', '2026-11-23 14:00:00')
        self._act('work_exit', '2026-11-23 16:00:00')
        self._act('work_return', '2026-11-23 16:30:00')
        self._act('work_exit', '2026-11-23 18:00:00')
        row = self._rows()
        self.assertEqual(row.coir_work_start, fields.Datetime.to_datetime('2026-11-23 18:00:00'))
        self.assertFalse(row.coir_work_end)
        self.assertEqual(row.coir_work_status, 'open')
        self.assertEqual(len(row.coir_work_outing_ids), 2)
        self._act('work_return', '2026-11-23 18:45:00')
        row = self._rows()
        self.assertEqual(row.coir_work_start, fields.Datetime.to_datetime('2026-11-23 18:00:00'))
        self.assertEqual(row.coir_work_end, fields.Datetime.to_datetime('2026-11-23 18:45:00'))
        self.assertEqual(row.coir_work_status, 'returned')
        self._act('meal_start', '2026-11-23 19:00:00')
        self.assertEqual(self._rows().coir_meal_status, 'open')
        self._act('meal_return', '2026-11-23 20:00:00')
        self.assertEqual(self._rows().coir_meal_status, 'returned')

    def test_projection_is_read_only_even_for_sudo(self):
        self._absence()
        row = self._rows()
        with self.assertRaises(AccessError):
            row.write({'check_in': '2026-11-23 14:00:00'})
        with self.assertRaises(AccessError):
            row.unlink()
        with self.assertRaises(AccessError):
            self.env['coir.attendance.day'].create({'employee_id': self.employee.id})

    def test_original_attendance_rule_applies_to_search_direct_read_and_grouping(self):
        attendance = self._act('check_in', '2026-11-23 14:00:00')
        row = self._rows(self.reader)
        self.assertEqual(len(row), 1)
        self.env['ir.rule'].create({
            'name': 'Test block original attendance only',
            'model_id': self.env['ir.model']._get_id('hr.attendance'),
            'domain_force': "[('id', '!=', %s)]" % attendance.id,
        })
        self.assertFalse(self._rows(self.reader))
        with self.assertRaises(AccessError):
            row.check_access('read')
        with self.assertRaises(AccessError):
            row.read(['entry_display'])
        grouped = self.env['coir.attendance.day'].with_user(self.reader)._read_group(
            [('employee_id', '=', self.employee.id)], ['employee_id'], ['__count'],
        )
        self.assertFalse(grouped)

    def test_original_absence_rule_applies_and_cannot_be_opened_indirectly(self):
        absence = self._absence()
        row = self._rows(self.reader)
        self.assertEqual(len(row), 1)
        self.env['ir.rule'].create({
            'name': 'Test block original absence only',
            'model_id': self.env['ir.model']._get_id('coir.attendance.absence'),
            'domain_force': "[('id', '!=', %s)]" % absence.id,
        })
        self.assertFalse(self._rows(self.reader))
        with self.assertRaises(AccessError):
            row.action_open_source()
        with self.assertRaises(AccessError):
            row.read(['employee_id', 'entry_display'])

    def test_view_changes_only_status_badges_and_absence_cell_colors(self):
        view = self.env.ref('coirtech_attendance_meal_control.attendance_day_list')
        from lxml import etree
        arch = etree.fromstring(view.arch_db.encode())
        self.assertFalse(any(name.startswith('decoration-') for name in arch.attrib))
        self.assertEqual(arch.xpath("//field[@name='entry_display']")[0].get('decoration-danger'), 'is_absence')
        for name in ('coir_meal_status', 'coir_work_status'):
            node = arch.xpath("//field[@name='%s']" % name)[0]
            self.assertEqual(node.get('widget'), 'badge')
            self.assertIn('open', node.get('decoration-danger'))
            self.assertIn('missing', node.get('decoration-danger'))
            self.assertIn('returned', node.get('decoration-success'))
        self.assertEqual(self.env.ref('coirtech_attendance_meal_control.attendance_meal_action').name, 'Reporte de asistencia')
        self.assertEqual(self.env.ref('coirtech_attendance_meal_control.attendance_meal_menu').name, 'Reporte de asistencia')
