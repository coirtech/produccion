from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .attendance import _COIR_WRITE_TOKEN


class CoirReentryAuthorization(models.Model):
    _name = "coir.reentry.authorization"
    _description = "Autorización de entrada adicional COIRTECH"
    _inherit = ["mail.thread"]
    _order = "authorized_at desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one("res.company", string="Empresa", required=True, readonly=True, index=True)
    valid_date = fields.Date(string="Fecha local autorizada", required=True, index=True)
    reason = fields.Text(string="Motivo", required=True)
    authorized_by = fields.Many2one("res.users", string="Autorizó", readonly=True, required=True, ondelete="restrict")
    authorized_at = fields.Datetime(string="Autorizado el", readonly=True, required=True)
    consumed_attendance_id = fields.Many2one("hr.attendance", string="Jornada autorizada", readonly=True, ondelete="restrict")
    consumed_at = fields.Datetime(string="Utilizado el", readonly=True)
    revoked = fields.Boolean(string="Revocada", readonly=True, default=False)
    revoked_by = fields.Many2one("res.users", string="Revocó", readonly=True, ondelete="restrict")
    revoked_at = fields.Datetime(string="Revocada el", readonly=True)
    state = fields.Selection([
        ("pending", "Pendiente"), ("used", "Utilizada"), ("revoked", "Revocada"),
    ], string="Estado", compute="_compute_state", store=True, index=True)

    @api.depends("employee_id.name", "valid_date")
    def _compute_name(self):
        for authorization in self:
            authorization.name = "%s — %s" % (authorization.employee_id.name or "", authorization.valid_date or "")

    @api.depends("consumed_attendance_id", "revoked")
    def _compute_state(self):
        for authorization in self:
            authorization.state = "used" if authorization.consumed_attendance_id else ("revoked" if authorization.revoked else "pending")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede autorizar otra entrada."))
        protected = {"company_id", "authorized_by", "authorized_at", "consumed_attendance_id", "consumed_at", "revoked", "revoked_by", "revoked_at", "state"}
        prepared = []
        for original in vals_list:
            if protected.intersection(original):
                raise AccessError(_("Los datos de auditoría de la autorización los asigna el servidor."))
            vals = dict(original)
            employee = self.env["hr.employee"].browse(vals.get("employee_id")).exists()
            if not employee:
                raise ValidationError(_("Selecciona un empleado válido."))
            employee.check_access("read")
            if employee.company_id not in self.env.companies:
                raise AccessError(_("No tienes acceso a la empresa del empleado."))
            if not employee.company_id.coir_meal_control_enabled:
                raise ValidationError(_("Activa el control COIRTECH en la empresa antes de autorizar otra entrada."))
            reason = (vals.get("reason") or "").strip()
            if not reason:
                raise ValidationError(_("Escribe el motivo de la entrada adicional."))
            vals.update(
                reason=reason, company_id=employee.company_id.id,
                valid_date=vals.get("valid_date") or employee._coir_day_bounds(fields.Datetime.now())[0],
                authorized_by=self.env.user.id, authorized_at=fields.Datetime.now(),
                consumed_attendance_id=False, consumed_at=False, revoked=False,
                revoked_by=False, revoked_at=False, state="pending",
            )
            prepared.append(vals)
        records = super().create(prepared)
        for record in records:
            record.message_post(body=Markup("<p>%s</p><p>%s</p>") % (
                escape(_("Autorización de una entrada adicional creada.")), escape(record.reason),
            ))
        return records

    def write(self, vals):
        allowed = {"consumed_attendance_id", "consumed_at", "revoked", "revoked_by", "revoked_at"}
        trusted = self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN
        if not trusted or set(vals) - allowed:
            raise AccessError(_("La autorización conserva su historial. Revócala y crea otra si necesitas cambiarla."))
        return super().write(vals)

    def unlink(self):
        if not (self.env.su and self.env.context.get("module_uninstall")):
            raise UserError(_("Las autorizaciones se conservan para auditoría. Puedes revocar una pendiente."))
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Crea una nueva autorización indicando el motivo; no se pueden duplicar."))

    def action_revoke(self):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede revocar autorizaciones."))
        self.check_access("write")
        self.employee_id._coir_lock_employee()
        self.invalidate_recordset()
        if self.state != "pending":
            raise UserError(_("Solo se puede revocar una autorización pendiente."))
        self.sudo().with_context(coir_write_token=_COIR_WRITE_TOKEN).write({
            "revoked": True, "revoked_by": self.env.user.id, "revoked_at": fields.Datetime.now(),
        })
        self.message_post(body=_("Autorización revocada por %s.", self.env.user.display_name))
        return True

    def _coir_consume(self, attendance):
        self.ensure_one()
        if not (self.env.su and self.env.context.get("coir_write_token") is _COIR_WRITE_TOKEN):
            raise AccessError(_("No puedes utilizar directamente una autorización."))
        self.invalidate_recordset()
        if self.state != "pending" or self.employee_id != attendance.employee_id or self.company_id != attendance.employee_id.company_id:
            raise UserError(_("La autorización ya no está disponible. Solicita revisión a Recursos Humanos."))
        if self.valid_date != self.employee_id._coir_day_bounds(attendance.check_in)[0]:
            raise UserError(_("La autorización no corresponde a la fecha local de esta entrada."))
        self.write({"consumed_attendance_id": attendance.id, "consumed_at": fields.Datetime.now()})
        self.message_post(body=_("La autorización se utilizó en la jornada %s.", attendance.id))
        attendance.message_post(body=Markup("<p>%s</p><p>%s: %s</p><p>%s: %s</p>") % tuple(escape(item) for item in (
            _("Entrada adicional autorizada por Recursos Humanos."), _("Autorizó"), self.authorized_by.display_name,
            _("Motivo"), self.reason,
        )))
        return True
