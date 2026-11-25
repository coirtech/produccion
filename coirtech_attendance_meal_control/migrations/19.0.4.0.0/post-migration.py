"""Keep V3 absence provenance and read the existing approved Time Off records."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    # Before V4 every row of this model originated as an automatic FALTA,
    # including those later resolved by an entry or cancelled by a leave.
    cr.execute("""
        UPDATE coir_attendance_absence
           SET was_automatic_absence = TRUE
         WHERE state IN ('absent', 'resolved', 'cancelled')
    """)
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["coir.attendance.absence"].invalidate_model(["was_automatic_absence"])
    env["coir.attendance.absence"]._initialize_v4_tracking()
    env["coir.attendance.absence"]._sync_approved_leaves()
