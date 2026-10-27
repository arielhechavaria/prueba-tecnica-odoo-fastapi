from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "tourism_event")
class TestTourismEventTransitions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bus = cls.env["tourism.resource"].create({"name": "Bus 1", "kind": "bus"})
        cls.guide = cls.env["tourism.resource"].create({"name": "Ana", "kind": "guide"})
        cls.event = cls.env["tourism.event"].create(
            {"name": "City tour", "start_date": "2026-11-01 09:00:00"}
        )
        cls.first = cls._allocate(cls.bus)
        cls.second = cls._allocate(cls.guide)

    @classmethod
    def _allocate(cls, resource):
        return cls.env["tourism.allocation"].create(
            {
                "event_id": cls.event.id,
                "resource_id": resource.id,
                "date_start": "2026-11-01 09:00:00",
                "date_end": "2026-11-01 18:00:00",
            }
        )

    def _statuses(self):
        return self.event.allocation_ids.mapped("status")

    def test_start_moves_event_to_durante_and_reserved_to_in_use(self):
        self.event.action_start()
        self.assertEqual(self.event.state, "durante")
        self.assertEqual(self._statuses(), ["in_use", "in_use"])

    def test_finish_moves_event_to_despues_and_in_use_to_released(self):
        self.event.action_start()
        self.event.action_finish()
        self.assertEqual(self.event.state, "despues")
        self.assertEqual(self._statuses(), ["released", "released"])

    def test_finish_frees_the_resource_for_another_event(self):
        self.event.action_start()
        self.event.action_finish()
        other = self.env["tourism.event"].create(
            {"name": "Wine route", "start_date": "2026-11-01 10:00:00"}
        )
        self.env["tourism.allocation"].create(
            {
                "event_id": other.id,
                "resource_id": self.bus.id,
                "date_start": "2026-11-01 09:00:00",
                "date_end": "2026-11-01 18:00:00",
            }
        )

    def test_cannot_finish_from_antes(self):
        with self.assertRaises(ValidationError):
            self.event.action_finish()
        self.assertEqual(self.event.state, "antes")
        self.assertEqual(self._statuses(), ["reserved", "reserved"])

    def test_cannot_start_twice(self):
        self.event.action_start()
        with self.assertRaises(ValidationError):
            self.event.action_start()
        self.assertEqual(self.event.state, "durante")
        self.assertEqual(self._statuses(), ["in_use", "in_use"])

    def test_cannot_go_back_from_despues(self):
        self.event.action_start()
        self.event.action_finish()
        for action in (self.event.action_start, self.event.action_finish):
            with self.assertRaises(ValidationError):
                action()
        self.assertEqual(self.event.state, "despues")
        self.assertEqual(self._statuses(), ["released", "released"])

    def test_transition_does_not_touch_other_events_allocations(self):
        other = self.env["tourism.event"].create(
            {"name": "Wine route", "start_date": "2026-11-02 10:00:00"}
        )
        untouched = self.env["tourism.allocation"].create(
            {
                "event_id": other.id,
                "resource_id": self.bus.id,
                "date_start": "2026-11-02 09:00:00",
                "date_end": "2026-11-02 18:00:00",
            }
        )
        self.event.action_start()
        self.assertEqual(untouched.status, "reserved")

    def test_start_keeps_released_allocations_released(self):
        self.second.status = "released"
        self.event.action_start()
        self.assertEqual(self.first.status, "in_use")
        self.assertEqual(self.second.status, "released")
