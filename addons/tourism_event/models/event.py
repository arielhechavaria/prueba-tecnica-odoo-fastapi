from odoo import fields, models
from odoo.exceptions import ValidationError


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

    def _transition(self, source, target, alloc_from, alloc_to):
        """Move events strictly from `source` to `target`, shifting their allocations."""
        for event in self:
            if event.state != source:
                raise ValidationError(
                    f"Event '{event.name}' cannot go to '{target}' from '{event.state}'."
                )
        # Goes through tourism.allocation.write so its slot validation is reused.
        self.allocation_ids.filtered(lambda a: a.status == alloc_from).write(
            {"status": alloc_to}
        )
        self.write({"state": target})

    def action_start(self):
        self._transition("antes", "durante", "reserved", "in_use")

    def action_finish(self):
        self._transition("durante", "despues", "in_use", "released")
