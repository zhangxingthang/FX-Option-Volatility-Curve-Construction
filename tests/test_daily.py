import csv
import tempfile
import unittest
from pathlib import Path

from track_daily_smiles import collect_daily, save_history


class TestDailyTracking(unittest.TestCase):
    def test_tracks_distinct_days_and_replaces_earlier_same_day_quote(self):
        with tempfile.TemporaryDirectory() as folder:
            quote_folder = Path(folder) / "data"
            quote_folder.mkdir()
            for filename, day, hour, atm in (
                ("first.csv", "2025-04-28", "05", 10.0),
                ("second.csv", "2025-04-28", "17", 11.0),
                ("third.csv", "2025-04-29", "05", 12.0),
            ):
                with (quote_folder / filename).open("w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(["Timestamp", "Currency", "Record", "Bid", "Ask",
                                     "CurrencyCode", "PricingConvention"])
                    for record, bid, ask, code, convention in (
                        ("IEURAUD_1M", atm - 0.2, atm + 0.2, "", ""),
                        ("IEURAUDRR25_1M", 0.7, 0.9, "1", "1"),
                        ("IEURAUDBF25_1M", 0.1, 0.3, "", ""),
                    ):
                        writer.writerow([f"{day}T{hour}:30:34+01:00", "EUR/AUD", record,
                                         bid, ask, code, convention])
            history = collect_daily(quote_folder)
            self.assertEqual([item["date"] for item in history], ["2025-04-28", "2025-04-29"])
            self.assertEqual(history[0]["file"], "second.csv")
            self.assertEqual(history[0]["atm_rr_bf_vol_points"]["atm"], 11.0)
            self.assertEqual(history[1]["atm_rr_bf_vol_points"]["atm"], 12.0)
            save_history(history, Path(folder) / "results")
            self.assertTrue((Path(folder) / "results" / "euraud_daily_volatility.png").exists())


if __name__ == "__main__":
    unittest.main()
