# Market Breadth Detector

Internal-market-breadth pipeline for pre-trade regime filtering on swing and
day trades. Computes advance-decline, new highs/lows, %-above-moving-average,
up/down volume, and a composite momentum gauge with regime classification
and price/breadth divergence detection.

Structured the same way as the Central Ohio Kayak Dashboard: scheduled
ingestion (GitHub Actions) -> compute -> persist (SQLite) -> Streamlit
dashboard + Twilio alerts.

## Status

Prototyping on `yfinance` for a ~30-ticker starter universe. Not yet
validated for live trading decisions -- see `Backtesting caveats` below
before trusting any regime signal with real capital.

## Quickstart

```bash
pip install -r requirements.txt

# 1. End-to-end example on a small universe (fetch, compute, backtest)
python -m examples.run_backtest_example

# 2. Run tests
pytest

# 3. Local dashboard (after running scripts/breadth_compute.py at least once)
streamlit run dashboard/streamlit_app.py
```

## Architecture

```
src/ingestion/   -- data pulls (yfinance now; Polygon/Tiingo later at scale)
src/engine/      -- breadth metrics, composite score, divergence detection
src/backtest/    -- signal generators + walk-forward evaluation harness
src/db/          -- SQLite schema + access layer
src/alerts/      -- Twilio SMS notifications
scripts/         -- entry points run by GitHub Actions
dashboard/       -- Streamlit app
examples/        -- standalone runnable walkthrough
tests/           -- lookahead-safety and metric sanity checks
```

## Data source

Starting on `yfinance` (free) for prototyping. Known limitations:
batches rather than true bulk pulls, occasional missing rows, rate limits
at full S&P 500 scale. Swap `src/ingestion/yfinance_client.py` for a
Polygon.io or Tiingo bulk-endpoint client once the engine/backtest logic
is validated and you need daily production reliability at ~500 tickers.

**Survivorship bias**: `src/ingestion/universe.py` pulls the *current*
S&P 500 list. Backtesting with today's constituents against years of
history excludes stocks that were removed (usually because they were
struggling), which inflates historical breadth readings. Documented in
the module; a static frozen `data/universe.csv` is provided for
reproducible runs, but it is not point-in-time-accurate historically.

## Backtesting caveats

- **Two separate questions, don't conflate them**: does a breadth regime
  *filter* improve a price signal's odds (`backtest_filter`), vs. does a
  divergence flag work as a standalone *timing* signal
  (`backtest_divergence_signal`).
- **Train/holdout discipline**: tune composite weights and regime
  thresholds only on the `train` window (`run_walk_forward`); the
  `holdout` window is reported once, not iterated on.
- **Sample size**: every backtest summary reports `n_trades` and a
  `low_sample_warning` flag below 30 observations. A Sharpe improvement
  on 15 trades is noise, not a result -- always check this before trusting
  a headline number.
- **Costs**: `apply_transaction_costs` subtracts a basis-point estimate
  from every trade return by default. Don't compare a filtered strategy
  (fewer, more selective trades) against an unfiltered one without costs
  applied to both -- it makes the filter look better than it is.
- **Lookahead**: all rolling calculations in `src/engine/metrics.py` and
  `src/backtest/runner.py` use only trailing data. `tests/test_engine.py`
  includes a regression test (truncate-and-recompute) to catch
  accidental leakage if you modify these.

## Infrastructure

- `.github/workflows/daily_ingest.yml` -- pulls prior day's OHLCV,
  commits updated SQLite DB. Runs ~4:30pm ET on weekdays.
- `.github/workflows/breadth_compute.yml` -- chained after ingestion,
  computes the day's metrics/regime, fires Twilio alerts on regime
  flips or new divergence flags (deduped via `alerts_sent` table).

Kept as two separate workflows so ingestion failures and compute failures
are easy to isolate -- same principle as the kayak dashboard's separation
of gauge-check from alert logic.

### Required GitHub Actions secrets (for Twilio alerts)

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`,
`ALERT_TO_NUMBER`

### Scaling beyond SQLite

SQLite is fine for solo/local use and is what the Actions workflows commit
back to the repo. If you hit file-locking issues running the dashboard
and the Action concurrently, or want to scale past a ~30-500 ticker
universe with frequent writes, move to Postgres (Supabase free tier is
low-friction) -- the schema in `src/db/schema.sql` is Postgres-compatible
as written.

## Next steps

- Validate the composite weights/thresholds via `run_walk_forward` on a
  longer history before trusting `regime` for live filtering.
- Swap yfinance for a bulk vendor once ready to run the full S&P 500
  universe daily.
- Add sector-level breadth (same engine functions, scoped to a sector
  ticker subset) per the original article's sector-rotation discussion.
