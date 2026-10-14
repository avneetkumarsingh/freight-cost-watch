import unittest
import pandas as pd

from costwatch import metrics


def _df(rows):
    d = pd.DataFrame(rows, columns=["origin", "destination", "route_type", "quantity_tonnes",
                                    "distance_km", "freight_cost_inr", "shipment_date"])
    d["shipment_date"] = pd.to_datetime(d["shipment_date"])
    d["route"] = d.origin + "-" + d.destination
    d["week_of"] = d.shipment_date - pd.to_timedelta(d.shipment_date.dt.weekday, unit="D")
    d["tonne_km"] = d.quantity_tonnes * d.distance_km
    return d


class MetricsTests(unittest.TestCase):
    def test_load_shipments_assigns_mon_sun_weeks(self):
        import tempfile, os
        csv = ("shipment_id,origin,destination,route_type,material,quantity_tonnes,distance_km,"
               "freight_cost_inr,shipment_date,transporter\n"
               "1,A,B,Short,x,10,100,1000,2024-01-07,t\n"   # Sunday -> week of Jan 1
               "2,A,B,Short,x,10,100,1000,2024-01-08,t\n")  # Monday -> week of Jan 8
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.csv")
            open(p, "w").write(csv)
            df = metrics.load_shipments(p)
        self.assertEqual(df.week_of.dt.strftime("%Y-%m-%d").tolist(), ["2024-01-01", "2024-01-08"])

    def test_cost_per_tonne_km_is_total_cost_over_total_tonne_km(self):
        df = _df([["A", "B", "Short", 10, 100, 1000, "2024-01-01"],
                  ["A", "B", "Short", 20, 100, 4000, "2024-01-02"]])
        w = metrics.weekly_costs(df)
        self.assertAlmostEqual(w.cost_per_tonne_km[0], 5000 / (10 * 100 + 20 * 100))

    def test_own_history_is_strictly_prior_and_uses_available_weeks(self):
        rows = [["A", "B", "Short", 10, 100, c, d] for c, d in
                [(1000, "2024-01-01"), (2000, "2024-01-08"), (4000, "2024-01-15")]]
        w = metrics.add_own_history(metrics.weekly_costs(_df(rows)))
        self.assertTrue(pd.isna(w.own_baseline[0]))                 # no look-back for week 1
        self.assertAlmostEqual(w.own_baseline[1], 1.0)              # only week 1 (cpt 1.0)
        self.assertAlmostEqual(w.own_baseline[2], (1.0 + 2.0) / 2)  # weeks 1-2, never itself
        self.assertEqual(w.n_prior_weeks.tolist()[1:], [1, 2])

    def test_own_history_window_is_8_weeks(self):
        days = pd.date_range("2024-01-01", periods=10, freq="7D")
        rows = [["A", "B", "Short", 10, 100, 1000 * (i + 1), str(d.date())] for i, d in enumerate(days)]
        w = metrics.add_own_history(metrics.weekly_costs(_df(rows)))
        cpt = [(i + 1) / 1.0 for i in range(10)]
        self.assertAlmostEqual(w.own_baseline[9], sum(cpt[1:9]) / 8)  # weeks 2..9, drops week 1

    def test_peer_baseline_excludes_self_and_matches_route_type(self):
        rows = [["A", "B", "Short", 10, 100, 1000, "2024-01-01"],
                ["C", "D", "Short", 10, 100, 2000, "2024-01-01"],
                ["E", "F", "Short", 10, 100, 4000, "2024-01-01"],
                ["G", "H", "Long", 10, 100, 9000, "2024-01-01"]]
        w = metrics.add_peer_baseline(metrics.weekly_costs(_df(rows))).set_index("route")
        self.assertAlmostEqual(w.loc["A-B", "peer_baseline"], (2.0 + 4.0) / 2)
        self.assertTrue(pd.isna(w.loc["G-H", "peer_baseline"]))     # no Long peers -> undefined


if __name__ == "__main__":
    unittest.main()
