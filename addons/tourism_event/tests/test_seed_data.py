from collections import defaultdict

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

EXPECTED = {
    "event_antes": ("antes", "reserved"),
    "event_durante": ("durante", "in_use"),
    "event_despues": ("despues", "released"),
}


@tagged("post_install", "-at_install", "tourism_event")
class TestSeedData(TransactionCase):
    def _event(self, xml_id):
        return self.env.ref(f"tourism_event.{xml_id}")

    def test_three_events_exist_one_per_state(self):
        for xml_id, (state, _status) in EXPECTED.items():
            event = self._event(xml_id)
            self.assertEqual(event.state, state, xml_id)
            self.assertTrue(event.location and event.capacity > 0, xml_id)

    def test_each_event_has_guide_bus_and_lodging(self):
        for xml_id in EXPECTED:
            kinds = set(self._event(xml_id).allocation_ids.resource_id.mapped("kind"))
            self.assertEqual(kinds, {"guide", "bus", "lodging"}, xml_id)

    def test_allocation_status_matches_event_state(self):
        for xml_id, (_state, status) in EXPECTED.items():
            statuses = set(self._event(xml_id).allocation_ids.mapped("status"))
            self.assertEqual(statuses, {status}, xml_id)

    def test_seed_allocations_never_overlap_per_resource(self):
        by_resource = defaultdict(list)
        for xml_id in EXPECTED:
            for alloc in self._event(xml_id).allocation_ids:
                by_resource[alloc.resource_id.id].append(
                    (alloc.date_start, alloc.date_end)
                )
        for slots in by_resource.values():
            slots.sort()
            for (_, prev_end), (next_start, _) in zip(slots, slots[1:]):
                self.assertLessEqual(prev_end, next_start)

    def test_seed_records_are_noupdate(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", "tourism_event"),
                "|",
                ("name", "=like", "seed\\_%"),
                ("name", "=like", "event\\_%"),
            ]
        )
        self.assertTrue(data)
        self.assertTrue(all(data.mapped("noupdate")))

    def test_xml_loading_goes_through_allocation_validation(self):
        # _load_records is the path every <record> in a data file takes.
        busy = self.env.ref("tourism_event.event_antes").allocation_ids[:1]
        with self.assertRaises(ValidationError):
            self.env["tourism.allocation"]._load_records(
                [
                    {
                        "xml_id": "tourism_event.seed_clash",
                        "noupdate": True,
                        "values": {
                            "event_id": self._event("event_durante").id,
                            "resource_id": busy.resource_id.id,
                            "date_start": busy.date_start,
                            "date_end": busy.date_end,
                        },
                    }
                ]
            )
