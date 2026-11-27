"""V4.4: refresh existing projected names from original Time Off sources.

Do not alter approvals, absence types, genuine attendances or automatic
absence history. The existing idempotent reconciler updates only projected
attendance indicators for known Time Off requests.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Re-evaluate existing approved/submitted/cancelled source requests. This
    # fixes previously cached 'Home Office' labels for Mexican translations.
    # Existing records are reconciled; no historical FALTA is backfilled.
    env["coir.attendance.absence"].sudo()._sync_approved_leaves()
