from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "tourism_event")
class TestTourismAllocation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bus = cls.env["tourism.resource"].create({"name": "Bus 1", "kind": "bus"})
        cls.guide = cls.env["tourism.resource"].create({"name": "Ana", "kind": "guide"})
        cls.event = cls.env["tourism.event"].create(
            {"name": "City tour", "start_date": "2026-11-01 09:00:00"}
        )
        cls.other_event = cls.env["tourism.event"].create(
            {"name": "Wine route", "start_date": "2026-11-01 10:00:00"}
        )

    def _allocate(self, resource, start, end, event=None):
        return self.env["tourism.allocation"].create(
            {
                "event_id": (event or self.event).id,
                "resource_id": resource.id,
                "date_start": start,
                "date_end": end,
            }
        )

    def test_resource_kind_accepts_guide_bus_lodging(self):
        self.assertEqual(
            [key for key, _ in self.env["tourism.resource"]._fields["kind"].selection],
            ["guide", "bus", "lodging"],
        )

    def test_new_allocation_is_reserved(self):
        allocation = self._allocate(
            self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00"
        )
        self.assertEqual(allocation.status, "reserved")

    def test_overlapping_allocation_of_same_resource_is_rejected(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        with self.assertRaises(ValidationError):
            self._allocate(
                self.bus,
                "2026-11-01 17:00:00",
                "2026-11-01 20:00:00",
                event=self.other_event,
            )

    def test_back_to_back_allocations_are_allowed(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        allocation = self._allocate(
            self.bus,
            "2026-11-01 18:00:00",
            "2026-11-01 20:00:00",
            event=self.other_event,
        )
        self.assertTrue(allocation.id)

    def test_same_dates_on_different_resources_are_allowed(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        allocation = self._allocate(
            self.guide, "2026-11-01 09:00:00", "2026-11-01 18:00:00"
        )
        self.assertTrue(allocation.id)

    def test_released_allocation_does_not_block_the_resource(self):
        first = self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        first.status = "released"
        allocation = self._allocate(
            self.bus,
            "2026-11-01 10:00:00",
            "2026-11-01 12:00:00",
            event=self.other_event,
        )
        self.assertTrue(allocation.id)

    def _insert_sql(self, resource, start, end, status="reserved"):
        self.cr.execute(
            "INSERT INTO tourism_allocation"
            " (event_id, resource_id, date_start, date_end, status)"
            " VALUES (%s, %s, %s, %s, %s)",
            (self.other_event.id, resource.id, start, end, status),
        )

    def test_database_rejects_overlap_without_the_python_check(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self._insert_sql(
                    self.bus, "2026-11-01 17:00:00", "2026-11-01 20:00:00"
                )

    def test_database_allows_back_to_back_and_released_rows(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 18:00:00")
        with self.cr.savepoint():
            self._insert_sql(self.bus, "2026-11-01 18:00:00", "2026-11-01 20:00:00")
        with self.cr.savepoint():
            self._insert_sql(
                self.bus, "2026-11-01 10:00:00", "2026-11-01 12:00:00", "released"
            )

    def test_end_must_be_after_start(self):
        with self.assertRaises(ValidationError):
            self._allocate(self.bus, "2026-11-01 18:00:00", "2026-11-01 09:00:00")

    def test_moving_an_allocation_onto_a_busy_slot_is_rejected(self):
        self._allocate(self.bus, "2026-11-01 09:00:00", "2026-11-01 12:00:00")
        later = self._allocate(
            self.bus,
            "2026-11-01 13:00:00",
            "2026-11-01 15:00:00",
            event=self.other_event,
        )
        with self.assertRaises(ValidationError):
            later.write({"date_start": "2026-11-01 11:00:00"})
