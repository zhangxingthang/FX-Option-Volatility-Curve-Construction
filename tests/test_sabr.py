import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sabr_euraud import fit_smile, parse_quotes, sabr_lognormal_vol


class TestSabr(unittest.TestCase):
    def test_recovers_market_anchor_volatilities(self):
        strikes, targets, parameters, errors = fit_smile({
            "atm": 10.525, "rr": 0.875, "bf": 0.2
        })
        np.testing.assert_allclose(sabr_lognormal_vol(1, strikes, 30 / 365, *parameters), targets,
                                   atol=0.000001)
        self.assertLess(max(abs(errors)), 0.000001)
        self.assertLess(strikes[0], 1)
        self.assertGreater(strikes[-1], 1)

    def test_selects_synchronized_quotes_not_later_stale_mix(self):
        header = ["Timestamp", "Currency", "Description", "Record", "Ask", "AskText",
                  "Bid", "BidText", "CurrencyCode", "PricingConvention"]
        base = ["2025-04-28T05:30:34.800+01:00", "EUR/AUD", ""]
        rows = [
            base + ["IEURAUD_1M", "10.925", "", "10.125", "", "", ""],
            ["2025-04-28T05:30:34.801+01:00", "EUR/AUD", "", "IEURAUDRR25_1M",
             "1.175", "", "0.575", "", "1", "1"],
            ["2025-04-28T05:30:34.801+01:00", "EUR/AUD", "", "IEURAUDBF25_1M",
             "0.8", "", "-0.4", "", "", ""],
            ["2025-04-28T17:11:51.355+01:00", "EUR/AUD", "", "IEURAUD_1M",
             "9", "", "8", "", "", ""],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.csv"
            with path.open("w", newline="") as destination:
                writer = csv.writer(destination)
                writer.writerow(header)
                writer.writerows(rows)
            quotes = parse_quotes(path)
        self.assertEqual(quotes["atm"], 10.525)
        self.assertEqual(quotes["rr"], 0.875)
        self.assertEqual(quotes["bf"], 0.2)


if __name__ == "__main__":
    unittest.main()
