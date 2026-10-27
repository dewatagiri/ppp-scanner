"""Unit tests for the accuracy rules in scan.py. Synthetic frames are used ONLY here, never in output."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan  # noqa: E402


def frame(n, high=None, tz=None):
    idx = pd.bdate_range("2023-01-02", periods=n, tz=tz)
    base = np.linspace(100, 120, n)
    df = pd.DataFrame({"Open": base, "High": base + 1, "Low": base - 1, "Close": base,
                       "Volume": 1_000_000.0}, index=idx)
    if high:
        for i, v in high.items():
            df.iloc[i, df.columns.get_loc("High")] = v
    return df


class LookAhead(unittest.TestCase):
    def test_high20_excludes_today(self):
        df = frame(100, high={99: 500.0})            # spike on the LAST bar only
        out = scan.compute(df)
        self.assertLess(out["High20Prior"].iloc[-1], 200)   # today's spike is not in its own pivot
        self.assertEqual(out["High20Prior"].iloc[-1], df["High"].iloc[-21:-1].max())
        self.assertGreater(out["Close"].iloc[-1] * 0 + 500, out["High20Prior"].iloc[-1])

    def test_breakout_compares_today_with_prior_high(self):
        df = frame(100)
        df.iloc[-1, df.columns.get_loc("Close")] = 300.0     # close blasts through the prior 20D high
        out = scan.compute(df)
        last = out.iloc[-1]
        self.assertTrue(last["Close"] > last["High20Prior"])

    def test_high52w_is_252_bars_not_365_days(self):
        # a high 252 bars back is still inside the window, 253 bars back has dropped out
        inside = scan.compute(frame(400, high={400 - 1 - 252: 999.0}))
        outside = scan.compute(frame(400, high={400 - 1 - 253: 999.0}))
        self.assertEqual(inside["High52W"].iloc[-1], 999.0)
        self.assertLess(outside["High52W"].iloc[-1], 999.0)

    def test_high52w_excludes_today(self):
        out = scan.compute(frame(400, high={399: 999.0}))
        self.assertLess(out["High52W"].iloc[-1], 999.0)


class Datetimes(unittest.TestCase):
    def test_naive_is_utc_then_bourse_tz(self):
        df = frame(5)
        df.index = pd.date_range("2024-01-02 07:00", periods=5, freq="D")   # naive, 07:00 UTC
        out = scan.normalise(df, "Asia/Kuala_Lumpur")
        self.assertEqual(str(out.index.tz), "Asia/Kuala_Lumpur")
        self.assertEqual(out.index[0].hour, 15)                              # 07:00 UTC = 15:00 MYT

    def test_daily_naive_date_is_not_shifted_a_day(self):
        # yfinance daily bars are naive local dates. UTC-then-convert would give 2026-10-26 in New York.
        df = frame(5)
        df.index = pd.DatetimeIndex(["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"])
        for tz in ("America/New_York", "Asia/Tokyo", "Europe/London"):
            out = scan.normalise(df, tz, daily=True)
            self.assertEqual(out.index[-1].strftime("%Y-%m-%d"), "2026-10-27", tz)
            self.assertEqual(str(out.index.tz), tz)
        aware = df.copy()
        aware.index = aware.index.tz_localize("Europe/London")   # FX pairs come back in London time
        self.assertEqual(scan.normalise(aware, "America/New_York", daily=True).index[-1].strftime("%Y-%m-%d"), "2026-10-27")

    def test_multiindex_flattened(self):
        df = frame(5)
        df.columns = pd.MultiIndex.from_product([df.columns, ["AAPL"]])
        self.assertFalse(isinstance(scan.normalise(df, "America/New_York").columns, pd.MultiIndex))

    def test_strip_tz_for_excel(self):
        out = scan.strip_tz(scan.normalise(frame(5, tz="UTC"), "Asia/Tokyo"))
        self.assertIsNone(out.index.tz)


class Sessions(unittest.TestCase):
    meta = {"tz": "Asia/Kuala_Lumpur", "close": "17:00"}

    def test_open_session_bar_dropped(self):
        df = scan.normalise(frame(10, tz="Asia/Kuala_Lumpur"), self.meta["tz"])
        day = df.index[-1]
        during = datetime(day.year, day.month, day.day, 4, 0, tzinfo=timezone.utc)   # 12:00 MYT
        after = datetime(day.year, day.month, day.day, 10, 0, tzinfo=timezone.utc)   # 18:00 MYT
        self.assertEqual(len(scan.drop_open_session(df, self.meta, during)), 9)
        self.assertEqual(len(scan.drop_open_session(df, self.meta, after)), 10)

    def test_fx_keeps_latest_bar(self):
        df = scan.normalise(frame(10, tz="America/New_York"), "America/New_York")
        day = df.index[-1]
        now = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
        meta = {"tz": "America/New_York", "close": "17:00", "noVolume": True}
        self.assertEqual(len(scan.drop_open_session(df, meta, now)), 10)


class Fields(unittest.TestCase):
    def test_open_gap_named_and_fx_has_no_volume(self):
        df = scan.compute(frame(100))
        stock = scan.build_stock("X", "S", df, {"noVolume": False})
        fx = scan.build_stock("EURUSD=X", "Majors", df, {"noVolume": True})
        self.assertIn("OpenGapPct", stock["indicators"])
        self.assertNotIn("GapPct", stock["indicators"])
        self.assertIsNone(fx["indicators"]["VolRatio"])
        self.assertIsNone(fx["indicators"]["DollarVol20"])


if __name__ == "__main__":
    unittest.main()
