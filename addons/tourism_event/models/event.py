from odoo import fields, models


class TourismEvent(models.Model):
    _name = "tourism.event"
    _description = "Tourism event"
    _order = "start_date desc, id desc"

    name = fields.Char(required=True)
    start_date = fields.Datetime(required=True)
    state = fields.Selection(
        [("antes", "Antes"), ("durante", "Durante"), ("despues", "Despues")],
        default="antes",
        required=True,
    )
    location = fields.Char()
    capacity = fields.Integer()
    description = fields.Text()
    allocation_ids = fields.One2many("tourism.allocation", "event_id")
