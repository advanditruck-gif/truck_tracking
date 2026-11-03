import unittest

from report import build_reports


class OtherExpenseReportTests(unittest.TestCase):
    def test_expenses_are_separate_and_do_not_reduce_balance(self):
        events = [
            {"id": 1, "run": "run-1", "t": "start_km", "at": "2026-11-02T08:00:00", "d": {"km": 100}},
            {"id": 2, "run": "run-1", "t": "visit", "at": "2026-11-02T09:00:00", "d": {"amount_collected": 500}},
            {"id": 3, "run": "run-1", "t": "fuel", "at": "2026-11-02T10:00:00", "d": {"fuel_for": "diesel", "amount": 100}},
            {"id": 4, "run": "run-1", "t": "other_expense", "at": "2026-11-02T11:00:00", "d": {"amount": 25}},
        ]

        report = build_reports(events)[0]

        self.assertEqual(report["other_expense_amount"], 25)
        self.assertEqual(report["other_expense_count"], 1)
        self.assertEqual(report["balance_amount"], 400)


if __name__ == "__main__":
    unittest.main()
