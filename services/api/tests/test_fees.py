"""Lock the fee model numbers (plan → "Minimum amounts and fee model")."""
from __future__ import annotations

import pytest

from dbcore import fees


@pytest.mark.parametrize(
    "amount,currency,kind,retention",
    [
        (200, "usd", "donation", 0.825),
        (3500, "mxn", "donation", 0.849),
        (500, "usd", "subscription", 0.873),
        (100, "usd", "donation", 0.73),
        (1000, "usd", "donation", 0.90),
        (500, "eur", "donation", 0.89),
        (10000, "mxn", "donation", 0.913),
    ],
)
def test_retention_numbers(amount, currency, kind, retention):
    est = fees.estimate(amount, currency, kind)
    assert est["retention"] == pytest.approx(retention, abs=0.005)
    assert est["net_mxn"] < est["gross_mxn"]


def test_estimate_breakdown_usd_2():
    est = fees.estimate(200, "usd")
    assert est["gross_mxn"] == 37.0
    assert est["fee_mxn"] == pytest.approx(5.26, abs=0.01)
    assert est["tax_mxn"] == pytest.approx(0.84, abs=0.01)
    assert est["isr_mxn"] == pytest.approx(0.37, abs=0.01)
    assert est["net_mxn"] == pytest.approx(30.53, abs=0.01)


def test_min_amounts_with_defaults():
    assert fees.min_amount("usd") == 200
    assert fees.min_amount("eur") == 200
    assert fees.min_amount("mxn") == 2500


def test_min_amount_respects_ratio_and_floor():
    assert fees.min_amount("usd", ratio=0.85) == 300
    assert fees.min_amount("mxn", ratio=0.85) == 4000  # 35.42 MXN rounded up to the 5 MXN step
    assert fees.min_amount("usd", ratio=0.0) == 100  # Stripe floor (50) rounded up to a unit
    assert fees.estimate(fees.min_amount("eur"), "eur")["retention"] >= 0.80


def test_presets_never_below_minimum():
    presets = {"usd": [100, 500, 1000], "mxn": [1000, 10000]}
    assert fees.presets(presets, "usd") == [200, 500, 1000]
    assert fees.presets(presets, "mxn") == [2500, 10000]
    assert fees.presets({}, "eur") == [200]


def test_estimate_rejects_bad_input():
    with pytest.raises(ValueError):
        fees.estimate(0, "usd")
    with pytest.raises(ValueError):
        fees.estimate(100, "gbp")
