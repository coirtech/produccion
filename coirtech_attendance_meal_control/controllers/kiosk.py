"""Identify first; mutate only after an explicit, authenticated kiosk action."""
import hashlib
import hmac
import secrets
import time

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools import format_datetime
from odoo.addons.hr_attendance.controllers.main import HrAttendance


class CoirtechMealKiosk(HrAttendance):
    _TICKET_KEY = 'coirtech_meal_identity'
    _TICKET_LIFETIME = 120  # Identity lifetime; not a meal timer or an alert.

    @staticmethod
    def _coir_company(token):
        if not isinstance(token, str) or not token or len(token) > 256:
            return request.env['res.company']
        return request.env['res.company'].sudo().search(
            [('attendance_kiosk_key', '=', token)], limit=1,
        )

    @staticmethod
    def _coir_error(message, expired=False):
        return {'ok': False, 'error': message, 'expired': expired}

    def _coir_clear_ticket(self):
        request.session.pop(self._TICKET_KEY, None)

    @http.route('/coirtech_meal/config', type='jsonrpc', auth='public')
    def coir_meal_config(self, token):
        company = self._coir_company(token)
        if not company:
            return self._coir_error(_('El enlace del quiosco no es válido.'))
        return {'ok': True, 'enabled': company.coir_meal_control_enabled}

    @http.route('/coirtech_meal/identify', type='jsonrpc', auth='public')
    def coir_meal_identify(self, token, employee_id=None, pin_code=None, barcode=None):
        self._coir_clear_ticket()
        company = self._coir_company(token)
        if not company or not company.coir_meal_control_enabled:
            return self._coir_error(_('El control de comidas no está activo en este quiosco.'))
        employees = request.env['hr.employee'].sudo().with_company(company).with_context(
            allowed_company_ids=[company.id],
        )
        domain = [('company_id', '=', company.id), ('active', '=', True)]
        if barcode is not None:
            if not isinstance(barcode, str) or not barcode or len(barcode) > 256:
                return self._coir_error(_('Credencial no válida.'))
            employee = employees.search(domain + [('barcode', '=', barcode)], limit=1)
        else:
            if type(employee_id) is not int:
                return self._coir_error(_('Selecciona un empleado válido.'))
            employee = employees.search(domain + [('id', '=', employee_id)], limit=1)
            if employee and company.attendance_kiosk_use_pin:
                if not isinstance(pin_code, str) or not employee.pin or not hmac.compare_digest(
                    employee.pin.encode('utf-8'), pin_code.encode('utf-8'),
                ):
                    return self._coir_error(_('PIN incorrecto.'))
        if not employee:
            return self._coir_error(_('No se pudo identificar al empleado en esta empresa.'))
        snapshot = employee._coir_meal_state()
        ticket = secrets.token_urlsafe(32)
        request.session[self._TICKET_KEY] = {
            'digest': hashlib.sha256(ticket.encode()).hexdigest(),
            'company_id': company.id,
            'employee_id': employee.id,
            'kiosk': hashlib.sha256(token.encode()).hexdigest(),
            'expires': time.time() + self._TICKET_LIFETIME,
            'attendance_id': snapshot['attendance_id'],
            'state': snapshot['state'],
            'revision': snapshot.get('revision', 0),
        }
        return {
            'ok': True,
            'ticket': ticket,
            'employee': {'id': employee.id, 'name': employee.name},
            'snapshot': snapshot,
            'kiosk_delay': company.attendance_kiosk_delay * 1000,
        }

    @http.route('/coirtech_meal/action', type='jsonrpc', auth='public')
    def coir_meal_action(self, token, ticket, action, confirm_without_return=False,
                         latitude=False, longitude=False):
        company = self._coir_company(token)
        identity = request.session.get(self._TICKET_KEY) or {}
        if not company or not company.coir_meal_control_enabled:
            self._coir_clear_ticket()
            return self._coir_error(_('El control de comidas no está activo.'), expired=True)
        if (
            not isinstance(ticket, str) or len(ticket) > 256
            or identity.get('company_id') != company.id
            or identity.get('kiosk') != hashlib.sha256(token.encode()).hexdigest()
            or identity.get('expires', 0) < time.time()
            or not hmac.compare_digest(
                identity.get('digest', ''), hashlib.sha256(ticket.encode()).hexdigest(),
            )
        ):
            self._coir_clear_ticket()
            return self._coir_error(_('Vuelve a identificarte para registrar el movimiento.'), expired=True)
        if action not in ('check_in', 'meal_start', 'meal_return', 'work_exit', 'work_return', 'check_out'):
            return self._coir_error(_('Movimiento no válido.'))
        if type(confirm_without_return) is not bool:
            return self._coir_error(_('Confirmación no válida.'))
        employee = request.env['hr.employee'].sudo().with_company(company).with_context(
            allowed_company_ids=[company.id],
        ).search([
            ('id', '=', identity['employee_id']),
            ('company_id', '=', company.id), ('active', '=', True),
        ], limit=1)
        if not employee:
            self._coir_clear_ticket()
            return self._coir_error(_('Vuelve a identificarte en el quiosco.'), expired=True)

        try:
            # Any validation failure rolls back every field/event in this action.
            with request.env.cr.savepoint():
                geo = self._get_geoip_response(
                    'kiosk', latitude=latitude, longitude=longitude,
                    device_tracking_enabled=company.attendance_device_tracking,
                ) if action in ('check_in', 'check_out') else None
                attendance = employee._coir_apply_meal_action(
                    action,
                    expected_attendance_id=identity['attendance_id'],
                    expected_state=identity['state'],
                    expected_revision=identity.get('revision', 0),
                    confirm_without_return=confirm_without_return,
                    geo_information=geo,
                )
                snapshot = employee._coir_meal_state()
        except (AccessError, UserError, ValidationError) as exc:
            return self._coir_error(str(exc))

        self._coir_clear_ticket()
        messages = {
            'check_in': _('Entrada registrada.'),
            'meal_start': _('Salida a comer registrada. Tu jornada sigue abierta.'),
            'meal_return': _('Regreso de comida registrado.'),
            'work_exit': _('Salida de trabajo registrada. Tu jornada sigue abierta y este tiempo cuenta como trabajado.'),
            'work_return': _('Regreso al trabajo registrado.'),
            'check_out': _('Salida final registrada.'),
        }
        if action == 'check_out' and attendance.coir_meal_start and not attendance.coir_meal_end:
            messages['check_out'] = _('Salida final registrada sin regreso de comida. Recursos Humanos podrá revisar el registro.')
        return {
            'ok': True,
            'message': messages[action],
            'snapshot': snapshot,
            'time_label': format_datetime(
                request.env, fields.Datetime.now(), tz=employee._get_tz(),
                dt_format='dd/MM/yyyy HH:mm:ss',
            ),
        }

    @http.route('/coirtech_meal/cancel', type='jsonrpc', auth='public')
    def coir_meal_cancel(self, token):
        if self._coir_company(token):
            self._coir_clear_ticket()
        return {'ok': True}

    # A kiosk tab with old JavaScript must not toggle someone out during lunch.
    @http.route()
    def manual_selection(self, token, employee_id, pin_code, latitude=False, longitude=False):
        company = self._coir_company(token)
        if company and company.coir_meal_control_enabled:
            raise UserError(_('Recarga el quiosco para usar los seis movimientos de COIRTECH.'))
        return super().manual_selection(token, employee_id, pin_code, latitude, longitude)

    @http.route()
    def scan_barcode_with_geolocation(self, token, barcode, latitude=False, longitude=False):
        company = self._coir_company(token)
        if company and company.coir_meal_control_enabled:
            raise UserError(_('Recarga el quiosco para usar los seis movimientos de COIRTECH.'))
        return super().scan_barcode_with_geolocation(token, barcode, latitude, longitude)
