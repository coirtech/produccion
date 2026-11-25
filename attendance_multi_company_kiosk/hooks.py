import inspect

from odoo import _
from odoo.exceptions import UserError


def post_init_hook(env):
    """A dependency name alone cannot express the minimum six-action API."""
    employee = env['hr.employee']
    attendance = env['hr.attendance']
    apply_action = getattr(employee, '_coir_apply_meal_action', None)
    state = getattr(employee, '_coir_meal_state', None)
    compatible = callable(apply_action) and callable(state)
    compatible = compatible and {'coir_revision', 'coir_work_outing_ids'}.issubset(attendance._fields)
    if compatible:
        parameters = inspect.signature(apply_action).parameters
        compatible = 'expected_revision' in parameters or any(
            item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
        )
    if not compatible:
        raise UserError(_(
            'Actualiza primero el módulo de Asistencias a una versión con los seis movimientos '
            '(2.0 o posterior). Quiosco Multiempresa se ha verificado con la versión 4.2.'
        ))
