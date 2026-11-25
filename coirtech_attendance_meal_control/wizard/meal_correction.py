from odoo import api, fields, models


class CoirMealCorrection(models.TransientModel):
    _name = "coir.meal.correction"
    _description = "Revisión de comida COIRTECH"

    attendance_id = fields.Many2one(
        "hr.attendance", string="Jornada", required=True, readonly=True,
        ondelete="cascade",
    )
    meal_start = fields.Datetime(string="Salida a comer")
    meal_end = fields.Datetime(string="Regreso de comida")
    reason = fields.Text(string="Motivo de la corrección", required=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        attendance = self.env["hr.attendance"].browse(values.get("attendance_id")).exists()
        if attendance:
            if "meal_start" in field_names and "default_meal_start" not in self.env.context:
                values["meal_start"] = attendance.coir_meal_start
            if "meal_end" in field_names and "default_meal_end" not in self.env.context:
                values["meal_end"] = attendance.coir_meal_end
        return values

    def action_apply(self):
        self.ensure_one()
        self.attendance_id._coir_correct_meal(self.meal_start, self.meal_end, self.reason)
        return {"type": "ir.actions.act_window_close"}


class CoirWorkCorrection(models.TransientModel):
    _name = "coir.work.correction"
    _description = "Revisión de salida de trabajo COIRTECH"

    outing_id = fields.Many2one("coir.work.outing", string="Salida temporal", required=True, readonly=True, ondelete="cascade")
    start = fields.Datetime(string="Salida de trabajo", required=True)
    end = fields.Datetime(string="Regreso al trabajo")
    reason = fields.Text(string="Motivo de la corrección", required=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        outing = self.env["coir.work.outing"].browse(values.get("outing_id")).exists()
        if outing:
            if "start" in field_names and "default_start" not in self.env.context:
                values["start"] = outing.start
            if "end" in field_names and "default_end" not in self.env.context:
                values["end"] = outing.end
        return values

    def action_apply(self):
        self.ensure_one()
        self.outing_id._coir_correct(self.start, self.end, self.reason)
        return {"type": "ir.actions.act_window_close"}
