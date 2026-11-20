from collections import OrderedDict

import pytz

from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_date, format_datetime


class MealReport(models.AbstractModel):
    _name = 'report.coirtech_attendance_meal_control.report_meal_journeys'
    _description = 'Reporte COIRTECH de asistencias y movimientos'

    def _check_report_access(self):
        if not self.env.user.has_group('hr_attendance.group_hr_attendance_officer'):
            raise AccessError(_('No tienes permiso para consultar este reporte.'))

    def _coir_dataset(self, docs):
        """One permission-checked source for PDF and Excel; no attendance sudo."""
        self._check_report_access()
        docs.check_access('read')
        docs = docs.filtered('coir_managed').sorted(
            key=lambda rec: (rec.coir_company_id.id, rec.employee_id.id, rec.date, rec.check_in, rec.id),
        )
        if not docs:
            raise UserError(_('No hay jornadas COIRTECH para los filtros seleccionados.'))
        docs.coir_work_outing_ids.check_access('read')
        journeys, events, summary = [], [], OrderedDict()
        for att in docs:
            employee = att.employee_id
            # Only timezone resolution needs private employee/calendar fields.
            tz_name = employee.sudo()._get_tz() or 'UTC'
            timezone = pytz.timezone(tz_name)

            def local(stamp):
                return pytz.UTC.localize(stamp).astimezone(timezone).replace(tzinfo=None) if stamp else None

            finished_outings = att.coir_work_outing_ids.filtered('end')
            pending_outings = att.coir_work_outing_ids.filtered(lambda row: not row.end)
            meal_pending = bool(att.coir_meal_start and not att.coir_meal_end)
            meal_seconds = (
                (att.coir_meal_end - att.coir_meal_start).total_seconds()
                if att.coir_meal_start and att.coir_meal_end else None
            )
            work_seconds = sum((row.end - row.start).total_seconds() for row in finished_outings)
            paid_seconds = (att.check_out - att.check_in).total_seconds() if att.check_out else None
            pending = meal_pending or bool(pending_outings)
            if att.check_out:
                status = _('Finalizada con movimientos pendientes') if pending else _('Finalizada')
            elif meal_pending:
                status = _('Jornada abierta — en comida')
            elif pending_outings:
                status = _('Jornada abierta — salida de trabajo')
            else:
                status = _('Jornada abierta')
            journey = {
                'attendance': att, 'id': att.id, 'company': att.coir_company_id,
                'company_name': att.coir_company_id.name,
                'employee_id': employee.id, 'employee_name': employee.name,
                'department': att.department_id.name or '', 'date': att.date,
                'timezone': tz_name, 'check_in': att.check_in, 'check_out': att.check_out,
                'local_check_in': local(att.check_in), 'local_check_out': local(att.check_out),
                'paid_seconds': paid_seconds, 'meal_seconds': meal_seconds,
                'work_seconds': work_seconds if finished_outings or not pending_outings else None,
                'meal_pending': int(meal_pending), 'work_pending': len(pending_outings),
                'review_note': att.coir_review_note or '', 'status': status, 'events': [],
            }

            def add_event(stamp, label, reference, interval_state='', interval_seconds=None,
                          journey_seconds=None, review_note='', sort_order=10):
                if not stamp:
                    return
                event = {
                    'journey_id': att.id, 'company_name': journey['company_name'],
                    'employee_name': journey['employee_name'], 'department': journey['department'],
                    'date': att.date, 'timezone': tz_name, 'stamp': stamp, 'local_stamp': local(stamp),
                    'label': label, 'reference': reference, 'interval_state': interval_state,
                    'interval_seconds': interval_seconds, 'journey_seconds': journey_seconds,
                    'reviewed': bool(att.coir_review_note),
                    'review_note': review_note or att.coir_review_note or '', 'sort_order': sort_order,
                }
                journey['events'].append(event)

            add_event(att.check_in, _('Entrada'), 'J-%s' % att.id, _('Registrada'), sort_order=0)
            meal_state = (
                _('Regreso registrado') if att.coir_meal_end
                else (_('Sin regreso al cierre') if att.check_out else _('Regreso pendiente'))
            )
            add_event(att.coir_meal_start, _('Salir a comer'), 'C-%s' % att.id, meal_state, sort_order=10)
            add_event(att.coir_meal_end, _('Regresar de comida'), 'C-%s' % att.id,
                      _('Regreso registrado'), interval_seconds=meal_seconds, sort_order=11)
            for index, outing in enumerate(att.coir_work_outing_ids.sorted(lambda row: (row.start, row.id))):
                outing_state = (
                    _('Regreso registrado') if outing.end
                    else (_('Sin regreso al cierre') if att.check_out else _('Regreso pendiente'))
                )
                add_event(outing.start, _('Salida de trabajo'), 'S-%s' % outing.id,
                          outing_state, review_note=outing.review_note or '', sort_order=20 + index * 2)
                add_event(outing.end, _('Regreso al trabajo'), 'S-%s' % outing.id,
                          _('Regreso registrado'),
                          interval_seconds=(outing.end - outing.start).total_seconds() if outing.end else None,
                          review_note=outing.review_note or '', sort_order=21 + index * 2)
            add_event(att.check_out, _('Salida final'), 'J-%s' % att.id, status,
                      journey_seconds=paid_seconds, sort_order=1000000)
            journey['events'].sort(key=lambda event: (event['stamp'], event['sort_order']))
            events.extend(journey['events'])
            journeys.append(journey)

            key = (att.coir_company_id.id, employee.id, att.date)
            if key not in summary:
                summary[key] = {
                    'company_name': journey['company_name'], 'company_id': att.coir_company_id.id,
                    'employee_name': employee.name, 'department': journey['department'], 'date': att.date,
                    'timezone': tz_name, 'journeys': 0, 'closed': 0, 'open': 0,
                    'first_entry': local(att.check_in), 'last_exit': None,
                    'paid_seconds': 0.0, 'meal_seconds': 0.0, 'meal_confirmed': 0,
                    'work_seconds': 0.0, 'work_confirmed': 0,
                    'meal_pending': 0, 'work_pending': 0, 'reviewed': 0,
                }
            item = summary[key]
            item['journeys'] += 1
            item['closed'] += int(bool(att.check_out))
            item['open'] += int(not att.check_out)
            item['first_entry'] = min(item['first_entry'], local(att.check_in))
            if att.check_out:
                stamp = local(att.check_out)
                item['last_exit'] = max(item['last_exit'], stamp) if item['last_exit'] else stamp
                item['paid_seconds'] += paid_seconds
            if meal_seconds is not None:
                item['meal_seconds'] += meal_seconds
                item['meal_confirmed'] += 1
            item['work_seconds'] += work_seconds
            item['work_confirmed'] += len(finished_outings)
            item['meal_pending'] += int(meal_pending)
            item['work_pending'] += len(pending_outings)
            item['reviewed'] += int(bool(att.coir_review_note))

        summaries = list(summary.values())
        for item in summaries:
            if not item['closed']:
                item['paid_seconds'] = None
            if not item['meal_confirmed'] and item['meal_pending']:
                item['meal_seconds'] = None
            if not item['work_confirmed'] and item['work_pending']:
                item['work_seconds'] = None
            if item['open']:
                item['status'] = _('Parcial — jornada abierta') if item['closed'] else _('Pendiente — jornada abierta')
            elif item['meal_pending'] or item['work_pending']:
                item['status'] = _('Finalizada con movimientos pendientes')
            else:
                item['status'] = _('Finalizada')
        return {'docs': docs, 'journeys': journeys, 'events': events, 'summary': summaries}

    def _get_report_values(self, docids, data=None):
        dataset = self._coir_dataset(self.env['hr.attendance'].browse(docids).exists())
        batches = []
        for company in dataset['docs'].coir_company_id:
            batches.append({
                'company': company,
                'records': dataset['docs'].filtered(lambda row: row.coir_company_id == company),
                'journeys': [row for row in dataset['journeys'] if row['company'] == company],
                'summary': [row for row in dataset['summary'] if row['company_id'] == company.id],
            })
        return {
            'doc_ids': dataset['docs'].ids, 'doc_model': 'hr.attendance', 'docs': dataset['docs'],
            'batches': batches, 'format_stamp': self._format_stamp,
            'format_seconds': self._format_seconds,
            'format_day': lambda day: format_date(self.env, day, date_format='dd/MM/yyyy'),
        }

    def _format_stamp(self, stamp, timezone):
        if not stamp:
            return '—'
        return format_datetime(self.env, stamp, tz=timezone, dt_format='dd/MM/yyyy HH:mm')

    @staticmethod
    def _format_seconds(seconds):
        if seconds is None:
            return '—'
        minutes = round(seconds / 60)
        return '%02d:%02d' % divmod(minutes, 60)
