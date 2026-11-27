"""Company-specific, presentation-only layouts for COIRTECH exports.

Only catalogue keys are persisted. A layout cannot request arbitrary model
fields or change the permission-checked attendance dataset.
"""
from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


# This identity cannot be supplied through RPC/context JSON. It defers the
# aggregate validation until a complete parent write has applied all commands.
_LAYOUT_MUTATION_TOKEN = object()
_MUTATION_CONTEXT = '_coir_report_layout_mutation'


def _column(key, label, kind='text', width=24, help_text=''):
    return {'key': key, 'label': label, 'kind': kind, 'width': width, 'help': help_text}


_SUMMARY_COLUMNS = [
    _column('company_name', 'Empresa'),
    _column('employee_name', 'Empleado', width=27),
    _column('department', 'Departamento', width=22),
    _column('date', 'Fecha laboral', 'date', 14),
    _column('timezone', 'Zona horaria efectiva', width=25),
    _column('first_entry', 'Primera entrada', 'datetime', 21),
    _column('last_exit', 'Última salida final registrada', 'datetime', 23),
    _column('journeys', 'Jornadas', 'integer', 12),
    _column('closed', 'Cerradas', 'integer', 12),
    _column('open', 'Abiertas', 'integer', 12),
    _column('paid_seconds', 'Horas de jornadas cerradas (h:mm)', 'duration', 23,
            'Subtotal de jornadas cerradas. La comida y las salidas pagadas ya están incluidas.'),
    _column('meal_seconds', 'Comida confirmada (h:mm)', 'duration', 22),
    _column('work_seconds', 'Salidas de trabajo confirmadas (h:mm)', 'duration', 25),
    _column('meal_pending', 'Comidas pendientes', 'integer', 18),
    _column('work_pending', 'Salidas pendientes', 'integer', 18),
    _column('status', 'Estado del resumen', width=31),
    _column('reviewed', 'Jornadas revisadas por RH', 'integer', 22),
    _column('notice_label', 'Ausencia / incidencia', width=34),
    _column('leave_periods', 'Periodo de ausencia', width=42),
    _column('leave_seconds', 'Horas autorizadas (h:mm)', 'duration', 23),
    _column('review_reason', 'Incidencia para RH', width=44),
    _column('meal_start', 'Salida a comer', 'datetime', 22,
            'Última salida a comer del día. Su regreso corresponde a la misma comida.'),
    _column('meal_end', 'Regreso de comida', 'datetime', 22,
            'Regreso de la última comida; queda vacío mientras esa comida siga abierta.'),
    _column('work_start', 'Salida de trabajo', 'datetime', 22,
            'Última salida de trabajo del día. El detalle conserva todos los movimientos.'),
    _column('work_end', 'Regreso al trabajo', 'datetime', 22,
            'Regreso de la última salida de trabajo; vacío si todavía no regresa.'),
    _column('meal_state', 'Estado de comida', width=28),
    _column('work_state', 'Estado de salidas', width=28),
    _column('overtime_seconds', 'Horas extra aprobadas (h:mm)', 'duration', 25,
            'Valor aprobado por Odoo para las jornadas cerradas; no se calcula una regla de horas extra adicional.'),
    _column('leave_label', 'Tipo de ausencia', width=30),
    _column('journey_counts', 'Cerradas / abiertas', width=18),
    _column('pending_counts', 'Pendientes comida / salida', width=23),
    _column('notice_detail', 'Ausencia / revisión RH', width=44,
            help_text='Combina el nombre del tipo de Tiempo personal, su periodo y la incidencia de RH.'),
]
_DETAIL_COLUMNS = [
    _column('company_name', 'Empresa'),
    _column('employee_name', 'Empleado', width=27),
    _column('department', 'Departamento', width=22),
    _column('date', 'Fecha laboral', 'date', 14),
    _column('journey_id', 'Jornada ID', 'integer', 13),
    _column('label', 'Movimiento', width=23),
    _column('local_stamp', 'Fecha y hora local', 'datetime', 22),
    _column('timezone', 'Zona horaria efectiva', width=25),
    _column('stamp', 'Fecha y hora UTC', 'datetime', 22),
    _column('reference', 'Referencia del intervalo', width=23),
    _column('interval_seconds', 'Comida / salida confirmada (h:mm)', 'duration', 25),
    _column('journey_seconds', 'Horas de jornada al cierre (h:mm)', 'duration', 25),
    _column('interval_state', 'Estado del intervalo / jornada', width=31),
    _column('reviewed', 'Jornada revisada por RH', width=22),
    _column('review_note', 'Último motivo de revisión', width=45),
    _column('leave_periods', 'Periodo de ausencia', width=42),
    _column('leave_seconds', 'Horas autorizadas (h:mm)', 'duration', 23),
    _column('review_reason', 'Incidencia para RH', width=44),
    _column('leave_label', 'Tipo de ausencia', width=30),
    _column('overtime_seconds', 'Horas extra aprobadas (h:mm)', 'duration', 27,
            'Horas extra aprobadas por Odoo, solo en la salida final para evitar duplicarlas por movimiento.'),
]
_CATALOGUE = {'summary': _SUMMARY_COLUMNS, 'detail': _DETAIL_COLUMNS}
_DEFAULT_KEYS = {
    ('xlsx', 'summary'): [column['key'] for column in _SUMMARY_COLUMNS[:21]],
    ('xlsx', 'detail'): [column['key'] for column in _DETAIL_COLUMNS[:18]],
    ('pdf', 'summary'): [
        'date', 'employee_name', 'journey_counts', 'paid_seconds', 'meal_seconds',
        'work_seconds', 'pending_counts', 'status', 'notice_detail', 'leave_seconds',
    ],
    ('pdf', 'detail'): [
        'employee_name', 'date', 'label', 'local_stamp', 'reference',
        'interval_seconds', 'journey_seconds', 'interval_state',
    ],
}
_PDF_LABELS = {
    ('summary', 'paid_seconds'): 'Horas cerradas (hh:mm)',
    ('summary', 'meal_seconds'): 'Comida confirmada (hh:mm)',
    ('summary', 'work_seconds'): 'Salidas confirmadas (hh:mm)',
    ('summary', 'status'): 'Estado',
    ('summary', 'leave_seconds'): 'Autorizadas (hh:mm)',
    ('detail', 'reference'): 'Referencia',
    ('detail', 'interval_seconds'): 'Comida / salida (hh:mm)',
    ('detail', 'journey_seconds'): 'Jornada al cierre (hh:mm)',
    ('detail', 'interval_state'): 'Estado',
}


def _catalogue_map(section):
    return {column['key']: column for column in _CATALOGUE[section]}


def _normalise_header(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise ValidationError(_('El encabezado debe contener entre 1 y 80 caracteres.'))
    return value.strip()


class CoirAttendanceReportLayout(models.Model):
    _name = 'coir.attendance.report.layout'
    _description = 'Columnas del Reporte de asistencia por empresa y formato'
    _order = 'company_id, output_format, id'
    _check_company_auto = True

    name = fields.Char(string='Configuración', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    output_format = fields.Selection(
        [('xlsx', 'Excel'), ('pdf', 'PDF')], string='Formato', required=True, default='xlsx',
    )
    line_ids = fields.One2many('coir.attendance.report.layout.line', 'layout_id', copy=True)
    summary_line_ids = fields.One2many(
        'coir.attendance.report.layout.line', 'layout_id', string='Columnas del resumen',
        domain=[('section', '=', 'summary')],
    )
    detail_line_ids = fields.One2many(
        'coir.attendance.report.layout.line', 'layout_id', string='Columnas del detalle',
        domain=[('section', '=', 'detail')],
    )
    _company_format_unique = models.Constraint(
        'UNIQUE(company_id, output_format)',
        'Ya existe una configuración para esta empresa y formato.',
    )

    @api.depends('company_id.name', 'output_format')
    def _compute_name(self):
        for layout in self:
            layout.name = '%s — %s' % (
                layout.company_id.name or '', 'Excel' if layout.output_format == 'xlsx' else 'PDF',
            )

    @api.model
    def _check_company_scope(self, company, manager=False):
        company = self.env['res.company'].browse(company.id).exists()
        company.ensure_one()
        group = ('hr_attendance.group_hr_attendance_manager' if manager
                 else 'hr_attendance.group_hr_attendance_officer')
        if not self.env.user.has_group(group):
            raise AccessError(_('No tienes permiso para configurar este reporte.' if manager
                                else 'No tienes permiso para consultar este reporte.'))
        if company not in self.env.companies:
            raise AccessError(_('Selecciona una empresa habilitada en tu sesión y autorizada para tu usuario.'))
        company.check_access('read')
        return company

    @api.model
    def _check_format_section(self, output_format, section=None):
        if output_format not in ('xlsx', 'pdf') or (section is not None and section not in _CATALOGUE):
            raise ValidationError(_('El formato o la sección del reporte no es válido.'))

    @api.model
    def _default_line_values(self, output_format):
        self._check_format_section(output_format)
        values = []
        for section, catalogue in _CATALOGUE.items():
            visible = _DEFAULT_KEYS[(output_format, section)]
            ordered = visible + [col['key'] for col in catalogue if col['key'] not in visible]
            for number, key in enumerate(ordered, start=1):
                descriptor = _catalogue_map(section)[key]
                label = _PDF_LABELS.get((section, key), descriptor['label']) if output_format == 'pdf' else descriptor['label']
                values.append({
                    'section': section, 'column_key': key, 'label': label,
                    'visible': key in visible, 'sequence': number * 10,
                })
        return values

    @api.model
    def _coir_get_columns(self, company, output_format, section):
        company = self._check_company_scope(company)
        self._check_format_section(output_format, section)
        layout = self.search([('company_id', '=', company.id), ('output_format', '=', output_format)], limit=1)
        catalogue = _catalogue_map(section)
        if layout:
            layout._validate_structure()
            lines = layout.line_ids.filtered(lambda line: line.section == section and line.visible).sorted(
                lambda line: (line.sequence, line.id),
            )
            return [{
                'key': line.column_key, 'label': line.label,
                'kind': catalogue[line.column_key]['kind'], 'width': catalogue[line.column_key]['width'],
            } for line in lines]
        return [{
            'key': item['column_key'], 'label': item['label'],
            'kind': catalogue[item['column_key']]['kind'], 'width': catalogue[item['column_key']]['width'],
        } for item in self._default_line_values(output_format) if item['section'] == section and item['visible']]

    @api.model
    def _coir_open_editor(self, company, output_format):
        company = self._check_company_scope(company, manager=True)
        self._check_format_section(output_format)
        layout = self.search([('company_id', '=', company.id), ('output_format', '=', output_format)], limit=1)
        if not layout:
            layout = self.create({'company_id': company.id, 'output_format': output_format})
        return {
            'type': 'ir.actions.act_window', 'name': _('Personalizar columnas del reporte'),
            'res_model': self._name, 'res_id': layout.id, 'view_mode': 'form',
            'views': [(self.env.ref('coirtech_attendance_meal_control.report_layout_form').id, 'form')],
            'target': 'new',
        }

    def _validate_structure(self):
        for layout in self:
            for section, catalogue in _CATALOGUE.items():
                lines = layout.line_ids.filtered(lambda line: line.section == section)
                keys = lines.mapped('column_key')
                if len(keys) != len(set(keys)) or set(keys) != {column['key'] for column in catalogue}:
                    raise ValidationError(_('La configuración debe conservar todas las columnas disponibles, sin duplicarlas. Usa la casilla Mostrar para ocultarlas.'))
                if not any(lines.mapped('visible')):
                    raise ValidationError(_('Debe quedar al menos una columna visible en Resumen y una en Detalle.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            values = dict(values)
            company = self.env['res.company'].browse(values.get('company_id') or self.env.company.id)
            self._check_company_scope(company, manager=True)
            output_format = values.get('output_format', 'xlsx')
            self._check_format_section(output_format)
            values.setdefault('company_id', company.id)
            values.setdefault('output_format', output_format)
            relation_fields = ('line_ids', 'summary_line_ids', 'detail_line_ids')
            if any(values.get(field) for field in relation_fields):
                for field in relation_fields:
                    if any(command[0] != Command.CREATE for command in values.get(field, [])):
                        raise ValidationError(_('Las columnas no se pueden trasladar desde otra configuración.'))
            else:
                # The editor opens a saved parent, so the full catalogue is
                # immediately editable, including on first use after upgrade.
                for field in relation_fields:
                    values.pop(field, None)
                values['line_ids'] = [Command.create(line) for line in self._default_line_values(output_format)]
            prepared.append(values)
        records = super(CoirAttendanceReportLayout, self.with_context(**{
            _MUTATION_CONTEXT: _LAYOUT_MUTATION_TOKEN,
        })).create(prepared)
        records = records.with_env(self.env)
        records._validate_structure()
        return records

    def write(self, vals):
        self.check_access('write')
        for layout in self:
            self._check_company_scope(layout.company_id, manager=True)
            if ('company_id' in vals and vals['company_id'] != layout.company_id.id
                    or 'output_format' in vals and vals['output_format'] != layout.output_format):
                raise ValidationError(_('La empresa y el formato de una configuración guardada no se cambian. Abre la configuración correspondiente.'))
        for field in ('line_ids', 'summary_line_ids', 'detail_line_ids'):
            for command in vals.get(field, []):
                if command[0] != Command.UPDATE or command[1] not in self.line_ids.ids:
                    raise ValidationError(_('Las columnas no se pueden agregar, eliminar ni trasladar. Usa Mostrar para ocultarlas.'))
                if any(key in command[2] for key in ('layout_id', 'section', 'column_key', 'company_id')):
                    raise ValidationError(_('La identidad de una columna no se puede modificar.'))
                # A command through a section-specific field cannot alter the
                # other section, even if a client submits a known line id.
                if field != 'line_ids':
                    line = self.env['coir.attendance.report.layout.line'].browse(command[1])
                    if line.section != ('summary' if field == 'summary_line_ids' else 'detail'):
                        raise ValidationError(_('La columna no pertenece a esta sección.'))
        result = super(CoirAttendanceReportLayout, self.with_context(**{
            _MUTATION_CONTEXT: _LAYOUT_MUTATION_TOKEN,
        })).write(vals)
        self._validate_structure()
        return result

    def unlink(self):
        self.check_access('unlink')
        for layout in self:
            self._check_company_scope(layout.company_id, manager=True)
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_('Usa «Aplicar al otro formato» para copiar las columnas de esta empresa.'))

    def action_reset_defaults(self):
        self.ensure_one()
        defaults = {(item['section'], item['column_key']): item for item in self._default_line_values(self.output_format)}
        self.write({'line_ids': [Command.update(line.id, {
            key: defaults[(line.section, line.column_key)][key] for key in ('sequence', 'label', 'visible')
        }) for line in self.line_ids]})
        return self._coir_open_editor(self.company_id, self.output_format)

    def action_apply_to_other_format(self):
        self.ensure_one()
        self.check_access('read')
        self._check_company_scope(self.company_id, manager=True)
        target_format = 'pdf' if self.output_format == 'xlsx' else 'xlsx'
        target = self.search([('company_id', '=', self.company_id.id), ('output_format', '=', target_format)], limit=1)
        if not target:
            target = self.create({'company_id': self.company_id.id, 'output_format': target_format})
        source = {(line.section, line.column_key): line for line in self.line_ids}
        target.write({'line_ids': [Command.update(line.id, {
            key: source[(line.section, line.column_key)][key] for key in ('sequence', 'label', 'visible')
        }) for line in target.line_ids]})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Columnas guardadas'),
                       'message': _('La misma configuración se aplicó también a %s.', 'PDF' if target_format == 'pdf' else 'Excel'),
                       'type': 'success', 'sticky': False},
        }


class CoirAttendanceReportLayoutLine(models.Model):
    _name = 'coir.attendance.report.layout.line'
    _description = 'Columna configurable del Reporte de asistencia'
    _order = 'sequence, id'
    _check_company_auto = True

    layout_id = fields.Many2one('coir.attendance.report.layout', required=True, ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one(related='layout_id.company_id', store=True, readonly=True, index=True)
    section = fields.Selection([('summary', 'Resumen'), ('detail', 'Detalle')], required=True)
    column_key = fields.Selection(
        selection=list({column['key']: column['label'] for columns in _CATALOGUE.values() for column in columns}.items()),
        string='Columna', required=True,
    )
    column_title = fields.Char(string='Dato original', compute='_compute_descriptor')
    description = fields.Char(string='Descripción', compute='_compute_descriptor')
    label = fields.Char(string='Encabezado del reporte', required=True, size=80)
    visible = fields.Boolean(string='Mostrar', default=True)
    sequence = fields.Integer(string='Orden', default=10)
    _column_unique = models.Constraint(
        'UNIQUE(layout_id, section, column_key)', 'La columna ya existe en esta sección.',
    )

    @api.depends('section', 'column_key')
    def _compute_descriptor(self):
        for line in self:
            descriptor = _catalogue_map(line.section).get(line.column_key, {}) if line.section in _CATALOGUE else {}
            line.column_title = descriptor.get('label', '')
            line.description = descriptor.get('help', '')

    @api.constrains('section', 'column_key', 'label')
    def _check_descriptor(self):
        for line in self:
            if line.column_key not in _catalogue_map(line.section):
                raise ValidationError(_('Esta columna no está disponible en la sección seleccionada.'))
            if not line.label or not line.label.strip() or len(line.label) > 80:
                raise ValidationError(_('El encabezado debe contener entre 1 y 80 caracteres.'))

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(_MUTATION_CONTEXT) is not _LAYOUT_MUTATION_TOKEN:
            raise AccessError(_('Las columnas se crean automáticamente al abrir una configuración.'))
        records = super().create([{
            **values, 'label': _normalise_header(values.get('label')),
        } for values in vals_list])
        return records

    def write(self, vals):
        self.check_access('write')
        for layout in self.layout_id:
            self.env['coir.attendance.report.layout']._check_company_scope(layout.company_id, manager=True)
        if any(key in vals for key in ('layout_id', 'company_id', 'section', 'column_key')):
            raise ValidationError(_('La identidad de una columna no se puede modificar.'))
        if 'label' in vals:
            vals = {**vals, 'label': _normalise_header(vals['label'])}
        result = super().write(vals)
        if self.env.context.get(_MUTATION_CONTEXT) is not _LAYOUT_MUTATION_TOKEN:
            self.layout_id._validate_structure()
        return result

    def unlink(self):
        raise AccessError(_('Las columnas no se eliminan. Desmarca Mostrar para ocultarlas.'))
