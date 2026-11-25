"""Read-only projection for the native Enterprise attendance Gantt.

Positive ids are untouched real attendances. Negative ids only exist in this
SQL view and identify an active absence. No placeholder is inserted into
hr_attendance, and no attendance query outside this projection changes.
"""
from functools import partial

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import SQL


class CoirAttendanceGantt(models.Model):
    _name = "coir.attendance.gantt"
    _inherit = "hr.attendance"
    _description = "Proyección de asistencias y faltas para Gantt"
    _auto = False
    _log_access = True

    coir_absence_id = fields.Many2one(
        "coir.attendance.absence", string="Falta", readonly=True,
    )

    # These are materialized values in the source table, not computations owned
    # by this read-only projection. In particular, employee/calendar changes
    # must not schedule UPDATEs against the UNION view.
    date = fields.Date(compute=None, precompute=False, store=True, readonly=True)
    worked_hours = fields.Float(compute=None, store=True, readonly=True)
    overtime_hours = fields.Float(compute=None, store=True, readonly=True)
    overtime_status = fields.Selection(compute=None, store=True, readonly=True)
    validated_overtime_hours = fields.Float(compute=None, store=True, readonly=True)
    expected_hours = fields.Float(compute=None, store=True, readonly=True)
    coir_meal_status = fields.Selection(compute=None, store=True, readonly=True)
    coir_meal_hours = fields.Float(compute=None, store=True, readonly=True)
    coir_company_id = fields.Many2one(related=None, compute=None, store=True, readonly=True)
    coir_work_hours = fields.Float(compute=None, store=True, readonly=True)
    coir_open_work_outing_id = fields.Many2one(compute=None, store=True, readonly=True)
    coir_work_status = fields.Selection(compute=None, store=True, readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL(
            """
            CREATE VIEW %s AS
                SELECT attendance.*, NULL::integer AS coir_absence_id
                  FROM hr_attendance attendance
                UNION ALL
                SELECT visual.*, absence.id AS coir_absence_id
                  FROM coir_attendance_absence absence
                 CROSS JOIN LATERAL jsonb_populate_record(
                     NULL::hr_attendance,
                     jsonb_build_object(
                         'id', -absence.id,
                         'employee_id', absence.employee_id,
                         'date', absence.date,
                         'check_in', absence.start_datetime,
                         'check_out', absence.end_datetime,
                         'worked_hours', 0.0,
                         'overtime_hours', 0.0,
                         'validated_overtime_hours', 0.0,
                         'expected_hours', 0.0,
                         'coir_managed', false,
                         'coir_company_id', absence.company_id,
                         'coir_section_id', absence.section_id,
                         'coir_section_name', absence.section_name,
                         'coir_meal_hours', 0.0,
                         'coir_meal_status', 'none',
                         'coir_work_hours', 0.0,
                         'coir_work_status', 'none',
                         'coir_revision', 0,
                         'create_uid', absence.create_uid,
                         'create_date', absence.create_date,
                         'write_uid', absence.write_uid,
                         'write_date', absence.write_date
                     )
                 ) visual
                 WHERE absence.state = 'absent'
            """, SQL.identifier(self._table),
        ))

    @api.model
    def _coir_source_security_domain(self):
        """Enforce the original models' current ACLs AND custom record rules.

        Queries remain SQL subqueries rather than materializing every visible id.
        No sudo or user-controlled bypass context is used here.
        """
        attendance = self.env["hr.attendance"]
        absence = self.env["coir.attendance.absence"]
        domains = []
        if attendance.has_access("read"):
            domains.append(Domain("id", "in", attendance._search([])))
        if absence.has_access("read"):
            domains.append(Domain(
                "coir_absence_id", "in", absence._search([("state", "=", "absent")]),
            ))
        return Domain.OR(domains)

    def _search(self, domain, offset=0, limit=None, order=None, *,
                active_test=True, bypass_access=False):
        return super()._search(
            Domain(domain) & self._coir_source_security_domain(),
            offset=offset, limit=limit, order=order,
            active_test=active_test, bypass_access=bypass_access,
        )

    def _check_access(self, operation):
        if operation != "read":
            return self, partial(AccessError, _("El indicador del tablero es de solo lectura."))
        denied = super()._check_access(operation)
        if denied or not self:
            return denied
        # A record that was read into the shared cache under sudo must still be
        # checked against the source model when read under the original user.
        attendance = self.env["hr.attendance"].browse([i for i in self.ids if i > 0])
        absence = self.env["coir.attendance.absence"].browse([-i for i in self.ids if i < 0])
        if ((attendance and not attendance.has_access("read"))
                or (absence and not absence.has_access("read"))):
            return self, partial(AccessError, _("No tienes acceso a estos registros de asistencia."))
        return None

    @api.depends("employee_id", "check_in", "check_out", "coir_absence_id")
    def _compute_display_name(self):
        normal = self.filtered(lambda row: row.id > 0)
        super(CoirAttendanceGantt, normal)._compute_display_name()
        for row in self - normal:
            row.display_name = "FALTA"

    def _compute_color(self):
        normal = self.filtered(lambda row: row.id > 0)
        super(CoirAttendanceGantt, normal)._compute_color()
        for row in self - normal:
            row.color = 1  # The native attendance error/absence color is red.

    @api.depends("employee_id", "check_in", "check_out", "coir_absence_id")
    def _compute_linked_overtime_ids(self):
        normal = self.filtered(lambda row: row.id > 0)
        super(CoirAttendanceGantt, normal)._compute_linked_overtime_ids()
        for row in self - normal:
            row.linked_overtime_ids = False

    @api.depends("employee_id", "coir_absence_id")
    def _compute_is_manager(self):
        normal = self.filtered(lambda row: row.id > 0)
        super(CoirAttendanceGantt, normal)._compute_is_manager()
        for row in self - normal:
            row.is_manager = False

    def _get_worked_hours_in_range(self, start_dt, end_dt):
        self.ensure_one()
        if self.id < 0:
            return 0.0
        return super()._get_worked_hours_in_range(start_dt, end_dt)

    @api.model_create_multi
    def create(self, vals_list):
        raise UserError(_("Los indicadores del tablero se generan automáticamente."))

    def write(self, vals):
        raise UserError(_("No se puede modificar un indicador del tablero."))

    def unlink(self):
        raise UserError(_("La falta desaparece al registrar la entrada del empleado."))

    def copy(self, default=None):
        raise UserError(_("Los indicadores del tablero no se pueden duplicar."))

    def action_approve_overtime(self):
        raise UserError(_("Gestiona las horas extra desde la asistencia original."))

    def action_refuse_overtime(self):
        raise UserError(_("Gestiona las horas extra desde la asistencia original."))

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        self.check_access("read")
        if self.id < 0:
            return self.env["coir.attendance.absence"].browse(-self.id).get_formview_action(access_uid=access_uid)
        return self.env["hr.attendance"].browse(self.id).get_formview_action(access_uid=access_uid)
