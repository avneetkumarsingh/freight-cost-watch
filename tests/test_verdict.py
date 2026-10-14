"""Adversarial checks on the hallucination guardrails, using the real notes."""
import unittest
from datetime import date
import pandas as pd

from costwatch.notes import load_notes
from costwatch.verdict import verify

NOTES = {n.note_id: n for n in load_notes()}


def ok(nid, route, week, own=0.30, peer=0.30):
    return verify(NOTES[nid], route, pd.Timestamp(week), own, peer)


class VerdictTests(unittest.TestCase):
    def test_note_parsing(self):
        self.assertEqual(NOTES["N001"].window, (date(2025, 2, 24), date(2025, 3, 8)))
        self.assertEqual(NOTES["N002"].window, (date(2025, 1, 20), date(2025, 1, 26)))
        self.assertEqual(NOTES["N003"].magnitude_pct, (5.0, 7.0))
        raising = sorted(k for k, n in NOTES.items() if n.effect == "raises")
        self.assertEqual(raising, ["N001", "N002", "N003"])

    def test_right_route_right_week_justifies(self):
        self.assertTrue(ok("N001", "Chennai-Bangalore", "2025-03-03").ok)
        self.assertTrue(ok("N002", "Ahmedabad-Mumbai", "2025-01-20").ok)

    def test_wrong_route_fails(self):
        self.assertEqual(ok("N001", "Mumbai-Pune", "2025-03-03").code, "scope")
        self.assertEqual(ok("N002", "Delhi-Jaipur", "2025-01-20").code, "scope")

    def test_wrong_window_fails(self):
        self.assertEqual(ok("N001", "Chennai-Bangalore", "2025-03-10").code, "window")  # flood over
        self.assertEqual(ok("N001", "Chennai-Bangalore", "2025-02-17").code, "window")  # before flood
        self.assertEqual(ok("N002", "Ahmedabad-Mumbai", "2025-01-27").code, "window")  # week after

    def test_notes_saying_no_cost_effect_never_justify(self):
        for nid in ["N004", "N005", "N006", "N007", "N008", "N009", "N010"]:
            for route in ["Mumbai-Delhi", "Delhi-Jaipur", "Chennai-Bangalore", "Kolkata-Bhubaneswar", "Mumbai-Pune"]:
                self.assertFalse(ok(nid, route, NOTES[nid].window[0], 0.05, 0.05).ok, (nid, route))

    def test_diesel_note_only_explains_small_rises_inside_horizon(self):
        self.assertTrue(ok("N003", "Mumbai-Pune", "2025-05-12", 0.06, 0.06).ok)
        self.assertEqual(ok("N003", "Mumbai-Pune", "2025-05-12", 0.30, 0.06).code, "magnitude")
        # all-routes cause also lifts peers, so a big gap vs peers is NOT explained by it
        self.assertEqual(ok("N003", "Mumbai-Pune", "2025-05-12", 0.06, 0.30).code, "magnitude")
        self.assertEqual(ok("N003", "Mumbai-Pune", "2025-04-28", 0.06, 0.06).code, "window")  # before
        self.assertEqual(ok("N003", "Mumbai-Pune", "2025-07-14", 0.06, 0.06).code, "window")  # absorbed


if __name__ == "__main__":
    unittest.main()
