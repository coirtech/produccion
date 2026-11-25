"""Administrative configuration for a shared, explicitly scoped attendance kiosk."""
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AttendanceMultiCompanyKiosk(models.Model):
    _name = "attendance.multi.company.kiosk"
    _description = "Quiosco Multiempresa"
    _order = "name, id"

    name = fields.Char(string="Nombre del quiosco", required=True, default="Control de asistencia")
    active = fields.Boolean(string="Activo", default=True)
    company_ids = fields.Many2many(
        "res.company", "attendance_multi_kiosk_company_rel", "kiosk_id", "company_id",
        string="Empresas participantes", default=lambda self: self.env.company,
        # The universal company rule must see every membership, including those
        # outside a user's current company context. Editing remains validated below.
        bypass_search_access=True,
        context={"active_test": False},
        help="Puedes agregar o quitar empresas. Sus asistencias anteriores se conservan.",
    )
    available_company_ids = fields.Many2many(
        "res.company", compute="_compute_available_companies", string="Empresas disponibles",
    )
    identification_mode = fields.Selection([
        ("manual", "Nombre y PIN, según la empresa"),
        ("barcode", "Credencial con cámara o lector"),
        ("both", "Nombre/PIN y credencial con cámara o lector"),
    ], string="Identificación", default="both", required=True)
    barcode_source = fields.Selection([
        ("company", "Usar la configuración de la primera empresa"),
        ("scanner", "Lector de código de barras / RFID"),
        ("front", "Cámara frontal"),
        ("back", "Cámara trasera"),
    ], string="Fuente del escaneo", default="company", required=True,
        help="Usa la configuración de escaneo de la primera empresa participante disponible, "
             "o elige una cámara o un lector específico para este quiosco.")
    access_token = fields.Char(string="Clave del enlace", required=True, readonly=True, copy=False, index=True)
    config_revision = fields.Integer(string="Revisión", readonly=True, copy=False, default=1)
    kiosk_url = fields.Char(string="Enlace del quiosco", compute="_compute_kiosk_url")

    _access_token_unique = models.Constraint("UNIQUE(access_token)", "La clave del quiosco debe ser única.")

    @api.depends_context("allowed_company_ids", "uid")
    def _compute_available_companies(self):
        for kiosk in self:
            kiosk.available_company_ids = self.env.companies

    @api.depends("access_token")
    def _compute_kiosk_url(self):
        for kiosk in self:
            kiosk.kiosk_url = (
                "%s/attendance_multi_company/%s" % (kiosk.get_base_url().rstrip("/"), kiosk.access_token)
                if kiosk.access_token else False
            )

    def _get_barcode_source(self):
        """Reuse the native scanner option unless this kiosk overrides it.

        The default also applies to rows created before this field existed, so
        upgrading does not replace a company's camera preference with a reader.
        Company ordering is stable regardless of the administrator's context.
        """
        self.ensure_one()
        if self.barcode_source in ("scanner", "front", "back"):
            return self.barcode_source
        company = self.company_ids.filtered(
            lambda item: item.active and item.coir_meal_control_enabled and not item.auto_check_out
        ).sorted("id")[:1]
        source = company.attendance_barcode_source if company else False
        return source if source in ("scanner", "front", "back") else "front"

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Solo un administrador de Asistencias puede configurar el quiosco multiempresa."))

    @api.model
    def _prepare_company_ids(self, commands, initial_ids=()):
        """Normalize membership without permitting company create/write/delete commands."""
        ids = set(initial_ids)
        if commands is False or commands is None:
            commands = [(5,)]
        if not isinstance(commands, (list, tuple)):
            raise ValidationError(_("Selecciona las empresas participantes."))
        for command in commands:
            if (not isinstance(command, (list, tuple)) or not command
                    or not isinstance(command[0], int) or isinstance(command[0], bool)):
                raise ValidationError(_("La selección de empresas no es válida."))
            op = command[0]
            if op == 5:
                ids.clear()
            elif op in (3, 4) and len(command) >= 2 and type(command[1]) is int and command[1] > 0:
                if op == 3:
                    ids.discard(command[1])
                else:
                    ids.add(command[1])
            elif op == 6 and len(command) >= 3 and isinstance(command[2], (list, tuple)):
                if any(type(value) is not int or value <= 0 for value in command[2]):
                    raise ValidationError(_("La selección de empresas no es válida."))
                ids = set(command[2])
            else:
                raise AccessError(_("Desde este quiosco solo puedes seleccionar o retirar empresas existentes."))
        if ids - set(self.env.companies.ids):
            raise AccessError(_("Selecciona únicamente empresas activadas en tu sesión y a las que tengas acceso."))
        return sorted(ids)

    @api.model
    def _validate_participants(self, company_ids, enabled):
        companies = self.env["res.company"].browse(company_ids).exists()
        if len(companies) != len(company_ids):
            raise ValidationError(_("Alguna empresa seleccionada ya no existe."))
        if enabled and not companies:
            raise ValidationError(_("Selecciona al menos una empresa o desactiva el quiosco."))
        if enabled:
            if any(not company.active for company in companies):
                raise ValidationError(_("Las empresas participantes deben estar activas."))
            if any(not company.coir_meal_control_enabled for company in companies):
                raise ValidationError(_("Activa los seis movimientos en los ajustes de Asistencias de cada empresa participante."))
            if any(company.auto_check_out for company in companies):
                raise ValidationError(_("Desactiva Salida automática en las empresas participantes."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        prepared = []
        for original in vals_list:
            if {"access_token", "config_revision", "kiosk_url", "available_company_ids"}.intersection(original):
                raise AccessError(_("La clave del enlace y sus datos de control los genera el servidor."))
            vals = dict(original)
            enabled = vals.get("active", self.env.context.get("default_active", True))
            if type(enabled) is not bool:
                raise ValidationError(_("El estado del quiosco no es válido."))
            commands = vals.get("company_ids", self.env.context.get("default_company_ids", [(6, 0, self.env.company.ids)]))
            company_ids = self._prepare_company_ids(commands)
            self._validate_participants(company_ids, enabled)
            vals.update(
                active=enabled,
                company_ids=[(6, 0, company_ids)],
                access_token=secrets.token_urlsafe(32),
                config_revision=1,
            )
            prepared.append(vals)
        safe_context = dict(self.env.context)
        for field_name in ("access_token", "config_revision", "kiosk_url", "available_company_ids"):
            safe_context.pop("default_" + field_name, None)
        return super(AttendanceMultiCompanyKiosk, self.with_context(safe_context)).create(prepared)

    def _lock_for_action(self):
        """Serialize actions/configuration and let Odoo retry a stale DB snapshot."""
        self.ensure_one()
        if not self.env.su:
            raise AccessError(_("La validación del quiosco corresponde al servidor."))
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM attendance_multi_company_kiosk WHERE id = %s FOR UPDATE", [self.id],
        )
        if not self.env.cr.fetchone():
            raise UserError(_("El quiosco ya no está disponible."))
        self.env.cr.execute(
            "UPDATE attendance_multi_company_kiosk SET config_revision = config_revision WHERE id = %s",
            [self.id],
        )
        self.invalidate_recordset()
        return self

    def write(self, vals):
        self._check_manager()
        self.check_access("write")
        if {"access_token", "config_revision", "kiosk_url", "available_company_ids"}.intersection(vals):
            raise AccessError(_("La clave del enlace y sus datos de control los genera el servidor."))
        if "active" in vals and type(vals["active"]) is not bool:
            raise ValidationError(_("El estado del quiosco no es válido."))
        sensitive = bool({"company_ids", "active", "identification_mode", "barcode_source"}.intersection(vals))
        for kiosk in self.sorted("id"):
            kiosk.sudo()._lock_for_action()
            kiosk.invalidate_recordset()
            company_ids = (
                self._prepare_company_ids(vals["company_ids"], kiosk.company_ids.ids)
                if "company_ids" in vals else list(kiosk.company_ids.ids)
            )
            if set(company_ids) - set(self.env.companies.ids):
                raise AccessError(_("Activa en tu sesión todas las empresas de este quiosco para modificarlo."))
            self._validate_participants(company_ids, vals.get("active", kiosk.active))
            prepared = dict(vals)
            if "company_ids" in prepared:
                prepared["company_ids"] = [(6, 0, company_ids)]
            if sensitive:
                prepared["config_revision"] = kiosk.config_revision + 1
            super(AttendanceMultiCompanyKiosk, kiosk).write(prepared)
        return True

    def action_regenerate_token(self):
        self.ensure_one()
        self._check_manager()
        self.check_access("write")
        self.sudo()._lock_for_action()
        self.invalidate_recordset()
        super().write({"access_token": secrets.token_urlsafe(32), "config_revision": self.config_revision + 1})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_kiosk(self):
        self.ensure_one()
        self._check_manager()
        self.check_access("read")
        if not self.active:
            raise UserError(_("Activa el quiosco antes de abrir su enlace."))
        self._validate_participants(self.company_ids.ids, True)
        return {"type": "ir.actions.act_url", "url": self.kiosk_url, "target": "new"}

    def unlink(self):
        if self.env.su and self.env.context.get("module_uninstall"):
            return super().unlink()
        raise UserError(_("Desactiva el quiosco para dejar de utilizarlo. Sus registros de configuración se conservan."))
