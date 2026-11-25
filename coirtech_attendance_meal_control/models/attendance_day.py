"""Read-only report of real journeys and independently justified daily notices."""
from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError
from odoo.tools import SQL, format_datetime


class CoirAttendanceDay(models.Model):
    _name = 'coir.attendance.day'
    _description = 'Reporte de asistencia'
    _auto = False
    _log_access = False
    _rec_name = 'employee_id'
    _order = 'date desc, employee_id, check_in desc, id desc'

    attendance_id = fields.Many2one('hr.attendance', string='Asistencia original', readonly=True)
    absence_id = fields.Many2one('coir.attendance.absence', string='Ausencia o incidencia original', readonly=True)
    is_absence = fields.Boolean(string='Es falta', readonly=True)
    is_indicator = fields.Boolean(string='Es ausencia o incidencia', readonly=True)
    indicator_state = fields.Selection([
        ('absent', 'FALTA'), ('approved', 'Ausencia aprobada'),
        ('partial', 'Ausencia parcial'), ('review', 'Revisión de Recursos Humanos'),
    ], string='Tipo de registro', readonly=True)
    report_label = fields.Char(string='Ausencia / incidencia', readonly=True)
    leave_label = fields.Char(string='Ausencia aprobada', readonly=True)
    leave_periods = fields.Char(string='Periodo autorizado', readonly=True)
    leave_hours = fields.Float(string='Horas autorizadas', readonly=True,
                               help='Horas justificadas sobre el horario laboral; no son horas trabajadas.')
    review_reason = fields.Char(string='Incidencia para RH', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    coir_company_id = fields.Many2one(related='company_id', string='Empresa (compatibilidad)', readonly=True)
    department_id = fields.Many2one('hr.department', string='Departamento', readonly=True)
    date = fields.Date(string='Fecha de jornada', readonly=True)
    timezone = fields.Char(string='Zona horaria efectiva', readonly=True)
    check_in = fields.Datetime(string='Entrada registrada', readonly=True)
    check_out = fields.Datetime(string='Salida final', readonly=True)
    entry_display = fields.Char(string='Entrada', compute='_compute_entry_display')
    coir_section_name = fields.Char(string='Sección', readonly=True)
    coir_managed = fields.Boolean(string='Jornada COIRTECH', readonly=True)
    coir_meal_start = fields.Datetime(string='Salida a comer', readonly=True)
    coir_meal_end = fields.Datetime(string='Regreso de comida', readonly=True)
    coir_meal_hours = fields.Float(string='Comida registrada', readonly=True)
    coir_meal_status = fields.Selection([
        ('none', 'Sin comida registrada'), ('open', 'En comida'),
        ('returned', 'Regreso registrado'), ('missing', 'Salida sin regreso registrado'),
    ], string='Estado de comida', readonly=True)
    coir_work_start = fields.Datetime(
        string='Salida de trabajo', readonly=True,
        help='Salida del último movimiento de trabajo. El detalle conserva todos los movimientos.',
    )
    coir_work_end = fields.Datetime(
        string='Regreso al trabajo', readonly=True,
        help='Regreso de esa misma última salida; queda vacío mientras siga abierta.',
    )
    coir_work_hours = fields.Float(string='Salidas confirmadas', readonly=True)
    coir_work_status = fields.Selection([
        ('none', 'Sin salidas de trabajo'), ('open', 'Fuera por trabajo'),
        ('returned', 'Regresos registrados'), ('missing', 'Salida sin regreso registrado'),
    ], string='Estado de salidas', readonly=True)
    worked_hours = fields.Float(string='Horas trabajadas', readonly=True)
    out_mode = fields.Selection([
        ('kiosk', 'Quiosco'), ('systray', 'Barra superior'), ('manual', 'Manual'),
        ('technical', 'Técnico'), ('auto_check_out', 'Salida automática'),
    ], string='Modo de salida', readonly=True)
    coir_work_outing_ids = fields.One2many(
        related='attendance_id.coir_work_outing_ids', readonly=True, related_sudo=False,
        string='Todas las salidas de trabajo',
    )

    @api.depends('is_absence', 'check_in', 'timezone')
    def _compute_entry_display(self):
        for row in self:
            row.entry_display = 'FALTA' if row.is_absence else (
                format_datetime(self.env, row.check_in, tz=row.timezone or 'UTC', dt_format='HH:mm:ss')
                if row.check_in else False
            )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE VIEW %s AS (
                SELECT
                    a.id * 2 AS id, a.id AS attendance_id,
                    NULL::integer AS absence_id, FALSE AS is_absence,
                    FALSE AS is_indicator, NULL::varchar AS indicator_state,
                    NULL::varchar AS report_label, NULL::varchar AS leave_label,
                    NULL::varchar AS leave_periods, NULL::double precision AS leave_hours,
                    NULL::varchar AS review_reason,
                    a.employee_id, e.company_id, v.department_id, a.date,
                    COALESCE(cal.tz, r.tz, company_cal.tz, 'UTC') AS timezone,
                    a.check_in, a.check_out, a.coir_section_name, a.coir_managed,
                    a.coir_meal_start, a.coir_meal_end, a.coir_meal_hours, a.coir_meal_status,
                    last_outing.start AS coir_work_start, last_outing.end AS coir_work_end,
                    a.coir_work_hours, a.coir_work_status, a.worked_hours, a.out_mode
                FROM hr_attendance a
                JOIN hr_employee e ON e.id = a.employee_id
                JOIN res_company c ON c.id = e.company_id
                LEFT JOIN hr_version v ON v.id = e.current_version_id
                LEFT JOIN resource_resource r ON r.id = e.resource_id
                LEFT JOIN resource_calendar cal ON cal.id = v.resource_calendar_id
                LEFT JOIN resource_calendar company_cal ON company_cal.id = c.resource_calendar_id
                LEFT JOIN LATERAL (
                    SELECT outing.start, outing.end
                    FROM coir_work_outing outing
                    WHERE outing.attendance_id = a.id
                    ORDER BY outing.start DESC, outing.id DESC LIMIT 1
                ) last_outing ON TRUE
                WHERE (a.coir_managed IS TRUE OR c.coir_meal_control_enabled IS TRUE)
                  AND e.coir_attendance_report_excluded IS NOT TRUE
                  AND NOT (
                    a.coir_managed IS NOT TRUE
                    AND COALESCE(a.in_mode, '') = 'technical'
                    AND COALESCE(a.out_mode, '') = 'technical'
                    AND a.check_out IS NOT NULL
                    AND a.check_out - a.check_in BETWEEN INTERVAL '0 seconds' AND INTERVAL '1 second'
                  )
                UNION ALL
                SELECT
                    f.id * 2 + 1 AS id, NULL::integer AS attendance_id,
                    f.id AS absence_id, f.state = 'absent' AS is_absence,
                    TRUE AS is_indicator, f.state AS indicator_state,
                    f.report_label, f.leave_label, f.leave_periods, f.leave_hours, f.review_reason,
                    f.employee_id, f.company_id, f.department_id, f.date, f.timezone,
                    NULL::timestamp AS check_in, NULL::timestamp AS check_out,
                    f.section_name AS coir_section_name, FALSE AS coir_managed,
                    NULL::timestamp AS coir_meal_start, NULL::timestamp AS coir_meal_end,
                    NULL::double precision AS coir_meal_hours, NULL::varchar AS coir_meal_status,
                    NULL::timestamp AS coir_work_start, NULL::timestamp AS coir_work_end,
                    NULL::double precision AS coir_work_hours, NULL::varchar AS coir_work_status,
                    NULL::double precision AS worked_hours, NULL::varchar AS out_mode
                FROM coir_attendance_absence f
                JOIN hr_employee excluded_employee ON excluded_employee.id = f.employee_id
                WHERE f.state IN ('absent', 'approved', 'partial', 'review')
                  AND excluded_employee.coir_attendance_report_excluded IS NOT TRUE
                  -- The attendance REPORT must never show future leave days.
                  -- This is evaluated per record's effective company timezone;
                  -- hr.leave and the original indicator rows remain intact.
                  AND f.date <= (CURRENT_TIMESTAMP AT TIME ZONE
                      COALESCE(NULLIF(f.timezone, ''), 'America/Mexico_City'))::date
            )
        """, SQL.identifier(self._table)))

    def _flush_source_models(self):
        # ORM columns on a SQL view cannot automatically infer these dependencies.
        for model_name in (
            'hr.attendance', 'coir.attendance.absence', 'coir.work.outing',
            'hr.employee', 'hr.version', 'resource.resource', 'resource.calendar', 'res.company',
        ):
            self.env[model_name].flush_model()

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, bypass_access=False, **kwargs):
        self._flush_source_models()
        self.invalidate_model(flush=False)
        query = super()._search(domain, offset, limit, order, bypass_access=bypass_access, **kwargs)
        if self.env.su or bypass_access or query.is_empty():
            return query
        # Apply the original models' ACLs and custom record rules to every search,
        # including read_group, export and direct reads of known projection ids.
        source_terms = []
        for model_name, field_name in (
            ('hr.attendance', 'attendance_id'), ('coir.attendance.absence', 'absence_id'),
        ):
            source = self.env[model_name]
            if source.has_access('read'):
                source_query = source._search([], active_test=False)
                source_terms.append(SQL(
                    '%s IN %s', SQL.identifier(self._table, field_name), source_query.subselect(),
                ))
        query.add_where(SQL('(%s)', SQL(' OR ').join(source_terms)) if source_terms else SQL('FALSE'))
        return query

    def _read_format(self, fnames, load='_classic_read'):
        # Odoo skips its access hook in sudo and an id-only read need not fetch
        # anything. Recheck membership in this report before formatting output,
        # so a saved/cached id never makes an excluded row reappear. This only
        # removes records: ordinary fetching still applies the source ACLs.
        if not self:
            return super()._read_format(fnames, load=load)
        self._flush_source_models()
        visible_ids = {row_id for row_id, in self.env.execute_query(SQL(
            'SELECT id FROM %s WHERE id IN %s',
            SQL.identifier(self._table), tuple(self.ids),
        ))}
        visible = self.browse([row_id for row_id in self.ids if row_id in visible_ids])
        return super(CoirAttendanceDay, visible)._read_format(fnames, load=load)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if operation != 'read' or not self:
            return result
        eligible = self - result[0] if result else self
        if not eligible:
            return result
        self._flush_source_models()
        # A cached recordset may predate checking the employee's opt-out box.
        # Its original row still exists, although it no longer belongs to this
        # SQL report. Guard ordinary access checks as well as search filtering;
        # _read_format also removes excluded rows when sudo skips this hook.
        excluded = self.env.execute_query(SQL("""
            SELECT a.id * 2 AS id
              FROM hr_attendance a JOIN hr_employee e ON e.id = a.employee_id
             WHERE a.id * 2 IN %s AND e.coir_attendance_report_excluded IS TRUE
            UNION ALL
            SELECT f.id * 2 + 1 AS id
              FROM coir_attendance_absence f JOIN hr_employee e ON e.id = f.employee_id
             WHERE f.id * 2 + 1 IN %s AND e.coir_attendance_report_excluded IS TRUE
        """, tuple(eligible.ids), tuple(eligible.ids)))
        if excluded:
            forbidden = self.browse([row_id for row_id, in excluded])
            forbidden |= result[0] if result else self.browse()
            return forbidden, lambda: AccessError(self.env._('Este empleado está excluido del Reporte de asistencia.'))
        if self.env.su:
            return result
        rows = self.env.execute_query(SQL(
            'SELECT id, attendance_id, absence_id FROM %s WHERE id IN %s',
            SQL.identifier(self._table), tuple(eligible.ids),
        ))
        allowed_attendances = set(self.env['hr.attendance'].browse(
            [attendance_id for _, attendance_id, _ in rows if attendance_id]
        )._filtered_access('read').ids)
        allowed_absences = set(self.env['coir.attendance.absence'].browse(
            [absence_id for _, _, absence_id in rows if absence_id]
        )._filtered_access('read').ids)
        forbidden = self.browse([
            row_id for row_id, attendance_id, absence_id in rows
            if (attendance_id and attendance_id not in allowed_attendances)
            or (absence_id and absence_id not in allowed_absences)
        ])
        if forbidden:
            forbidden |= result[0] if result else self.browse()
            message = self.env._('No tienes permiso para consultar las asistencias, ausencias o incidencias originales.')
            return forbidden, lambda: AccessError(message)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Este reporte es de consulta. Registra la entrada en Asistencias.'))

    def write(self, vals):
        raise AccessError(_('Abre la asistencia original para corregir sus movimientos.'))

    def unlink(self):
        raise AccessError(_('Los registros del reporte no se pueden eliminar desde esta vista.'))

    def action_open_source(self):
        self.ensure_one()
        self.check_access('read')
        source = self.attendance_id or self.absence_id
        source.check_access('read')
        return {
            'type': 'ir.actions.act_window', 'name': _('Asistencia') if self.attendance_id else _('Ausencia o incidencia'),
            'res_model': source._name, 'res_id': source.id, 'view_mode': 'form', 'target': 'current',
        }

    def action_report_selected(self):
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id(
            'coirtech_attendance_meal_control.attendance_report_wizard_action',
        )
        action['context'] = dict(self.env.context, active_model=self._name, active_ids=self.ids,
                                 active_id=self[:1].id or False)
        return action
