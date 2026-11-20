import base64
import io
from datetime import datetime, time

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class CoirAttendanceReportWizard(models.TransientModel):
    _name = 'coir.attendance.report.wizard'
    _description = 'Reporte COIRTECH de asistencias y movimientos'

    date_from = fields.Date(
        string='Fecha laboral desde', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(string='Fecha laboral hasta', required=True, default=fields.Date.context_today)
    company_ids = fields.Many2many(
        'res.company', string='Empresas', required=True,
        default=lambda self: self.env.companies,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],
    )
    employee_ids = fields.Many2many('hr.employee', string='Empleados')
    department_ids = fields.Many2many('hr.department', string='Departamentos')
    attendance_ids = fields.Many2many(
        'hr.attendance', string='Jornadas seleccionadas', readonly=True,
        help='Si hay jornadas seleccionadas, se aplica el periodo y los filtros solamente a esa selección.',
    )
    report_file = fields.Binary(string='Archivo Excel', readonly=True, attachment=False)
    report_filename = fields.Char(string='Nombre del archivo', readonly=True)

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        if self.env.context.get('active_model') == 'hr.attendance' and self.env.context.get('active_ids'):
            records = self.env['hr.attendance'].browse(self.env.context['active_ids']).exists()
            records.check_access('read')
            records = records.filtered('coir_managed')
            if records:
                if 'attendance_ids' in names:
                    values['attendance_ids'] = [(6, 0, records.ids)]
                if 'date_from' in names:
                    values['date_from'] = min(records.mapped('date'))
                if 'date_to' in names:
                    values['date_to'] = max(records.mapped('date'))
                if 'company_ids' in names:
                    values['company_ids'] = [(6, 0, records.coir_company_id.ids)]
        return values

    @api.onchange('company_ids')
    def _onchange_companies(self):
        self.employee_ids = self.employee_ids.filtered(lambda employee: employee.company_id in self.company_ids)
        self.department_ids = self.department_ids.filtered(lambda department: department.company_id in self.company_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_('La fecha inicial no puede ser posterior a la fecha final.'))

    def _get_attendances(self):
        self.ensure_one()
        self.check_access('read')
        if not self.env.user.has_group('hr_attendance.group_hr_attendance_officer'):
            raise AccessError(_('No tienes permiso para consultar este reporte.'))
        if not self.company_ids:
            raise ValidationError(_('Selecciona por lo menos una empresa.'))
        if self.company_ids - self.env.companies:
            raise AccessError(_('Selecciona empresas habilitadas en tu sesión y autorizadas para tu usuario.'))
        if self.employee_ids.filtered(lambda employee: employee.company_id not in self.company_ids):
            raise ValidationError(_('Los empleados deben pertenecer a las empresas seleccionadas.'))
        if self.department_ids.filtered(lambda department: department.company_id not in self.company_ids):
            raise ValidationError(_('Los departamentos deben pertenecer a las empresas seleccionadas.'))
        domain = [
            ('coir_managed', '=', True), ('coir_company_id', 'in', self.company_ids.ids),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.attendance_ids:
            self.attendance_ids.check_access('read')
            domain.append(('id', 'in', self.attendance_ids.ids))
        records = self.env['hr.attendance'].search(domain, order='check_in, id')
        if not records:
            raise UserError(_('No hay jornadas COIRTECH para los filtros seleccionados.'))
        return records

    def action_print_pdf(self):
        records = self._get_attendances()
        return self.env.ref('coirtech_attendance_meal_control.action_report_meal').report_action(records)

    def action_export_xlsx(self):
        self.ensure_one()
        records = self._get_attendances()
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(records)
        content = self._build_xlsx(dataset)
        filename = 'COIRTECH_Asistencias_%s_%s.xlsx' % (self.date_from, self.date_to)
        self.write({'report_file': base64.b64encode(content), 'report_filename': filename})
        return {
            'type': 'ir.actions.act_url', 'target': 'download',
            'url': '/web/content/coir.attendance.report.wizard/%s/report_file/%s?download=true' % (self.id, filename),
        }

    def _build_xlsx(self, dataset):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False,
        })
        workbook.set_properties({'title': 'COIRTECH — Asistencias y movimientos', 'company': 'COIRTECH'})
        common = {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter'}
        formats = {
            'title': workbook.add_format({**common, 'font_size': 20, 'bold': True, 'font_color': '#174D3A'}),
            'subtitle': workbook.add_format({**common, 'font_color': '#425766', 'text_wrap': True}),
            'note': workbook.add_format({**common, 'font_size': 10, 'font_color': '#425766', 'text_wrap': True}),
            'header': workbook.add_format({**common, 'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#17513C', 'text_wrap': True, 'border': 1, 'border_color': '#D8E2DE'}),
            'text': workbook.add_format({**common, 'text_wrap': True}),
            'date': workbook.add_format({**common, 'num_format': 'dd/mm/yyyy'}),
            'datetime': workbook.add_format({**common, 'num_format': 'dd/mm/yyyy hh:mm'}),
            'integer': workbook.add_format({**common, 'num_format': '0'}),
            'duration': workbook.add_format({**common, 'num_format': '[h]:mm'}),
            'pending': workbook.add_format({**common, 'font_color': '#7A4B10', 'bg_color': '#FFF4DC', 'text_wrap': True}),
        }

        def setup(sheet, title, headers, widths, note):
            last_col = len(headers) - 1
            sheet.hide_gridlines(2)
            sheet.set_tab_color('#17513C')
            sheet.merge_range(0, 0, 0, last_col, title, formats['title'])
            sheet.set_row(0, 30)
            period = 'Fecha laboral: %s a %s · Empresas: %s' % (
                self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y'),
                ', '.join(self.company_ids.mapped('name')),
            )
            sheet.merge_range(1, 0, 1, last_col, period, formats['subtitle'])
            sheet.set_row(1, 30)
            sheet.merge_range(2, 0, 2, last_col, note, formats['note'])
            sheet.set_row(2, 38)
            for col, (header, width) in enumerate(zip(headers, widths)):
                sheet.write_string(4, col, header, formats['header'])
                sheet.set_column(col, col, width)
            sheet.set_row(4, 44)
            sheet.freeze_panes(5, 2)
            sheet.set_landscape()
            sheet.set_paper(9)
            # Two horizontal pages retain readable type for the complete detail.
            sheet.fit_to_pages(2, 0)
            sheet.repeat_rows(0, 4)
            sheet.repeat_columns(0, 1)
            sheet.set_margins(0.25, 0.25, 0.4, 0.4)
            sheet.set_footer('&LCOIRTECH — Asistencias&C&P / &N&RConfidencial')

        def write(sheet, row, col, value, kind='text'):
            fmt = formats[kind]
            if value is None or value is False:
                sheet.write_blank(row, col, None, fmt)
            elif kind == 'date':
                sheet.write_datetime(row, col, datetime.combine(value, time.min), fmt)
            elif kind == 'datetime':
                sheet.write_datetime(row, col, value, fmt)
            elif kind == 'duration':
                sheet.write_number(row, col, value / 86400, fmt)
            elif kind == 'integer':
                sheet.write_number(row, col, value, fmt)
            else:
                sheet.write_string(row, col, str(value), fmt)

        summary_sheet = workbook.add_worksheet('Resumen')
        summary_columns = [
            ('Empresa', 24, 'company_name', 'text'), ('Empleado', 27, 'employee_name', 'text'),
            ('Departamento', 22, 'department', 'text'), ('Fecha laboral', 14, 'date', 'date'),
            ('Zona horaria efectiva', 25, 'timezone', 'text'),
            ('Primera entrada', 21, 'first_entry', 'datetime'), ('Última salida final registrada', 23, 'last_exit', 'datetime'),
            ('Jornadas', 12, 'journeys', 'integer'), ('Cerradas', 12, 'closed', 'integer'), ('Abiertas', 12, 'open', 'integer'),
            ('Horas de jornadas cerradas (h:mm)', 23, 'paid_seconds', 'duration'),
            ('Comida confirmada (h:mm)', 22, 'meal_seconds', 'duration'),
            ('Salidas de trabajo confirmadas (h:mm)', 25, 'work_seconds', 'duration'),
            ('Comidas pendientes', 18, 'meal_pending', 'integer'), ('Salidas pendientes', 18, 'work_pending', 'integer'),
            ('Estado del resumen', 31, 'status', 'text'), ('Jornadas revisadas por RH', 22, 'reviewed', 'integer'),
        ]
        setup(summary_sheet, 'COIRTECH — Resumen de asistencias',
              [col[0] for col in summary_columns], [col[1] for col in summary_columns],
              'Comida y salidas de trabajo pagadas: ya están incluidas en las horas de jornada. No se suman nuevamente. '
              'Si hay jornadas abiertas, las horas cerradas son un subtotal parcial. Una duración sin confirmar se deja vacía.')
        for row_index, item in enumerate(dataset['summary'], start=5):
            summary_sheet.set_row(row_index, 34)
            for col_index, (header, width, key, kind) in enumerate(summary_columns):
                actual_kind = 'pending' if key == 'status' and (item['open'] or item['meal_pending'] or item['work_pending']) else kind
                write(summary_sheet, row_index, col_index, item[key], actual_kind)
        summary_sheet.autofilter(4, 0, 4 + len(dataset['summary']), len(summary_columns) - 1)
        summary_sheet.print_area(0, 0, 4 + len(dataset['summary']), len(summary_columns) - 1)

        detail_sheet = workbook.add_worksheet('Detalle')
        detail_columns = [
            ('Empresa', 24, 'company_name', 'text'), ('Empleado', 27, 'employee_name', 'text'),
            ('Departamento', 22, 'department', 'text'), ('Fecha laboral', 14, 'date', 'date'),
            ('Jornada ID', 13, 'journey_id', 'integer'), ('Movimiento', 23, 'label', 'text'),
            ('Fecha y hora local', 22, 'local_stamp', 'datetime'), ('Zona horaria efectiva', 25, 'timezone', 'text'),
            ('Fecha y hora UTC', 22, 'stamp', 'datetime'), ('Referencia del intervalo', 23, 'reference', 'text'),
            ('Comida / salida confirmada (h:mm)', 25, 'interval_seconds', 'duration'),
            ('Horas de jornada al cierre (h:mm)', 25, 'journey_seconds', 'duration'),
            ('Estado del intervalo / jornada', 31, 'interval_state', 'text'),
            ('Jornada revisada por RH', 22, 'reviewed', 'text'), ('Último motivo de revisión', 45, 'review_note', 'text'),
        ]
        setup(detail_sheet, 'COIRTECH — Detalle de movimientos',
              [col[0] for col in detail_columns], [col[1] for col in detail_columns],
              'Cada fila es un movimiento registrado. Las referencias C y S enlazan salida y regreso; J identifica la jornada. '
              'Las duraciones de comida/salida aparecen solo al regreso. Las horas de jornada aparecen solo en Salida final. '
              'Los totales usan instantes UTC para respetar cambios de zona horaria.')
        for row_index, event in enumerate(dataset['events'], start=5):
            detail_sheet.set_row(row_index, 34)
            for col_index, (header, width, key, kind) in enumerate(detail_columns):
                value = (_('Sí') if event[key] else _('No')) if key == 'reviewed' else event[key]
                write(detail_sheet, row_index, col_index, value, kind)
        detail_sheet.autofilter(4, 0, 4 + len(dataset['events']), len(detail_columns) - 1)
        detail_sheet.print_area(0, 0, 4 + len(dataset['events']), len(detail_columns) - 1)
        workbook.close()
        return output.getvalue()
