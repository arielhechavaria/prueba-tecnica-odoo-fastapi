from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

GUARDED_FIELDS = {"resource_id", "date_start", "date_end", "status"}


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

    def init(self):
        # Race-safe backstop: the validation below cannot see concurrent transactions.
        self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        self.env.cr.execute(
            """
            ALTER TABLE tourism_allocation
                DROP CONSTRAINT IF EXISTS tourism_allocation_no_overlap;
            ALTER TABLE tourism_allocation
                ADD CONSTRAINT tourism_allocation_no_overlap
                EXCLUDE USING gist (
                    resource_id WITH =,
                    tsrange(date_start, date_end) WITH &&
                ) WHERE (status <> 'released');
            """
        )

    def _validate_slot(self, resource_id, date_start, date_end, status, ignore=None):
        """Raise a readable error before the database constraint would fire."""
        start = fields.Datetime.to_datetime(date_start)
        end = fields.Datetime.to_datetime(date_end)
        if end <= start:
            raise ValidationError(_("The allocation must end after it starts."))
        if status == "released":
            return
        domain = [
            ("resource_id", "=", resource_id),
            ("status", "!=", "released"),
            ("date_start", "<", end),
            ("date_end", ">", start),
        ]
        if ignore:
            domain.append(("id", "not in", ignore.ids))
        clash = self.search(domain, limit=1)
        if clash:
            raise ValidationError(
                _(
                    "%(resource)s is already allocated to %(event)s in that period.",
                    resource=clash.resource_id.name,
                    event=clash.event_id.name,
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if {"resource_id", "date_start", "date_end"} <= vals.keys():
                self._validate_slot(
                    vals["resource_id"],
                    vals["date_start"],
                    vals["date_end"],
                    vals.get("status", "reserved"),
                )
        return super().create(vals_list)

    def write(self, vals):
        if GUARDED_FIELDS & vals.keys():
            for allocation in self:
                self._validate_slot(
                    vals.get("resource_id", allocation.resource_id.id),
                    vals.get("date_start", allocation.date_start),
                    vals.get("date_end", allocation.date_end),
                    vals.get("status", allocation.status),
                    ignore=allocation,
                )
        return super().write(vals)
