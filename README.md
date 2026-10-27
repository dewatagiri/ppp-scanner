# PPP: Pantau Pecah Paras Scanner

A free end-of-day breakout screener for **New York, London, Tokyo, Singapore, Kuala Lumpur, Jakarta, Hong Kong** and **Forex**, published as a static GitHub Pages site.

**Live:** https://dewatagiri.github.io/ppp-scanner/

## What it does

A GitHub Actions job runs `scan.py` after each market closes. It downloads daily bars from Yahoo Finance (via `yfinance`), computes the indicators and commits the results to `data/<bourse>.json`. The page (`index.html`) loads that JSON with `fetch()` and applies the scan filters in your browser. There is no backend and no database.

Scans: **PPP 20-Day Breakout**, **EMA 20 Pullback**, **Tight Range at 52-Week High**, **Open Gappers**, **Sector Leaders (ROC-20)**. English and Bahasa Melayu. Installable on your phone ("Add to Home Screen").

## Column definitions

| Column | Meaning |
|---|---|
| Close | Last regular-session close, unadjusted. |
| Chg % | Close vs previous close. |
| 20D Pivot | Highest High of the 20 bars **before** today (shifted one bar, no look-ahead). |
| Vol/Avg | Today's volume ÷ 20-day average volume. FX shows `Vol: n/a`. |
| Dollar Vol (M) | 20-day average of Close × Volume, in millions of local currency. FX shows `Vol: n/a`. |
| EMA 20 / SMA 50 | 20-day exponential / 50-day simple moving average of Close. |
| 10D Range % | (10-day high − 10-day low) ÷ close × 100. |
| ROC-20 % | Close vs close 20 sessions ago. |
| **Open Gap %** | **Today's regular-session open vs the previous close.** This is the gap at the opening bell. It is **not** pre-market. |
| Pre-mkt % | **US only.** Latest pre-market price (04:00–09:30 New York, `prepost=True`) vs the previous close. Shows `n/a` for other bourses, and `–` if Yahoo has no pre-market bars for that ticker. |
| Tests | Conditions actually tested ÷ conditions in the scan. FX skips the volume conditions, so it shows e.g. `1/3`. |

52-week high = highest High of the previous **252 trading bars** (not 365 calendar days), excluding today.

## Forex

Yahoo has no volume for spot FX. FX keeps all non-volume conditions, skips the volume ones, shows `Vol: n/a`, and lives in its own section of the bourse list with a banner stating how many conditions were tested. Do not compare FX results with stock results.

## Scan schedule (Monday–Friday, UTC)

| UTC | Bourse |
|---|---|
| 07:15 | Tokyo |
| 08:45 | Hong Kong |
| 09:45 | Singapore, Kuala Lumpur, Jakarta |
| 12:45 | New York (pre-market run, fills Pre-mkt %) |
| 17:15 | London |
| 21:30 | New York (after close) |
| 22:30 | Forex |

GitHub may start scheduled jobs several minutes late. You can also run it by hand: **Actions → scan → Run workflow**.

## Data limits

- Source is Yahoo Finance via `yfinance`. Data may be delayed, incomplete or wrong, and Yahoo can throttle or change its service without notice.
- Daily bars only. The bar of a session still in progress is dropped, so results are always for the last completed session (FX uses its latest bar).
- Downloads run in batches of about 50 tickers with retry and backoff. Tickers that still fail are listed in the JSON (`failed`) and the count is shown above each table.
- If a bourse cannot be downloaded at all, the page says `Data unavailable for <bourse> — last good scan: <time>`. The site never shows simulated or placeholder data.
- The ticker list is a fixed shortlist per bourse (see `MARKETS` in `scan.py`), not the whole market.
- Pre-market data on Yahoo is thin for some tickers.

## Run it yourself

```
pip install -r requirements.txt
python -m unittest discover -s tests   # look-ahead, 252-bar window, datetime checks
python scan.py            # all bourses, or e.g. python scan.py US MY
python -m http.server     # open http://localhost:8000
```

The old local FastAPI server (`app.py`) was dropped: the page is now fully static, so `python -m http.server` replaces it.

## Credits

Charts: [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) 4.2.0 (Apache-2.0, see `assets/LICENSE-lightweight-charts.txt`), bundled in `assets/`. This site is powered by TradingView Lightweight Charts™, https://www.tradingview.com/

## Disclaimer

For education and research only. Not investment advice, and not a recommendation to buy or sell any security. Data comes from Yahoo Finance via yfinance and may be delayed, incomplete or wrong. Check with your broker before trading. Trading involves risk, including loss of capital. Views are my own and do not represent any organisation I am or have been affiliated with.

## Privacy

This site collects no personal data. Settings are stored only in your own browser. Consistent with Malaysia's Personal Data Protection Act 2010 (PDPA) and Indonesia's Personal Data Protection Law (UU PDP No. 27/2022).

© 2026 Azman Taufik
