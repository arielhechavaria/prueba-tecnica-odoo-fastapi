from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "tourism_event")
class TestTourismEvent(TransactionCase):
    def test_new_event_starts_in_antes(self):
        event = self.env["tourism.event"].create(
            {"name": "City tour", "start_date": "2026-11-01 09:00:00"}
        )
        self.assertEqual(event.state, "antes")

    def test_event_keeps_name_start_date_and_extra_attributes(self):
        event = self.env["tourism.event"].create(
            {
                "name": "Wine route",
                "start_date": "2026-11-02 10:30:00",
                "location": "Mendoza",
                "capacity": 20,
                "description": "Full day tour",
            }
        )
        self.assertEqual(event.name, "Wine route")
        self.assertEqual(str(event.start_date), "2026-11-02 10:30:00")
        self.assertEqual(event.location, "Mendoza")
        self.assertEqual(event.capacity, 20)
        self.assertEqual(event.description, "Full day tour")

    def test_state_only_accepts_antes_durante_despues(self):
        self.assertEqual(
            [key for key, _ in self.env["tourism.event"]._fields["state"].selection],
            ["antes", "durante", "despues"],
        )

    def test_name_and_start_date_are_required(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env["tourism.event"].create({"start_date": "2026-11-01 09:00:00"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env["tourism.event"].create({"name": "No date"})
