from odoo import fields, models


class CoirMealSection(models.Model):
    _name = "coir.meal.section"
    _description = "Sección de comidas COIRTECH"
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(string="Sección", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Empresa", required=True,
        default=lambda self: self.env.company, index=True,
    )
