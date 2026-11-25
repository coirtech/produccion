"""A separate public kiosk; the original company kiosks are not overridden.

Only the server-held identification ticket can choose an employee or company
for a write. The existing attendance module performs every business action.
"""
import hashlib
import hmac
import math
import secrets
import time

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request
from odoo.service.common import exp_version
from odoo.tools import format_datetime, py_to_js_locale
from odoo.tools.image import image_data_uri
from odoo.addons.hr_attendance.controllers.main import HrAttendance


class MultiCompanyAttendanceKiosk(http.Controller):
    _SESSION_KEY = 'attendance_multi_company_identity'
    _TICKET_SECONDS = 120
    _PAGE_SIZE = 24
    _ACTIONS = frozenset((
        'check_in', 'meal_start', 'meal_return',
        'work_exit', 'work_return', 'check_out',
    ))

    @staticmethod
    def _error(message, expired=False):
        return {'ok': False, 'error': message, 'expired': expired}

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    @staticmethod
    def _clean_context(company_ids=None):
        # JSON-RPC accepts a client context. Never propagate its default_* or
        # privileged addon flags into employee searches or attendance.create.
        result = {'lang': request.env.user.lang or 'en_US', 'active_test': True}
        if company_ids is not None:
            result['allowed_company_ids'] = company_ids
        return result

    def _find_kiosk(self, token):
        kiosk_model = request.env['attendance.multi.company.kiosk'].sudo().with_context(self._clean_context())
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            return kiosk_model.browse()
        return kiosk_model.search([('access_token', '=', token), ('active', '=', True)], limit=1)

    @staticmethod
    def _companies(kiosk):
        return kiosk.company_ids.filtered(lambda company:
            company.coir_meal_control_enabled and not company.auto_check_out
            and ('active' not in company._fields or company.active)
        )

    def _employees(self, companies):
        return request.env['hr.employee'].sudo().with_context(self._clean_context(companies.ids))

    def _clear_identity(self):
        request.session.pop(self._SESSION_KEY, None)

    def _employee_info(self, employee):
        return {
            'id': employee.id,
            'name': employee.name,
            'company_id': employee.company_id.id,
            'company_name': employee.company_id.name,
            'device_tracking_enabled': bool(employee.company_id.attendance_device_tracking),
        }

    def _departments(self, companies):
        """Keep the native department selector, limited to this link's employees."""
        counts = dict(self._employees(companies)._read_group(
            [('active', '=', True), ('company_id', 'in', companies.ids),
             ('department_id', '!=', False)],
            ['department_id'], ['__count'],
        ))
        return [{
            'id': department.id,
            'name': '%s · %s' % (department.name, department.company_id.name)
                if len(companies) > 1 else department.name,
            'count': count,
        } for department, count in sorted(
            counts.items(), key=lambda item: (item[0].name or '', item[0].id),
        ) if department.company_id.id in companies.ids and department.active]

    @staticmethod
    def _manual_domain(domain):
        """Accept only the native kiosk's name/department conjunction."""
        if not isinstance(domain, (list, tuple)) or len(domain) > 12:
            raise ValidationError(_('El filtro de empleados no es válido.'))
        clean = []
        for condition in domain:
            if isinstance(condition, str) and condition == '&':
                clean.append(condition)
                continue
            if not isinstance(condition, (list, tuple)) or len(condition) != 3:
                raise ValidationError(_('El filtro de empleados no es válido.'))
            field_name, operator, value = condition
            if field_name == 'name' and operator in ('=', 'ilike'):
                if not isinstance(value, str) or len(value) > 100:
                    raise ValidationError(_('Escribe un nombre de hasta 100 caracteres.'))
            elif field_name == 'department_id' and operator == '=':
                if type(value) is not int or value <= 0:
                    raise ValidationError(_('El departamento solicitado no es válido.'))
            else:
                raise ValidationError(_('Solo puedes filtrar por nombre o departamento.'))
            clean.append((field_name, operator, value))
        try:
            return Domain(clean)
        except (AssertionError, TypeError, ValueError) as exc:
            raise ValidationError(_('El filtro de empleados no es válido.')) from exc

    def _ticket_valid(self, kiosk, token, ticket, identity):
        return bool(
            isinstance(ticket, str) and 16 <= len(ticket) <= 256
            and identity.get('kiosk_id') == kiosk.id
            and identity.get('config_revision') == kiosk.config_revision
            and identity.get('token_digest') == self._digest(token)
            and identity.get('expires', 0) > time.time()
            and hmac.compare_digest(identity.get('ticket_digest', ''), self._digest(ticket))
        )

    @http.route('/attendance_multi_company/<string:token>', type='http', auth='public', methods=['GET'], sitemap=False)
    def kiosk_page(self, token, **kwargs):
        kiosk = self._find_kiosk(token)
        self._clear_identity()
        headers = [
            ('Cache-Control', 'no-store, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Referrer-Policy', 'no-referrer'),
            ('X-Content-Type-Options', 'nosniff'),
            ('X-Frame-Options', 'SAMEORIGIN'),
        ]
        companies = self._companies(kiosk) if kiosk else request.env['res.company']
        if not kiosk or not companies:
            return request.render(
                'attendance_multi_company_kiosk.kiosk_unavailable',
                {'message': _('El enlace está desactivado o ya no es válido. Solicita el enlace vigente a Recursos Humanos.')},
                status=404, headers=headers,
            )
        company = companies.sorted('id')[:1]
        kiosk_backend_info = {
            'token': token,
            'company_id': company.id,
            'company_name': kiosk.name,
            'departments': self._departments(companies),
            'kiosk_mode': {
                'manual': 'manual', 'barcode': 'barcode', 'both': 'barcode_manual',
            }[kiosk.identification_mode],
            'barcode_source': kiosk._get_barcode_source(),
            'from_trial_mode': False,
            # The bridge applies the identified employee's own company setting
            # before asking for location or submitting an action.
            'device_tracking_enabled': any(companies.mapped('attendance_device_tracking')),
            'lang': py_to_js_locale(company.partner_id.lang or company.env.lang),
            'server_version_info': exp_version().get('server_version_info'),
        }
        return request.render(
            'attendance_multi_company_kiosk.kiosk_page',
            {'token': token, 'kiosk_backend_info': kiosk_backend_info}, headers=headers,
        )

    @http.route('/attendance_multi_company/config', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_config(self, token):
        kiosk = self._find_kiosk(token)
        if not kiosk:
            return self._error(_('El enlace está desactivado o ya no es válido.'), expired=True)
        companies = self._companies(kiosk)
        if not companies:
            return self._error(_('No hay empresas habilitadas para este quiosco. Comunícate con Recursos Humanos.'))
        return {'ok': True, 'enabled': True, 'config': {
            'name': kiosk.name,
            'identification_mode': kiosk.identification_mode,
            'barcode_source': kiosk._get_barcode_source(),
            'identity_timeout_ms': 110000,
            'companies': [{'id': company.id, 'name': company.name} for company in companies.sorted('name')],
        }}

    @http.route('/attendance_multi_company/employees_infos', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_employees_infos(self, token, limit=24, offset=0, domain=None):
        """Read API used by Odoo's unchanged manual-selection component."""
        kiosk = self._find_kiosk(token)
        if not kiosk:
            return self._error(_('El enlace está desactivado o ya no es válido.'), expired=True)
        if kiosk.identification_mode not in ('manual', 'both'):
            return self._error(_('Utiliza tu credencial para identificarte.'))
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 100000:
            return self._error(_('La página solicitada no es válida.'))
        try:
            filters = self._manual_domain([] if domain is None else domain)
        except ValidationError as exc:
            return self._error(str(exc))
        companies = self._companies(kiosk)
        scope = Domain([('active', '=', True), ('company_id', 'in', companies.ids)]) & filters
        employees_model = self._employees(companies)
        employees = employees_model.search(scope, limit=limit, offset=offset, order='name, id')
        return {
            'ok': True,
            'records': [{
                'id': employee.id,
                'display_name': employee.name,
                'job_id': employee.job_id.name or '',
                'avatar': image_data_uri(employee.avatar_128),
                'status': employee.attendance_state,
                'mode': employee.last_attendance_id.in_mode,
                'company_id': employee.company_id.id,
                'company_name': employee.company_id.name,
            } for employee in employees],
            'length': employees_model.search_count(scope),
        }

    @http.route('/attendance_multi_company/employee_data', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_employee_data(self, token, employee_id):
        """Read only: choosing an employee prepares the original PIN keypad."""
        kiosk = self._find_kiosk(token)
        if not kiosk:
            return self._error(_('El enlace está desactivado o ya no es válido.'), expired=True)
        if kiosk.identification_mode not in ('manual', 'both'):
            return self._error(_('Utiliza tu credencial para identificarte.'))
        if type(employee_id) is not int or employee_id <= 0:
            return self._error(_('Selecciona un empleado válido.'))
        companies = self._companies(kiosk)
        employee = self._employees(companies).search([
            ('id', '=', employee_id), ('active', '=', True), ('company_id', 'in', companies.ids),
        ], limit=1)
        if not employee:
            return self._error(_('El empleado no está habilitado en este quiosco.'))
        company = employee.company_id
        return {
            'ok': True,
            'id': employee.id,
            'employee_name': employee.name,
            'employee_avatar': image_data_uri(employee.avatar_128),
            'company_id': company.id,
            'company_name': company.name,
            'attendance_state': employee.attendance_state,
            'use_pin': bool(company.attendance_kiosk_use_pin),
            'kiosk_delay': min(30000, max(1500, (company.attendance_kiosk_delay or 5) * 1000)),
            'device_tracking_enabled': bool(company.attendance_device_tracking),
            'coir_meal_identity': True,
        }

    @http.route('/attendance_multi_company/employees', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_employees(self, token, search='', offset=0):
        kiosk = self._find_kiosk(token)
        if not kiosk:
            return self._error(_('El enlace está desactivado o ya no es válido.'), expired=True)
        if kiosk.identification_mode not in ('manual', 'both'):
            return self._error(_('Utiliza tu credencial para identificarte.'))
        if not isinstance(search, str) or len(search) > 100:
            return self._error(_('Escribe un nombre de hasta 100 caracteres.'))
        if type(offset) is not int or offset < 0 or offset > 100000:
            return self._error(_('La página solicitada no es válida.'))
        companies = self._companies(kiosk)
        domain = [('active', '=', True), ('company_id', 'in', companies.ids)]
        if search.strip():
            domain.append(('name', 'ilike', search.strip()))
        employees = self._employees(companies).search(
            domain, limit=self._PAGE_SIZE + 1, offset=offset, order='name, id',
        )
        return {
            'ok': True,
            'employees': [dict(self._employee_info(employee), use_pin=bool(employee.company_id.attendance_kiosk_use_pin))
                          for employee in employees[:self._PAGE_SIZE]],
            'has_more': len(employees) > self._PAGE_SIZE,
            'offset': offset,
            'next_offset': offset + self._PAGE_SIZE,
        }

    @http.route('/attendance_multi_company/identify', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_identify(self, token, employee_id=None, pin_code=None, barcode=None):
        self._clear_identity()
        kiosk = self._find_kiosk(token)
        if not kiosk:
            return self._error(_('El enlace está desactivado o ya no es válido.'), expired=True)
        companies = self._companies(kiosk)
        employee_model = self._employees(companies)
        domain = [('active', '=', True), ('company_id', 'in', companies.ids)]
        if barcode is not None:
            if employee_id is not None or pin_code is not None:
                return self._error(_('Utiliza un solo método de identificación.'))
            if kiosk.identification_mode not in ('barcode', 'both'):
                return self._error(_('Selecciona tu nombre para identificarte.'))
            if not isinstance(barcode, str) or not barcode or len(barcode) > 256:
                return self._error(_('La credencial no es válida.'))
            employees = employee_model.search(domain + [('barcode', '=', barcode)], limit=2)
            if len(employees) != 1:
                return self._error(_('No se pudo identificar la credencial en las empresas de este quiosco.'))
            employee = employees
        else:
            if kiosk.identification_mode not in ('manual', 'both'):
                return self._error(_('Utiliza tu credencial para identificarte.'))
            if type(employee_id) is not int or employee_id <= 0:
                return self._error(_('Selecciona un empleado válido.'))
            employee = employee_model.search(domain + [('id', '=', employee_id)], limit=1)
            if not employee:
                return self._error(_('El empleado no está habilitado en este quiosco.'))
            if employee.company_id.attendance_kiosk_use_pin:
                if (not isinstance(pin_code, str) or len(pin_code) > 256 or not employee.pin
                        or not hmac.compare_digest(employee.pin.encode('utf-8'), pin_code.encode('utf-8'))):
                    return self._error(_('PIN incorrecto o sin configurar. Revisa tu identificación con Recursos Humanos.'))

        # Identification is deliberately read-only with respect to attendance.
        company = employee.company_id
        employee = employee.with_context(self._clean_context([company.id])).with_company(company)
        snapshot = employee._coir_meal_state()
        ticket = secrets.token_urlsafe(32)
        request.session[self._SESSION_KEY] = {
            'kiosk_id': kiosk.id,
            'config_revision': kiosk.config_revision,
            'token_digest': self._digest(token),
            'ticket_digest': self._digest(ticket),
            'employee_id': employee.id,
            'company_id': company.id,
            'expires': time.time() + self._TICKET_SECONDS,
            'attendance_id': snapshot['attendance_id'],
            'state': snapshot['state'],
            'revision': snapshot.get('revision', 0),
        }
        return {
            'ok': True, 'ticket': ticket,
            'employee': self._employee_info(employee),
            'device_tracking_enabled': bool(company.attendance_device_tracking),
            'snapshot': snapshot,
            'kiosk_delay': min(30000, max(1500, (company.attendance_kiosk_delay or 5) * 1000)),
        }

    @http.route('/attendance_multi_company/action', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_action(self, token, ticket, action, confirm_without_return=False,
                     latitude=False, longitude=False):
        if not isinstance(action, str) or action not in self._ACTIONS:
            return self._error(_('Movimiento no válido.'))
        if type(confirm_without_return) is not bool:
            return self._error(_('Confirmación no válida.'))
        for coordinate, maximum in ((latitude, 90), (longitude, 180)):
            if coordinate is not False and coordinate is not None and (
                type(coordinate) not in (int, float) or not math.isfinite(coordinate)
                or not -maximum <= coordinate <= maximum
            ):
                return self._error(_('La ubicación recibida no es válida.'))
        kiosk = self._find_kiosk(token)
        identity = request.session.get(self._SESSION_KEY) or {}
        if not kiosk or not self._ticket_valid(kiosk, token, ticket, identity):
            self._clear_identity()
            return self._error(_('El enlace o la identificación cambió. Vuelve a identificarte.'), expired=True)

        try:
            with request.env.cr.savepoint():
                # Lock and reload so changing the company list, disabling or
                # rotating this kiosk invalidates even an already-open screen.
                kiosk._lock_for_action()
                if not kiosk.active or not hmac.compare_digest(kiosk.access_token, token) or not self._ticket_valid(kiosk, token, ticket, identity):
                    raise UserError(_('La configuración del quiosco cambió. Vuelve a identificarte.'))
                companies = self._companies(kiosk)
                if identity['company_id'] not in companies.ids:
                    raise UserError(_('La empresa ya no está habilitada en este quiosco.'))
                company = companies.filtered(lambda item: item.id == identity['company_id'])
                employee = self._employees(company).with_company(company).search([
                    ('id', '=', identity['employee_id']),
                    ('company_id', '=', company.id), ('active', '=', True),
                ], limit=1)
                if not employee:
                    raise UserError(_('El empleado ya no está habilitado en este quiosco.'))
                employee._coir_lock_employee()
                if not employee.active or employee.company_id.id != company.id:
                    raise UserError(_('La ficha del empleado cambió. Vuelve a identificarte.'))
                geo = HrAttendance._get_geoip_response(
                    'kiosk', latitude=latitude or False, longitude=longitude or False,
                    device_tracking_enabled=company.attendance_device_tracking,
                ) if action in ('check_in', 'check_out') else None
                employee._coir_apply_meal_action(
                    action, expected_attendance_id=identity['attendance_id'],
                    expected_state=identity['state'], expected_revision=identity['revision'],
                    confirm_without_return=confirm_without_return,
                    geo_information=geo,
                )
                snapshot = employee._coir_meal_state()
        except (AccessError, UserError, ValidationError) as exc:
            self._clear_identity()
            return self._error(str(exc), expired=True)

        self._clear_identity()
        messages = {
            'check_in': _('Entrada registrada.'),
            'meal_start': _('Salida a comer registrada. Tu jornada sigue abierta.'),
            'meal_return': _('Regreso de comida registrado.'),
            'work_exit': _('Salida de trabajo registrada. Este tiempo cuenta dentro de tu jornada.'),
            'work_return': _('Regreso al trabajo registrado.'),
            'check_out': _('Salida final registrada.'),
        }
        return {
            'ok': True, 'message': messages[action], 'snapshot': snapshot,
            'time_label': format_datetime(
                request.env, fields.Datetime.now(), tz=employee._get_tz(),
                dt_format='dd/MM/yyyy HH:mm:ss',
            ),
        }

    @http.route('/attendance_multi_company/cancel', type='jsonrpc', auth='public', methods=['POST'])
    def kiosk_cancel(self, token, ticket=None):
        # Cancelling never creates or closes attendance and never depends on
        # an old token remaining active after an administrator changes it.
        # A delayed cancellation from an older screen must not erase a newer
        # employee's ticket. Calls from the previous release omit this field.
        identity = request.session.get(self._SESSION_KEY) or {}
        if ticket is None or (
            isinstance(token, str) and 32 <= len(token) <= 256
            and isinstance(ticket, str) and 16 <= len(ticket) <= 256
            and hmac.compare_digest(identity.get('token_digest', ''), self._digest(token))
            and hmac.compare_digest(identity.get('ticket_digest', ''), self._digest(ticket))
        ):
            self._clear_identity()
        return {'ok': True}
