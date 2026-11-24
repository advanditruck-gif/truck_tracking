import unittest

from report import build_reports


class FoodExpenseReportTests(unittest.TestCase):
    def test_food_expense_is_added_and_deducted_from_balance(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "visit", "at": "2026-11-02T09:00:00", "d": {"amount_collected": 500}},
            {"id": 3, "run": "run-1", "t": "fuel", "at": "2026-11-02T10:00:00", "d": {"fuel_for": "diesel", "amount": 100}},
            {"id": 4, "run": "run-1", "t": "other_expense", "at": "2026-11-02T11:00:00", "d": {"amount": 25}},
        ]

        report = build_reports(events)[0]

        self.assertEqual(report["other_expense_amount"], 25)
        self.assertEqual(report["other_expense_count"], 1)
        self.assertEqual(report["food_expense_amount"], 350)
        self.assertEqual(report["balance_amount"], 50)

    def test_food_expense_is_charged_once_for_runs_on_the_same_date(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "visit", "at": "2026-11-02T09:00:00", "d": {"amount_collected": 500}},
            {"id": 3, "run": "run-2", "t": "start_km", "at": "2026-11-02T12:00:00", "d": {"km": 150}},
            {"id": 4, "run": "run-2", "t": "visit", "at": "2026-11-02T13:00:00", "d": {"amount_collected": 200}},
        ]

        reports = build_reports(events)

        self.assertEqual(len({report["date"] for report in reports}), 1)
        self.assertEqual(sum(report["food_expense_amount"] for report in reports), 350)
        self.assertEqual(sum(report["balance_amount"] for report in reports), 350)
        self.assertEqual(reports[0]["run"], "run-2")
        self.assertEqual(reports[0]["food_expense_amount"], 0)
        self.assertEqual(reports[1]["run"], "run-1")
        self.assertEqual(reports[1]["food_expense_amount"], 350)

    def test_excluded_run_is_omitted_from_reports(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-2", "t": "start_km", "at": "2026-11-02T12:00:00",
             "d": {"km": 150, "exclude_from_report": True}},
        ]

        reports = build_reports(events)

        self.assertEqual([report["run"] for report in reports], ["run-1"])


class GeneratorHoursReportTests(unittest.TestCase):
    def test_generator_start_end_and_usage_are_reported(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "generator_start", "at": "2026-11-02T08:01:00", "d": {"hours": 209}},
            {"id": 3, "run": "run-1", "t": "stop_km", "at": "2026-11-02T18:00:00", "d": {"km": 150}},
            {"id": 4, "run": "run-1", "t": "generator_stop", "at": "2026-11-02T18:01:00", "d": {"hours": 211.5}},
        ]

        report = build_reports(events)[0]

        self.assertEqual(report["generator_start_hours"], 209)
        self.assertEqual(report["generator_end_hours"], 211.5)
        self.assertEqual(report["generator_hours_used"], 2.5)

    def test_generator_photos_are_included_with_odometer_style_report_images(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "generator_start", "at": "2026-11-02T08:01:00",
             "d": {"hours": 209, "image_path": "events/generator-start.jpg"}},
            {"id": 3, "run": "run-1", "t": "generator_stop", "at": "2026-11-02T18:01:00",
             "d": {"hours": 211, "image_path": "events/generator-stop.jpg"}},
        ]

        report = build_reports(events)[0]

        self.assertEqual([image["type"] for image in report["images"]], ["generator_start", "generator_stop"])
        self.assertEqual([image["event_id"] for image in report["images"]], [2, 3])

    def test_missing_generator_reading_does_not_invent_usage(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "generator_start", "at": "2026-11-02T08:01:00", "d": {"hours": "invalid"}},
        ]

        report = build_reports(events)[0]

        self.assertIsNone(report["generator_start_hours"])
        self.assertIsNone(report["generator_end_hours"])
        self.assertIsNone(report["generator_hours_used"])

    def test_decreasing_meter_reading_does_not_report_negative_usage(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "generator_start", "at": "2026-11-02T08:01:00", "d": {"hours": 210}},
            {"id": 3, "run": "run-1", "t": "generator_stop", "at": "2026-11-02T18:01:00", "d": {"hours": 209}},
        ]

        report = build_reports(events)[0]

        self.assertEqual(report["generator_start_hours"], 210)
        self.assertEqual(report["generator_end_hours"], 209)
        self.assertIsNone(report["generator_hours_used"])


if __name__ == "__main__":
    unittest.main()
