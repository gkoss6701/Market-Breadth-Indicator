"""
Sanity tests focused on the things most likely to silently break a breadth
pipeline: lookahead leakage and basic metric correctness. Not exhaustive --
extend as you add metrics.
"""
import pandas as pd

from src.backtest.runner import forward_returns
from src.engine.composite import classify_regime, composite_score
from src.engine.metrics import advance_decline_line, pct_above_ma


def _toy_universe():
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    rows = []
    # Ticker A: steadily rising, stays above its MA
    for i, d in enumerate(dates):
        rows.append({"date": d, "ticker": "A", "close": 100 + i, "volume": 1000})
    # Ticker B: steadily falling, stays below its MA
    for i, d in enumerate(dates):
        rows.append({"date": d, "ticker": "B", "close": 100 - i, "volume": 1000})
    return pd.DataFrame(rows)


def test_pct_above_ma_bounds():
    df = _toy_universe()
    result = pct_above_ma(df, window=3)
    assert (result.dropna() >= 0).all()
    assert (result.dropna() <= 100).all()


def test_advance_decline_line_no_lookahead():
    df = _toy_universe()
    ad_line = advance_decline_line(df)
    # Truncate the input and recompute -- earlier values must be identical,
    # since they shouldn't depend on data that comes after them.
    cutoff = df["date"].unique()[5]
    truncated = df[df["date"] <= cutoff]
    ad_line_truncated = advance_decline_line(truncated)
    pd.testing.assert_series_equal(
        ad_line.loc[:cutoff], ad_line_truncated, check_names=False
    )


def test_forward_returns_shifts_correctly():
    close = pd.Series([100, 110, 121], index=pd.date_range("2024-01-01", periods=3, freq="B"))
    fwd = forward_returns(close, holding_days=1)
    assert abs(fwd.iloc[0] - 0.10) < 1e-9
    assert pd.isna(fwd.iloc[-1])  # no future data for the last observation


def test_composite_score_and_regime_run():
    df = _toy_universe()
    metrics = {"pct_above_50ma": pct_above_ma(df, window=3)}
    score = composite_score(metrics, weights={"pct_above_50ma": 1.0}, window=3)
    regime = classify_regime(score)
    assert set(regime.dropna().unique()) <= {"risk_on", "neutral", "weak", "risk_off", "unknown"}
