"""PPP: Pantau Pecah Paras Scanner - batch scan, writes data/<bourse>.json.

Run:  python scan.py            (all bourses)
      python scan.py US MY      (selected bourses)

Never writes synthetic data. If a bourse cannot be downloaded, the previous JSON
is kept (so the last good scan stays visible) and marked status="failed".
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).with_name("data")
CHUNK = 50                     # tickers per yf.download call
ATTEMPTS = 4                   # download rounds per bourse (retries only what is still missing)
BACKOFF = (5, 20, 60)          # seconds to wait between rounds (throttling)
HISTORY = "2y"                 # >= 252 trading bars, so High52W has a full window
MIN_BARS = 60
STALE_DAYS = 5                 # ticker whose last bar is this far behind its bourse -> failed
CLOSE_BUFFER = timedelta(minutes=20)

# bourse -> metadata. minDv/sliderMax/step are in millions of local currency.
# tz = bourse timezone, close = local regular-session close, premarket = US only.
MARKETS = {
    "US": {"name": "New York (NYSE/Nasdaq)", "city": "New York", "tz": "America/New_York", "close": "16:00", "premarket": True,
           "cur": "USD", "sym": "$", "minDv": 20, "sliderMax": 500, "step": 5, "stocks": {
        "NVDA": "Semiconductors", "AMD": "Semiconductors", "AVGO": "Semiconductors", "ARM": "Semiconductors",
        "QCOM": "Semiconductors", "SMCI": "Hardware", "AAPL": "Technology", "MSFT": "Technology",
        "GOOGL": "Communication", "META": "Communication", "NFLX": "Communication", "AMZN": "Consumer",
        "TSLA": "Consumer", "UBER": "Consumer", "PLTR": "Software", "PANW": "Cybersecurity",
        "CRWD": "Cybersecurity", "COIN": "Financials"}},
    "UK": {"name": "London (LSE)", "city": "London", "tz": "Europe/London", "close": "16:30",
           "cur": "GBP", "sym": "£", "minDv": 20, "sliderMax": 500, "step": 5, "stocks": {
        "SHEL.L": "Energy", "BP.L": "Energy", "AZN.L": "Healthcare", "GSK.L": "Healthcare", "HSBA.L": "Financials",
        "BARC.L": "Financials", "LLOY.L": "Financials", "LSEG.L": "Financials", "ULVR.L": "Consumer",
        "DGE.L": "Consumer", "RR.L": "Industrials", "BA.L": "Industrials", "REL.L": "Industrials",
        "RIO.L": "Materials", "GLEN.L": "Materials", "NG.L": "Utilities"}},
    "JP": {"name": "Tokyo (TSE)", "city": "Tokyo", "tz": "Asia/Tokyo", "close": "15:30",
           "cur": "JPY", "sym": "¥", "minDv": 2000, "sliderMax": 50000, "step": 500, "stocks": {
        "7203.T": "Autos", "6902.T": "Autos", "6758.T": "Technology", "6861.T": "Technology", "6501.T": "Technology",
        "8035.T": "Semiconductors", "9984.T": "Technology", "9983.T": "Consumer", "7974.T": "Consumer",
        "8306.T": "Financials", "8058.T": "Trading", "6098.T": "Services", "4063.T": "Materials",
        "9432.T": "Communication", "7011.T": "Industrials"}},
    "SG": {"name": "Singapore (SGX)", "city": "Singapore", "tz": "Asia/Singapore", "close": "17:00",
           "cur": "SGD", "sym": "S$", "minDv": 10, "sliderMax": 200, "step": 5, "stocks": {
        "D05.SI": "Financials", "O39.SI": "Financials", "U11.SI": "Financials", "S68.SI": "Financials",
        "Z74.SI": "Communication", "C6L.SI": "Transport", "BN4.SI": "Industrials", "S63.SI": "Industrials",
        "C38U.SI": "REITs", "A17U.SI": "REITs", "F34.SI": "Consumer", "C09.SI": "Real Estate",
        "U96.SI": "Utilities", "Y92.SI": "Consumer"}},
    "MY": {"name": "Kuala Lumpur (Bursa Malaysia)", "city": "Kuala Lumpur", "tz": "Asia/Kuala_Lumpur", "close": "17:00",
           "cur": "MYR", "sym": "RM", "minDv": 10, "sliderMax": 200, "step": 5, "stocks": {
        "1155.KL": "Financials", "1295.KL": "Financials", "1023.KL": "Financials", "5819.KL": "Financials",
        "5347.KL": "Utilities", "6033.KL": "Utilities", "5225.KL": "Healthcare", "5183.KL": "Materials",
        "4707.KL": "Consumer", "6888.KL": "Communication", "3182.KL": "Consumer", "1961.KL": "Plantation",
        "5285.KL": "Plantation", "0166.KL": "Technology", "5168.KL": "Healthcare"}},
    "ID": {"name": "Jakarta (IDX)", "city": "Jakarta", "tz": "Asia/Jakarta", "close": "16:00",
           "cur": "IDR", "sym": "Rp", "minDv": 50000, "sliderMax": 1000000, "step": 5000, "stocks": {
        "BBCA.JK": "Financials", "BBRI.JK": "Financials", "BMRI.JK": "Financials", "BBNI.JK": "Financials",
        "TLKM.JK": "Communication", "ASII.JK": "Autos", "UNVR.JK": "Consumer", "ICBP.JK": "Consumer",
        "GOTO.JK": "Technology", "AMMN.JK": "Materials", "MDKA.JK": "Materials", "ADRO.JK": "Energy",
        "BYAN.JK": "Energy", "CPIN.JK": "Consumer", "KLBF.JK": "Healthcare"}},
    "HK": {"name": "Hong Kong (HKEX)", "city": "Hong Kong", "tz": "Asia/Hong_Kong", "close": "16:00",
           "cur": "HKD", "sym": "HK$", "minDv": 100, "sliderMax": 2000, "step": 20, "stocks": {
        "0700.HK": "Technology", "9988.HK": "Technology", "3690.HK": "Technology", "1810.HK": "Technology",
        "9618.HK": "Technology", "1299.HK": "Financials", "0005.HK": "Financials", "2318.HK": "Financials",
        "0388.HK": "Financials", "0941.HK": "Communication", "1211.HK": "Autos", "0883.HK": "Energy"}},
    # FX trades 24h; the daily bar rolls at 17:00 New York. Yahoo gives no volume for spot FX.
    "FX": {"name": "Forex (spot, no volume)", "city": "New York", "tz": "America/New_York", "close": "17:00",
           "cur": "", "sym": "", "minDv": 0, "sliderMax": 0, "step": 1, "noVolume": True, "stocks": {
        "EURUSD=X": "Majors", "GBPUSD=X": "Majors", "USDJPY=X": "Majors", "AUDUSD=X": "Majors",
        "USDCAD=X": "Majors", "USDCHF=X": "Majors", "NZDUSD=X": "Majors", "EURJPY=X": "Crosses",
        "GBPJPY=X": "Crosses", "EURGBP=X": "Crosses", "USDSGD=X": "Asia", "USDMYR=X": "Asia",
        "USDIDR=X": "Asia", "USDHKD=X": "Asia", "USDCNY=X": "Asia"}},
}


def log(msg):
    print(msg, flush=True)


def _num(x, nd=4):
    """Convert to JSON-safe float (NaN/inf -> None)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else round(x, nd)


# ---------------------------------------------------------------- datetime checklist
def normalise(df: pd.DataFrame, tz: str, daily: bool = False) -> pd.DataFrame:
    """Datetime checklist, applied to EVERY frame we load from yfinance.

    1. flatten the yfinance MultiIndex:  df.columns.get_level_values(0)
    2. tz_localize('UTC') if the index is naive
    3. tz_convert to the bourse timezone (all session logic uses this local time)
    Excel/CSV export must go through strip_tz() first.

    Exception, daily=True: yf.download returns daily bars as tz-naive LOCAL calendar dates
    (ignore_tz defaults to True for 1d), i.e. a date label, not an instant. Steps 2-3 would
    read "2026-10-27" as 00:00 UTC and move it to 2026-10-26 20:00 in New York, a day early.
    So for daily bars the bourse tz is attached to the date label (local midnight) instead.
    """
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    idx = pd.DatetimeIndex(df.index)
    if daily:
        if idx.tz is not None:
            idx = idx.tz_localize(None)        # keep the wall-clock date, drop the source tz
        idx = idx.normalize().tz_localize(tz, ambiguous=True, nonexistent="shift_forward")
    else:
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        idx = idx.tz_convert(tz)
    df.index = idx
    return df


def strip_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Excel cannot store tz-aware datetimes: drop tz (keeping local wall time) before any export."""
    df = df.copy()
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def split_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """One ticker's OHLCV out of a yf.download(group_by='ticker') result."""
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker not in raw.columns.get_level_values(0):
            raise KeyError(ticker)
        return raw[ticker]
    return raw  # single-ticker download that came back flat


# ---------------------------------------------------------------- download with retry
def is_throttle(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return any(k in s for k in ("ratelimit", "rate limit", "too many requests", "429"))


def download_chunked(tickers, label, **kw):
    """yf.download in chunks of ~50 with threads=True. Retries only the tickers still
    missing, with backoff between rounds. Returns ({ticker: raw_frame}, {ticker: reason})."""
    got, reasons = {}, {}
    pending = list(tickers)
    for attempt in range(1, ATTEMPTS + 1):
        throttled = False
        for i in range(0, len(pending), CHUNK):
            chunk = pending[i:i + CHUNK]
            try:
                raw = yf.download(chunk, group_by="ticker", auto_adjust=False, threads=True, progress=False, **kw)
            except Exception as e:  # network error / throttling: whole chunk stays pending
                throttled = throttled or is_throttle(e)
                for t in chunk:
                    reasons[t] = f"{type(e).__name__}: {e}"[:160]
                log(f"[{label}] attempt {attempt}: chunk of {len(chunk)} failed: {e}")
                continue
            for t in chunk:
                try:
                    df = split_frame(raw, t).dropna(how="all")
                    if df.empty:
                        raise ValueError("no data returned")
                    got[t] = df
                    reasons.pop(t, None)
                except Exception as e:
                    reasons[t] = f"{type(e).__name__}: {e}"[:160]
        pending = [t for t in tickers if t not in got]
        if not pending:
            break
        if attempt < ATTEMPTS:
            wait = BACKOFF[min(attempt - 1, len(BACKOFF) - 1)] * (2 if throttled else 1)
            log(f"[{label}] {len(pending)} ticker(s) missing, retry {attempt + 1}/{ATTEMPTS} in {wait}s")
            time.sleep(wait)
    return got, {t: reasons.get(t, "no data returned") for t in pending}


# ---------------------------------------------------------------- indicators
def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["Close", "High", "Low"]).copy()
    df["Volume"] = df["Volume"].fillna(0)
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    df["EMA20"] = c.ewm(span=20, adjust=False).mean()
    df["SMA50"] = c.rolling(50).mean()
    df["VolSMA20"] = v.rolling(20).mean()
    df["DollarVol20"] = (c * v).rolling(20).mean()
    # NO LOOK-AHEAD: .shift(1) moves each rolling max one bar forward, so row t holds the
    # max High of bars t-20..t-1 (resp. t-252..t-1) and never includes bar t itself.
    # The breakout test (Close > High20Prior, Close >= 0.95*High52W) compares today's bar
    # against these shifted values. Proven in tests/test_scan.py.
    df["High20Prior"] = h.rolling(20).max().shift(1)
    # 252 TRADING BARS (about one year of sessions), not 365 calendar days. HISTORY is 2y so
    # the window is full; min_periods=60 only matters for freshly listed stocks.
    df["High52W"] = h.rolling(252, min_periods=60).max().shift(1)
    df["Range10"] = 100 * (h.rolling(10).max() - l.rolling(10).min()) / c
    df["Range10Low60"] = df["Range10"].rolling(60, min_periods=20).min()
    df["ROC20"] = (c / c.shift(20) - 1) * 100
    return df


def drop_open_session(df: pd.DataFrame, meta: dict, now_utc: datetime) -> pd.DataFrame:
    """Drop today's bar if the bourse is still open (volume/close of a partial bar mislead).
    Session logic runs in the bourse's local time. FX is 24h, so its latest bar is kept."""
    if meta.get("noVolume") or df.empty:
        return df
    tz = ZoneInfo(meta["tz"])
    now = now_utc.astimezone(tz)
    hh, mm = map(int, meta["close"].split(":"))
    close_dt = datetime(now.year, now.month, now.day, hh, mm, tzinfo=tz) + CLOSE_BUFFER
    if df.index[-1].date() == now.date() and now < close_dt:
        return df.iloc[:-1]
    return df


KEYS = ["Open", "High", "Low", "Close", "Volume", "EMA20", "SMA50", "VolSMA20",
        "DollarVol20", "High20Prior", "High52W", "Range10", "Range10Low60", "ROC20"]


def build_stock(ticker, sector, df, meta):
    no_vol = meta.get("noVolume", False)
    last, prev = df.iloc[-1], df.iloc[-2]
    ind = {k: _num(last[k]) for k in KEYS}
    ind["VolRatio"] = _num(last["Volume"] / last["VolSMA20"], 3) if last["VolSMA20"] else None
    if no_vol:  # FX has no real volume: never fake it
        for k in ("Volume", "VolSMA20", "DollarVol20", "VolRatio"):
            ind[k] = None
    # Open Gap % = today's regular-session OPEN vs previous CLOSE. It is NOT pre-market.
    ind["OpenGapPct"] = _num((last["Open"] / prev["Close"] - 1) * 100, 3)
    ind["ChangePct"] = _num((last["Close"] / prev["Close"] - 1) * 100, 3)
    ind["PreMktPct"] = None
    tail = df.tail(252)
    times = [d.strftime("%Y-%m-%d") for d in tail.index]   # index is already bourse-local
    nd = 5 if no_vol else 2
    candles = [{"time": ts, "open": _num(r.Open, nd), "high": _num(r.High, nd), "low": _num(r.Low, nd),
                "close": _num(r.Close, nd), "volume": None if no_vol else _num(r.Volume, 0)}
               for ts, r in zip(times, tail.itertuples())]

    def line(col):
        return [{"time": ts, "value": _num(x, nd)} for ts, x in zip(times, tail[col]) if _num(x) is not None]

    return {"ticker": ticker, "sector": sector, "indicators": ind, "candles": candles,
            "ema20": line("EMA20"), "sma50": line("SMA50"), "pivot20": line("High20Prior")}


# ---------------------------------------------------------------- US pre-market
def premarket(frames, tz):
    """Latest pre-market price (04:00-09:30 New York, yfinance prepost=True) vs the previous
    regular close. Returns {ticker: (pct, 'ISO local time')}; tickers without bars are omitted."""
    tickers = list(frames)
    raw, _ = download_chunked(tickers, "US premarket", period="5d", interval="5m", prepost=True)
    out = {}
    for t, intra in raw.items():
        try:
            intra = normalise(intra, tz).dropna(subset=["Close"])
            pre = intra.between_time("04:00", "09:30", inclusive="left")
            if pre.empty:
                continue
            day = pre.index[-1].normalize()
            closes = frames[t]["Close"]
            before = closes[closes.index.normalize() < day]
            if before.empty:
                continue
            out[t] = (_num((pre["Close"].iloc[-1] / before.iloc[-1] - 1) * 100, 3), pre.index[-1].isoformat(timespec="minutes"))
        except Exception as e:
            log(f"[US premarket] {t}: {e}")
    return out


# ---------------------------------------------------------------- one bourse
def scan_bourse(code, now_utc):
    meta = MARKETS[code]
    tickers = list(meta["stocks"])
    got, reasons = download_chunked(tickers, code, period=HISTORY, interval="1d")
    frames, failed = {}, dict(reasons)
    for t, raw in got.items():
        try:
            df = compute(drop_open_session(normalise(raw, meta["tz"], daily=True), meta, now_utc))
            if len(df) < MIN_BARS:
                raise ValueError(f"only {len(df)} bars")
            frames[t] = df
        except Exception as e:
            failed[t] = f"{type(e).__name__}: {e}"[:160]
    if frames:  # drop halted / delisted names whose last bar is far behind the bourse
        newest = max(df.index[-1] for df in frames.values())
        for t in [t for t, df in frames.items() if newest - df.index[-1] > timedelta(days=STALE_DAYS)]:
            failed[t] = f"stale: last bar {frames.pop(t).index[-1].date()}"
    if not frames:
        raise RuntimeError(f"no usable data for any of {len(tickers)} tickers")

    stocks = [build_stock(t, meta["stocks"][t], frames[t], meta) for t in tickers if t in frames]
    pre_status = None
    if meta.get("premarket"):
        try:
            pre = premarket(frames, meta["tz"])
            for s in stocks:
                if s["ticker"] in pre:
                    s["indicators"]["PreMktPct"], s["indicators"]["PreMktTime"] = pre[s["ticker"]]
            pre_status = "ok" if pre else "unavailable"
        except Exception as e:
            log(f"[{code}] premarket failed: {e}")
            pre_status = "unavailable"

    last_session = max(df.index[-1] for df in frames.values()).strftime("%Y-%m-%d")
    out_meta = {k: v for k, v in meta.items() if k != "stocks"}
    now_iso = now_utc.isoformat(timespec="seconds")
    return {"bourse": code, "status": "ok", "generated_at": now_iso, "last_attempt_at": now_iso,
            "data_source": f"Yahoo Finance via yfinance {yf.__version__}", "last_session": last_session,
            "premkt_status": pre_status, "meta": out_meta, "count": len(stocks),
            "failed": sorted(failed), "failed_reasons": failed, "stocks": stocks}


def write_json(path: Path, obj):
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def run(codes):
    now_utc = datetime.now(timezone.utc)
    bad = []
    for code in codes:
        path = DATA_DIR / f"{code.lower()}.json"
        log(f"=== {code} ===")
        try:
            result = scan_bourse(code, now_utc)
            log(f"[{code}] ok: {result['count']} stocks, {len(result['failed'])} failed")
        except Exception as e:
            log(f"[{code}] FAILED: {e}")
            bad.append(code)
            try:  # keep the last good scan, only flag the failure
                result = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                meta = {k: v for k, v in MARKETS[code].items() if k != "stocks"}
                result = {"bourse": code, "generated_at": None, "meta": meta, "count": 0,
                          "failed": [], "stocks": []}
            result.update({"status": "failed", "error": str(e)[:300], "last_attempt_at": now_utc.isoformat(timespec="seconds")})
        write_json(path, result)
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bourses", nargs="*", help=f"any of {', '.join(MARKETS)} (default: all)")
    codes = [c.upper() for c in ap.parse_args(argv).bourses] or list(MARKETS)
    unknown = [c for c in codes if c not in MARKETS]
    if unknown:
        ap.error(f"unknown bourse(s): {', '.join(unknown)}")
    bad = run(codes)
    if bad:
        log(f"FAILED bourses: {', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
