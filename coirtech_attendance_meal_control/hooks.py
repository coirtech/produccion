"""Initialize derived report information without creating historical absences."""


def post_init_hook(env):
    env["coir.attendance.absence"]._initialize_v4_tracking()
    env["coir.attendance.absence"]._sync_approved_leaves()
