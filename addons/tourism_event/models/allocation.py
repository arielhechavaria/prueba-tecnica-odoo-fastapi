from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TourismAllocation(models.Model):
    _name = "tourism.allocation"
    _description = "Resource allocation to a tourism event"
    _order = "date_start"

    event_id = fields.Many2one(
        "tourism.event", required=True, ondelete="cascade", index=True
    )
    resource_id = fields.Many2one(
        "tourism.resource", required=True, ondelete="restrict", index=True
    )
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    status = fields.Selection(
        [("reserved", "Reserved"), ("in_use", "In use"), ("released", "Released")],
        default="reserved",
        required=True,
    )

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for allocation in self:
            if allocation.date_end <= allocation.date_start:
                raise ValidationError("The allocation must end after it starts.")

    @api.constrains("resource_id", "date_start", "date_end", "status")
    def _check_no_overlap(self):
        for allocation in self.filtered(lambda a: a.status != "released"):
            clash = self.search(
                [
                    ("id", "!=", allocation.id),
                    ("resource_id", "=", allocation.resource_id.id),
                    ("status", "!=", "released"),
                    ("date_start", "<", allocation.date_end),
                    ("date_end", ">", allocation.date_start),
                ],
                limit=1,
            )
            if clash:
                raise ValidationError(
                    f"{allocation.resource_id.name} is already allocated "
                    f"to {clash.event_id.name} in that period."
                )
