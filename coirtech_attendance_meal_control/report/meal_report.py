from collections import OrderedDict
from datetime import datetime

import pytz

from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import format_date, format_datetime


class MealReport(models.AbstractModel):
    _name = 'report.coirtech_attendance_meal_control.report_meal_journeys'
    _description = 'Reporte COIRTECH de asistencias y movimientos'

    def _check_report_access(self):
        if not self.env.user.has_group('hr_attendance.group_hr_attendance_officer'):
            raise AccessError(_('No tienes permiso para consultar este reporte.'))

    def _coir_real_attendances(self, docs):
        # Enforce exclusion in the report itself, including direct PDF actions
        # from native attendance selections. It is not a removable UI filter.
        docs = self.env['hr.attendance'].search([
            ('id', 'in', docs.ids), ('employee_id.coir_attendance_report_excluded', '=', False),
        ]) if docs else self.env['hr.attendance']
        return docs.filtered(lambda rec: (
            (rec.coir_managed or rec.coir_company_id.coir_meal_control_enabled)
            and not (
                not rec.coir_managed and rec.in_mode == 'technical' and rec.out_mode == 'technical'
                and rec.check_out and 0 <= (rec.check_out - rec.check_in).total_seconds() <= 1
            )
        ))

    def _coir_related_notices(self, docs, sync=True):
        """Approved leave belonging to selected real journeys, with source ACLs."""
        notices = self.env['coir.attendance.absence']
        if not docs or not notices.has_access('read'):
            return notices
        dates = docs.mapped('date')
        if sync:
            notices._sync_approved_leaves(
                date_from=min(dates), date_to=max(dates), company_ids=docs.coir_company_id.ids,
            )
        days = {(rec.coir_company_id.id, rec.employee_id.id, rec.date) for rec in docs}
        return notices.search(Domain.AND([
            Domain('state', 'in', ['approved', 'partial', 'review']),
            Domain('employee_id.coir_attendance_report_excluded', '=', False),
            Domain.OR([
                Domain.AND([
                    Domain('company_id', '=', company_id), Domain('employee_id', '=', employee_id),
                    Domain('date', '=', day),
                ]) for company_id, employee_id, day in sorted(days)
            ]),
        ]), order='date, employee_id, id')._coir_visible_in_report()

    def _coir_dataset(self, docs, absences=None):
        """One permission-checked source for PDF and Excel; no attendance sudo."""
        self._check_report_access()
        docs = self.env['hr.attendance'].browse(docs.ids).exists()
        docs.check_access('read')
        docs = self._coir_real_attendances(docs).sorted(
            key=lambda rec: (rec.coir_company_id.id, rec.employee_id.id, rec.date, rec.check_in, rec.id),
        )
        absences = (
            self.env['coir.attendance.absence'].browse(absences.ids).exists()
            if absences is not None else self._coir_related_notices(docs)
        )
        absences.check_access('read')
        absences = self.env['coir.attendance.absence'].search([
            ('id', 'in', absences.ids), ('state', 'in', ['absent', 'approved', 'partial', 'review']),
            ('employee_id.coir_attendance_report_excluded', '=', False),
        ]) if absences else self.env['coir.attendance.absence']
        # Defensive bound: even a saved/hand-built report action with source
        # absence IDs may not export days later than today in company time.
        absences = absences._coir_visible_in_report()
        if not docs and not absences:
            raise UserError(_('No hay asistencias, ausencias o incidencias para los filtros seleccionados.'))
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
            paid_seconds = (
                ((att.check_out - att.check_in).total_seconds() if att.coir_managed else att.worked_hours * 3600)
                if att.check_out else None
            )
            # The native validated value already honours overtime rules,
            # manager approval and manual corrections. Do not estimate it from
            # an arbitrary eight-hour day or add it to paid hours again.
            overtime_seconds = att.validated_overtime_hours * 3600 if att.check_out else None
            last_outing = att.coir_work_outing_ids.sorted(lambda row: (row.start, row.id))[-1:]
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
                'is_absence': False, 'is_indicator': False,
                'attendance': att, 'id': att.id, 'company': att.coir_company_id,
                'company_name': att.coir_company_id.name,
                'employee_id': employee.id, 'employee_name': employee.name,
                'department': att.department_id.name or '', 'date': att.date,
                'timezone': tz_name, 'check_in': att.check_in, 'check_out': att.check_out,
                'local_check_in': local(att.check_in), 'local_check_out': local(att.check_out),
                'paid_seconds': paid_seconds, 'meal_seconds': meal_seconds,
                'overtime_seconds': overtime_seconds,
                'work_seconds': work_seconds if finished_outings or not pending_outings else None,
                'meal_pending': int(meal_pending), 'work_pending': len(pending_outings),
                'review_note': att.coir_review_note or '', 'status': status, 'events': [],
                'leave_label': '', 'leave_periods': '', 'leave_seconds': None, 'review_reason': '',
            }

            def add_event(stamp, label, reference, interval_state='', interval_seconds=None,
                          journey_seconds=None, review_note='', sort_order=10):
                if not stamp:
                    return
                event = {
                    'is_absence': False,
                    'journey_id': att.id, 'company_id': att.coir_company_id.id,
                    'company_name': journey['company_name'],
                    'employee_name': journey['employee_name'], 'department': journey['department'],
                    'date': att.date, 'timezone': tz_name, 'stamp': stamp, 'local_stamp': local(stamp),
                    'label': label, 'reference': reference, 'interval_state': interval_state,
                    'interval_seconds': interval_seconds, 'journey_seconds': journey_seconds,
                    'overtime_seconds': overtime_seconds if sort_order == 1000000 else None,
                    'reviewed': bool(att.coir_review_note),
                    'review_note': review_note or att.coir_review_note or '', 'sort_order': sort_order,
                    'leave_label': '', 'leave_periods': '', 'leave_seconds': None, 'review_reason': '',
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
                    'is_absence': False, 'employee_id': employee.id,
                    'company_name': journey['company_name'], 'company_id': att.coir_company_id.id,
                    'employee_name': employee.name, 'department': journey['department'], 'date': att.date,
                    'timezone': tz_name, 'journeys': 0, 'closed': 0, 'open': 0,
                    'first_entry': local(att.check_in), 'last_exit': None,
                    'paid_seconds': 0.0, 'meal_seconds': 0.0, 'meal_confirmed': 0,
                    'work_seconds': 0.0, 'work_confirmed': 0,
                    'meal_pending': 0, 'work_pending': 0, 'reviewed': 0,
                    'notice_label': '', 'leave_label': '', 'leave_periods': '',
                    'leave_seconds': None, 'review_reason': '',
                    'overtime_seconds': 0.0,
                    'meal_start': None, 'meal_end': None, 'meal_state': '',
                    'work_start': None, 'work_end': None, 'work_state': '',
                    '_meal_stamp': None, '_work_stamp': None,
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
                item['overtime_seconds'] += overtime_seconds
            # Keep the latest matching pair, not the latest non-empty return.
            # A newer unfinished interval must never inherit an older return.
            if att.coir_meal_start and (
                    not item['_meal_stamp'] or att.coir_meal_start >= item['_meal_stamp']):
                item.update({
                    '_meal_stamp': att.coir_meal_start,
                    'meal_start': local(att.coir_meal_start), 'meal_end': local(att.coir_meal_end),
                    'meal_state': (
                        _('Regreso registrado') if att.coir_meal_end
                        else (_('Sin regreso al cierre') if att.check_out else _('Regreso pendiente'))
                    ),
                })
            if last_outing and (not item['_work_stamp'] or last_outing.start >= item['_work_stamp']):
                item.update({
                    '_work_stamp': last_outing.start,
                    'work_start': local(last_outing.start), 'work_end': local(last_outing.end),
                    'work_state': (
                        _('Regreso registrado') if last_outing.end
                        else (_('Sin regreso al cierre') if att.check_out else _('Regreso pendiente'))
                    ),
                })
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
                item['overtime_seconds'] = None
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

        # Independent notices never create worked journeys or an artificial punch.
        # Only an obsolete automatic FALTA is suppressed by actual attendance.
        # Approved leave and RH review must coexist with the real clock times.
        absences = absences.filtered(lambda rec: rec.state != 'absent' or (
            rec.company_id.id, rec.employee_id.id, rec.date
        ) not in summary)
        for absence in absences:
            employee = absence.employee_id
            is_absence = absence.state == 'absent'
            label = 'FALTA' if is_absence else (absence.report_label or _('REVISAR RH'))
            leave_label = absence.leave_label or ''
            leave_periods = absence.leave_periods or ''
            # An unknown/flexible schedule is sent to RH without estimating a
            # duration. A blank is preferable to claiming zero authorised time.
            leave_seconds = absence.leave_hours * 3600 if absence.leave_hours > 0 else None
            review_reason = absence.review_reason or ''
            absence_event = {
                'is_absence': is_absence, 'journey_id': None,
                'company_id': absence.company_id.id, 'company_name': absence.company_id.name,
                'employee_name': employee.name, 'department': absence.department_id.name or '',
                'date': absence.date, 'timezone': absence.timezone,
                'stamp': None, 'local_stamp': None, 'label': label,
                'reference': '%s-%s' % ('F' if is_absence else 'A', absence.id),
                'interval_state': label,
                'interval_seconds': None, 'journey_seconds': None,
                'overtime_seconds': None,
                'reviewed': False, 'review_note': '', 'sort_order': 0,
                'leave_label': leave_label, 'leave_periods': leave_periods,
                'leave_seconds': leave_seconds, 'review_reason': review_reason,
            }
            journeys.append({
                'is_absence': is_absence, 'is_indicator': True,
                'attendance': self.env['hr.attendance'], 'id': None,
                'company': absence.company_id, 'company_name': absence.company_id.name,
                'employee_id': employee.id, 'employee_name': employee.name,
                'department': absence.department_id.name or '', 'date': absence.date,
                'timezone': absence.timezone, 'check_in': None, 'check_out': None,
                'local_check_in': None, 'local_check_out': None,
                'paid_seconds': None, 'meal_seconds': None, 'work_seconds': None,
                'overtime_seconds': None,
                'meal_pending': 0, 'work_pending': 0, 'review_note': '',
                'status': label, 'events': [absence_event],
                'leave_label': leave_label, 'leave_periods': leave_periods,
                'leave_seconds': leave_seconds, 'review_reason': review_reason,
            })
            key = (absence.company_id.id, employee.id, absence.date)
            if key in summary:
                # Preserve the genuine first entry, exits, movement counters and
                # paid hours. Authorised hours occupy their own separate column.
                summary[key].update({
                    'notice_label': label, 'leave_label': leave_label,
                    'leave_periods': leave_periods, 'leave_seconds': leave_seconds,
                    'review_reason': review_reason,
                })
            else:
                item = {
                    'is_absence': is_absence, 'absence_id': absence.id,
                    'company_name': absence.company_id.name, 'company_id': absence.company_id.id,
                    'employee_id': employee.id, 'employee_name': employee.name,
                    'department': absence.department_id.name or '', 'date': absence.date,
                    'timezone': absence.timezone, 'journeys': 0, 'closed': 0, 'open': 0,
                    'first_entry': None, 'last_exit': None, 'paid_seconds': None,
                    'meal_seconds': None, 'meal_confirmed': 0, 'work_seconds': None,
                    'work_confirmed': 0, 'meal_pending': 0, 'work_pending': 0,
                    'reviewed': 0, 'status': label,
                    'notice_label': '' if is_absence else label,
                    'leave_label': leave_label, 'leave_periods': leave_periods,
                    'leave_seconds': leave_seconds, 'review_reason': review_reason,
                    'overtime_seconds': None,
                    'meal_start': None, 'meal_end': None, 'meal_state': '',
                    'work_start': None, 'work_end': None, 'work_state': '',
                }
                summary[key] = item
                summaries.append(item)
        summaries.sort(key=lambda row: (row['company_id'], row['employee_id'], row['date']))
        journeys.sort(key=lambda row: (
            row['company'].id, row['employee_id'], row['date'], row['check_in'] or datetime.min, row['id'] or 0,
        ))
        events = [event for journey in journeys for event in journey['events']]
        for item in summaries:
            item['journey_counts'] = '%s / %s' % (item['closed'], item['open']) if item['journeys'] else ''
            item['pending_counts'] = '%s / %s' % (item['meal_pending'], item['work_pending']) if item['journeys'] else ''
            item['notice_detail'] = '\n'.join(filter(None, (
                item['notice_label'], item['leave_periods'], item['review_reason'],
            )))
        return {'docs': docs, 'absences': absences, 'journeys': journeys, 'events': events, 'summary': summaries}

    def _get_report_values(self, docids, data=None):
        data = data or {}
        dataset = self._coir_dataset(
            self.env['hr.attendance'].browse(data.get('coir_attendance_ids', docids) or []).exists(),
            (self.env['coir.attendance.absence'].browse(data['coir_absence_ids'] or []).exists()
             if 'coir_absence_ids' in data else None),
        )
        batches = []
        layouts = self.env['coir.attendance.report.layout']
        for company in (dataset['docs'].coir_company_id | dataset['absences'].company_id).sorted('id'):
            records = dataset['docs'].filtered(lambda row: row.coir_company_id == company)
            absent_records = dataset['absences'].filtered(lambda row: row.company_id == company)
            batches.append({
                'company': company,
                'records': records, 'document': records[:1] or absent_records[:1],
                'journeys': [row for row in dataset['journeys'] if row['company'] == company],
                'summary': [row for row in dataset['summary'] if row['company_id'] == company.id],
                'events': [row for row in dataset['events'] if row['company_id'] == company.id],
                'summary_blocks': self._coir_pdf_blocks(layouts._coir_get_columns(company, 'pdf', 'summary')),
                'detail_blocks': self._coir_pdf_blocks(layouts._coir_get_columns(company, 'pdf', 'detail')),
            })
        return {
            'doc_ids': dataset['docs'].ids, 'doc_model': 'hr.attendance', 'docs': dataset['docs'],
            'batches': batches, 'format_stamp': self._format_stamp,
            'format_seconds': self._format_seconds,
            'format_day': lambda day: format_date(self.env, day, date_format='dd/MM/yyyy'),
            'format_cell': self._coir_pdf_cell,
            'absence_cell': self._coir_absence_cell,
        }

    @staticmethod
    def _coir_pdf_blocks(columns):
        """Keep wide user layouts readable without revealing hidden columns.

        New columns keep the saved order. A selected employee/date identity is
        repeated in later horizontal blocks only after its first appearance.
        No identity or source ID is silently added to the user's selection.
        """
        blocks, pending, seen = [], list(columns), set()
        while pending:
            repeated = [column for column in columns if (
                column['key'] in ('employee_name', 'date') and column['key'] in seen
            )]
            block_columns = repeated + pending[:8 - len(repeated)]
            pending = pending[8 - len(repeated):]
            seen.update(column['key'] for column in block_columns)
            blocks.append({'columns': block_columns})
        for index, block in enumerate(blocks, 1):
            block.update({'index': index, 'count': len(blocks)})
        return blocks

    @staticmethod
    def _coir_export_value(row, column, section):
        key, kind = column['key'], column['kind']
        if row.get('is_absence') and key in ('first_entry', 'status', 'label', 'interval_state'):
            return 'FALTA', 'text'
        value = row.get(key)
        if section == 'detail' and key == 'reviewed':
            return (_('Sí') if value else _('No')), 'text'
        return value, kind

    @staticmethod
    def _coir_absence_cell(row, columns, column):
        if not row.get('is_absence'):
            return False
        markers = {'first_entry', 'status', 'label', 'interval_state'}
        return column['key'] in markers or not any(item['key'] in markers for item in columns)

    def _coir_pdf_cell(self, row, column, section):
        value, kind = self._coir_export_value(row, column, section)
        if value is None or value is False or value == '':
            return '—'
        if kind == 'date':
            return value.strftime('%d/%m/%Y')
        if kind == 'datetime':
            # Dataset timestamps are already converted to the effective local
            # timezone (or explicitly UTC in the column named UTC).
            return value.strftime('%d/%m/%Y %H:%M')
        if kind == 'duration':
            return self._format_seconds(value)
        return str(value)

    def _format_stamp(self, stamp, timezone):
        if not stamp:
            return '—'
        return format_datetime(self.env, stamp, tz=timezone, dt_format='dd/MM/yyyy HH:mm')

    @staticmethod
    def _format_seconds(seconds):
        if seconds is None:
            return '—'
        minutes = round(seconds / 60)
        sign = '-' if minutes < 0 else ''
        return sign + '%02d:%02d' % divmod(abs(minutes), 60)
