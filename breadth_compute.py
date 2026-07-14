"""
Reads accumulated prices, computes today's breadth metrics + composite
score/regime, writes to breadth_daily, and fires Twilio alerts on regime
flips or fresh divergence flags. Run via .github/workflows/breadth_compute.yml,
chained after daily_ingest.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from src.alerts.twilio_notify import maybe_alert_divergence, maybe_alert_regime_flip
from src.db.models import get_connection, get_latest_breadth, init_db, upsert_breadth_daily
from src.engine.composite import classify_regime, composite_score
from src.engine.divergence import bearish_divergence, bullish_divergence
from src.engine.metrics import (
    advance_decline_line,
    index_close,
    new_highs_lows,
    pct_above_ma,
    up_down_volume_ratio,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BENCHMARK_TICKER = "SPY"


def main():
    init_db()
    with get_connection() as conn:
        prices = pd.read_sql("SELECT * FROM prices", conn, parse_dates=["date"])

    if prices.empty:
        logger.warning("No price data found; run daily_ingest first.")
        return

    universe = prices[prices["ticker"] != BENCHMARK_TICKER]

    metrics = {
        "pct_above_20ma": pct_above_ma(universe, 20),
        "pct_above_50ma": pct_above_ma(universe, 50),
        "pct_above_200ma": pct_above_ma(universe, 200),
        "ad_line": advance_decline_line(universe),
        "up_down_vol_ratio": up_down_volume_ratio(universe),
    }
    nh, nl = new_highs_lows(universe, window=252)
    metrics["new_highs"], metrics["new_lows"] = nh, nl

    score = composite_score(
        {k: v for k, v in metrics.items() if k in
         ("pct_above_50ma", "ad_line", "new_highs", "new_lows", "up_down_vol_ratio")}
    )
    regime = classify_regime(score)

    bench = index_close(prices, BENCHMARK_TICKER)
    bearish = bearish_divergence(bench, score.reindex(bench.index))
    bullish = bullish_divergence(bench, score.reindex(bench.index))

    latest_date = score.index.max()
    today = latest_date.date().isoformat()

    row = {
        "date": today,
        "pct_above_20ma": _safe(metrics["pct_above_20ma"], latest_date),
        "pct_above_50ma": _safe(metrics["pct_above_50ma"], latest_date),
        "pct_above_200ma": _safe(metrics["pct_above_200ma"], latest_date),
        "ad_line": _safe(metrics["ad_line"], latest_date),
        "new_highs": _safe(metrics["new_highs"], latest_date),
        "new_lows": _safe(metrics["new_lows"], latest_date),
        "up_down_vol_ratio": _safe(metrics["up_down_vol_ratio"], latest_date),
        "composite_score": _safe(score, latest_date),
        "regime": regime.get(latest_date, "unknown"),
        "bearish_divergence": bool(bearish.get(latest_date, False)),
        "bullish_divergence": bool(bullish.get(latest_date, False)),
    }
    upsert_breadth_daily(row)
    logger.info("Wrote breadth_daily row for %s: %s", today, row["regime"])

    # Alerts
    prior = get_latest_breadth(n_days=2)
    if len(prior) >= 2:
        prior_regime = prior.iloc[1]["regime"]
        maybe_alert_regime_flip(today, prior_regime, row["regime"])
    if row["bearish_divergence"]:
        maybe_alert_divergence(today, "bearish_divergence")
    if row["bullish_divergence"]:
        maybe_alert_divergence(today, "bullish_divergence")


def _safe(series: pd.Series, date) -> float | None:
    val = series.get(date)
    if val is None or pd.isna(val):
        return None
    return float(val)


if __name__ == "__main__":
    main()
