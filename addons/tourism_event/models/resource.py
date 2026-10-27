from odoo import fields, models


class TourismResource(models.Model):
    _name = "tourism.resource"
    _description = "Tourism resource"
    _order = "name"

    name = fields.Char(required=True)
    kind = fields.Selection(
        [("guide", "Guide"), ("bus", "Bus"), ("lodging", "Lodging")],
        required=True,
    )
    allocation_ids = fields.One2many("tourism.allocation", "resource_id")
