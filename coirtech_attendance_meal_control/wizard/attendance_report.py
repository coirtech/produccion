import base64
import io
import math
from datetime import datetime, time

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class CoirAttendanceReportWizard(models.TransientModel):
    _name = 'coir.attendance.report.wizard'
    # Native Odoo 19 bridge for assigning hr.employee M2M filters without
    # granting private employee-model access to an attendance officer.
    _inherit = ['hr.mixin']
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
    absence_ids = fields.Many2many(
        'coir.attendance.absence', string='Ausencias e incidencias seleccionadas', readonly=True,
    )
    selection_only = fields.Boolean(string='Usar únicamente la selección', readonly=True)
    report_file = fields.Binary(string='Archivo Excel', readonly=True, attachment=False)
    report_filename = fields.Char(string='Nombre del archivo', readonly=True)

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        active_model = self.env.context.get('active_model')
        # An all-excluded selection must remain an empty explicit selection;
        # it must never turn into an unrestricted report of other employees.
        if (active_model in ('hr.attendance', 'coir.attendance.day')
                and self.env.context.get('active_ids') and 'selection_only' in names):
            values['selection_only'] = True
        if active_model == 'hr.attendance' and self.env.context.get('active_ids'):
            records = self.env['hr.attendance'].browse(self.env.context['active_ids']).exists()
            records.check_access('read')
            records = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_real_attendances(records)
            if records:
                if 'attendance_ids' in names:
                    values['attendance_ids'] = [(6, 0, records.ids)]
                if 'selection_only' in names:
                    values['selection_only'] = True
                if 'date_from' in names:
                    values['date_from'] = min(records.mapped('date'))
                if 'date_to' in names:
                    values['date_to'] = max(records.mapped('date'))
                if 'company_ids' in names:
                    values['company_ids'] = [(6, 0, records.coir_company_id.ids)]
        elif active_model == 'coir.attendance.day' and self.env.context.get('active_ids'):
            rows = self.env[active_model].browse(self.env.context['active_ids']).exists()
            rows.check_access('read')
            if rows:
                if 'attendance_ids' in names:
                    values['attendance_ids'] = [(6, 0, rows.attendance_id.ids)]
                if 'absence_ids' in names:
                    values['absence_ids'] = [(6, 0, rows.absence_id.ids)]
                if 'selection_only' in names:
                    values['selection_only'] = True
                if 'date_from' in names:
                    values['date_from'] = min(rows.mapped('date'))
                if 'date_to' in names:
                    values['date_to'] = max(rows.mapped('date'))
                if 'company_ids' in names:
                    values['company_ids'] = [(6, 0, rows.company_id.ids)]
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

    def _check_report_filters(self):
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

    def _get_attendances(self, allow_empty=False):
        self._check_report_filters()
        domain = [
            '|', ('coir_managed', '=', True), ('coir_company_id.coir_meal_control_enabled', '=', True),
            ('employee_id.coir_attendance_report_excluded', '=', False),
            ('coir_company_id', 'in', self.company_ids.ids),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.selection_only or self.attendance_ids or self.absence_ids:
            self.attendance_ids.check_access('read')
            domain.append(('id', 'in', self.attendance_ids.ids))
        records = self.env['hr.attendance'].search(domain, order='check_in, id')
        records = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_real_attendances(records)
        if not records and not allow_empty:
            raise UserError(_('No hay jornadas COIRTECH para los filtros seleccionados.'))
        return records

    def _get_absences(self, selected_attendances=None):
        self._check_report_filters()
        self.env['coir.attendance.absence']._sync_approved_leaves(
            date_from=self.date_from, date_to=self.date_to, company_ids=self.company_ids.ids,
        )
        domain = [
            ('state', 'in', ['absent', 'approved', 'partial', 'review']),
            ('employee_id.coir_attendance_report_excluded', '=', False),
            ('company_id', 'in', self.company_ids.ids),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.selection_only or self.attendance_ids or self.absence_ids:
            self.absence_ids.check_access('read')
            records = selected_attendances if selected_attendances is not None else self._get_attendances(allow_empty=True)
            related = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_related_notices(
                records, sync=False,
            )
            domain.append(('id', 'in', (self.absence_ids | related).ids))
        return self.env['coir.attendance.absence'].search(
            domain, order='date, employee_id, id',
        )._coir_visible_in_report()

    def _get_report_records(self):
        records = self._get_attendances(allow_empty=True)
        absences = self._get_absences(selected_attendances=records)
        if not records and not absences:
            raise UserError(_('No hay asistencias, ausencias o incidencias para los filtros seleccionados.'))
        return records, absences

    def action_print_pdf(self):
        records, absences = self._get_report_records()
        return self.env.ref('coirtech_attendance_meal_control.action_report_meal').report_action(
            records, data={'coir_attendance_ids': records.ids, 'coir_absence_ids': absences.ids},
        )

    def action_export_xlsx(self):
        self.ensure_one()
        records, absences = self._get_report_records()
        dataset = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']._coir_dataset(records, absences)
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
        # The 1904 date system preserves genuine numeric negative overtime
        # durations instead of displaying #####. XLSX records the epoch and
        # write_datetime converts real calendar dates consistently with it.
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False,
            'date_1904': True,
        })
        workbook.set_properties({'title': 'Reporte de asistencia', 'company': 'COIRTECH'})
        common = {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter'}
        format_specs = {
            'title': {**common, 'font_size': 20, 'bold': True, 'font_color': '#174D3A', 'text_wrap': True},
            'subtitle': {**common, 'font_color': '#425766', 'text_wrap': True},
            'note': {**common, 'font_size': 10, 'font_color': '#425766', 'text_wrap': True},
            'header': {**common, 'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#17513C', 'text_wrap': True, 'border': 1, 'border_color': '#D8E2DE'},
            'text': {**common, 'text_wrap': True},
            'date': {**common, 'num_format': 'dd/mm/yyyy'},
            'datetime': {**common, 'num_format': 'dd/mm/yyyy hh:mm'},
            'integer': {**common, 'num_format': '0'},
            'duration': {**common, 'num_format': '[h]:mm;-[h]:mm'},
            'pending': {**common, 'font_color': '#7A4B10', 'bg_color': '#FFF4DC', 'text_wrap': True},
        }
        # Retain the standard [h]:mm format for nonnegative durations and
        # native tests/readers, with a signed format only where needed.
        format_specs['duration']['num_format'] = '[h]:mm'
        format_specs['signed_duration'] = {**common, 'num_format': '[h]:mm;-[h]:mm'}
        formats = {name: workbook.add_format(spec) for name, spec in format_specs.items()}
        absence_formats = {
            name: workbook.add_format({**spec, 'bold': True, 'font_color': '#9C0006', 'bg_color': '#FFC7CE'})
            for name, spec in format_specs.items()
            if name in ('text', 'date', 'datetime', 'integer', 'duration', 'signed_duration')
        }
        layouts = self.env['coir.attendance.report.layout']
        report = self.env['report.coirtech_attendance_meal_control.report_meal_journeys']
        companies = (dataset['docs'].coir_company_id | dataset['absences'].company_id).sorted('id')
        multi_company = len(companies) > 1

        def setup(sheet, title, columns, company, note):
            last_col = len(columns) - 1
            widths = [max(60, column['width']) if len(columns) == 1 else column['width'] for column in columns]
            total_width = sum(widths)
            sheet.hide_gridlines(2)
            sheet.set_tab_color('#17513C')
            period = 'Fecha laboral: %s a %s · Empresa: %s' % (
                self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y'), company.name,
            )
            for row, value, kind, height in (
                    (0, title, 'title', 30), (1, period, 'subtitle', 30), (2, note, 'note', 52)):
                if last_col:
                    sheet.merge_range(row, 0, row, last_col, value, formats[kind])
                else:
                    sheet.write_string(row, 0, value, formats[kind])
                font_size = format_specs[kind]['font_size']
                wrapped_lines = max(1, math.ceil(len(value) * font_size / 11 / max(10, total_width)))
                sheet.set_row(row, max(height, wrapped_lines * (font_size + 3) + 6))
            for col, column in enumerate(columns):
                sheet.write_string(4, col, column['label'], formats['header'])
                sheet.set_column(col, col, widths[col])
            header_lines = max(math.ceil(len(column['label']) / max(8, widths[col] - 2)) for col, column in enumerate(columns))
            sheet.set_row(4, max(52, header_lines * 15 + 8))
            sheet.freeze_panes(5, min(2, len(columns)))
            sheet.set_landscape()
            sheet.set_paper(9)
            sheet.fit_to_pages(2 if len(columns) > 10 else 1, 0)
            sheet.repeat_rows(0, 4)
            sheet.set_margins(0.25, 0.25, 0.4, 0.4)
            sheet.set_footer('&LCOIRTECH — Asistencias&C&P / &N&RConfidencial')

        def write(sheet, row_index, column_index, value, kind, is_absence=False, pending=False):
            format_kind = 'signed_duration' if kind == 'duration' and value is not None and value < 0 else kind
            if is_absence:
                fmt = absence_formats[format_kind]
            else:
                fmt = formats['pending' if pending else format_kind]
            if value is None or value is False:
                sheet.write_blank(row_index, column_index, None, fmt)
            elif kind == 'date':
                sheet.write_datetime(row_index, column_index, datetime.combine(value, time.min), fmt)
            elif kind == 'datetime':
                sheet.write_datetime(row_index, column_index, value, fmt)
            elif kind == 'duration':
                sheet.write_number(row_index, column_index, value / 86400, fmt)
            elif kind == 'integer':
                sheet.write_number(row_index, column_index, value, fmt)
            else:
                sheet.write_string(row_index, column_index, str(value), fmt)

        summary_note = (
            'Comida y salidas de trabajo pagadas: ya están incluidas en las horas de jornada. No se suman nuevamente. '
            'Si hay jornadas abiertas, las horas cerradas son un subtotal parcial. '
            'Las faltas no tienen horas trabajadas. Las horas autorizadas y extra aprobadas se muestran aparte.'
        )
        detail_note = (
            'Cada fila es un movimiento, falta, ausencia aprobada o incidencia. C y S enlazan salida y regreso; '
            'J identifica la jornada; F, la falta; A, la ausencia o incidencia. '
            'Las duraciones de comida/salida aparecen solo al regreso; las horas de jornada y extra aprobadas, solo en Salida final.'
        )
        for index, company in enumerate(companies, 1):
            for section, base_name, title, note in (
                    ('summary', 'Resumen', 'COIRTECH — Resumen de asistencias', summary_note),
                    ('detail', 'Detalle', 'COIRTECH — Detalle de movimientos', detail_note)):
                columns = layouts._coir_get_columns(company, 'xlsx', section)
                # The ordinal prefix guarantees uniqueness even with equal
                # company names, forbidden Excel characters or long names.
                name = base_name
                if multi_company:
                    safe_company = ''.join('-' if char in '[]:*?/\\' else char for char in company.name).strip("'")
                    prefix = '%s %s ' % (base_name, index)
                    name = (prefix + safe_company)[:31].rstrip("'")
                sheet = workbook.add_worksheet(name)
                rows = [row for row in dataset['summary' if section == 'summary' else 'events']
                        if row['company_id'] == company.id]
                setup(sheet, title, columns, company, note)
                for row_index, row in enumerate(rows, start=5):
                    # Multi-line custom text remains visible instead of being
                    # silently clipped by the former fixed 34-point row height.
                    max_lines = 1
                    values = []
                    for column in columns:
                        value, kind = report._coir_export_value(row, column, section)
                        values.append((value, kind))
                        if kind == 'text' and value:
                            width = max(8, column['width'] - 2)
                            max_lines = max(max_lines, sum(max(1, math.ceil(len(line) / width)) for line in str(value).split('\n')))
                    sheet.set_row(row_index, min(240, max(34, max_lines * 15 + 6)))
                    for col_index, (column, value_kind) in enumerate(zip(columns, values)):
                        value, kind = value_kind
                        pending = section == 'summary' and column['key'] == 'status' and (
                            row['open'] or row['meal_pending'] or row['work_pending'])
                        write(sheet, row_index, col_index, value, kind, report._coir_absence_cell(row, columns, column), pending)
                sheet.autofilter(4, 0, 4 + len(rows), len(columns) - 1)
                sheet.print_area(0, 0, 4 + len(rows), len(columns) - 1)
        workbook.close()
        return output.getvalue()
