"""Refresh presentation from native Time Off, retaining all source records."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    absence = env['coir.attendance.absence']
    # Earlier rows already recorded the approved request's provenance. Keep
    # that history when the same projection also handles submitted requests.
    previous = absence.sudo().search([
        ('had_approved_leave', '=', True), ('had_leave_request', '=', False),
    ])
    if previous:
        previous._service().write({'had_leave_request': True})

    # Preserve users' headings, column ordering and visibility. Only replace
    # the exact old default headings that would mislabel an unapproved period.
    columns = env['coir.attendance.report.layout.line']
    for key, previous_label, current_label in (
            ('leave_periods', 'Periodo autorizado', 'Periodo de ausencia'),
            ('notice_detail', 'Ausencia aprobada / revisión RH', 'Ausencia / revisión RH')):
        columns.search([('column_key', '=', key), ('label', '=', previous_label)]).write({
            'label': current_label,
        })

    absence._initialize_v4_tracking()
    absence._sync_approved_leaves()
