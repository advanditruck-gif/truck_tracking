import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import retention


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {
                "id": 1,
                "t": "location",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/location.jpg", "location": "Town"},
            },
            {
                "id": 2,
                "t": "fuel",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/fuel.jpg", "amount": 100},
            },
            {
                "id": 3,
                "t": "other_expense",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/expense.jpg", "amount": 50},
            },
            {
                "id": 4,
                "t": "start_km",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/odometer.jpg", "km": 123},
            },
            {
                "id": 5,
                "t": "generator_start",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/generator.jpg", "hours": 123},
            },
            {
                "id": 6,
                "t": "stop_km",
                "at": "2026-11-01T10:00:00Z",
                "d": {"image_path": "events/odometer-stop.jpg", "km": 456},
            },
        ]

    @patch.object(retention.db, "update_event_data")
    @patch.object(retention.supabase_storage, "delete_image")
    @patch.object(retention.db, "events_by_types")
    def test_cleanup_deletes_expired_image_types_and_preserves_other_images(
        self, events_by_types, delete_image, update_event_data
    ):
        events_by_types.side_effect = lambda types: [
            event for event in self.events if event["t"] in types
        ]
        now = datetime(2026, 12, 10, 20, 30, tzinfo=timezone.utc)

        result = retention.run_cleanup(now=now)

        self.assertEqual([item["id"] for item in result["bill_images_deleted"]], [2])
        self.assertEqual(
            [item["id"] for item in result["other_images_deleted"]], [1, 4, 5, 6]
        )
        self.assertEqual(
            [call.args[0] for call in delete_image.call_args_list],
            [
                "events/fuel.jpg",
                "events/location.jpg",
                "events/odometer.jpg",
                "events/generator.jpg",
                "events/odometer-stop.jpg",
            ],
        )
        self.assertEqual(
            [call.args[0] for call in update_event_data.call_args_list], [2, 1, 4, 5, 6]
        )
        for call in update_event_data.call_args_list:
            data = call.args[1]
            self.assertNotIn("image_path", data)
            self.assertIn("image_deleted_at", data)

    @patch.object(retention.db, "events_by_types")
    def test_fuel_image_is_retained_until_after_tenth_of_next_month(self, events_by_types):
        events_by_types.side_effect = lambda types: [
            event for event in self.events if event["t"] in types
        ]

        result = retention.run_cleanup(
            dry_run=True, now=datetime(2026, 12, 10, 18, 29, tzinfo=timezone.utc)
        )

        self.assertEqual(result["bill_images_deleted"], [])

    @patch.object(retention.db, "events_by_types")
    def test_fuel_image_is_due_after_tenth_passes(self, events_by_types):
        events_by_types.side_effect = lambda types: [
            event for event in self.events if event["t"] in types
        ]

        result = retention.run_cleanup(
            dry_run=True, now=datetime(2026, 12, 10, 20, 30, tzinfo=timezone.utc)
        )

        self.assertEqual([item["id"] for item in result["bill_images_deleted"]], [2])


if __name__ == "__main__":
    unittest.main()
