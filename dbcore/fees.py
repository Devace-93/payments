"""Fee model for a Stripe account in Mexico (CONTRACT.md §8). Pure functions.

Stripe MX card pricing: 3.6 % + MXN 3.00 per successful domestic charge,
+0.5 % for international cards, +2 % currency conversion when the charge
currency is not MXN, 16 % IVA on Stripe's fee, +0.7 % Billing on
subscriptions. ISR (``ISR_RATE``, RESICO) applies to the gross.

Everything is computed in MXN (where the account settles) using the
reference rates in ``FX_RATES_MXN``. ``retention`` is the share of the gross
that reaches the owner; ``min_amount(currency)`` is the smallest amount whose
retention is at least ``MIN_NET_RATIO``, rounded up to a whole unit (``usd`` /
``eur``) or to 5 MXN, never below Stripe's own charge minimum.
"""
from __future__ import annotations

import math

from .config import config

STRIPE_PERCENT = 0.036
STRIPE_FIXED_MXN = 3.00
INTERNATIONAL_CARD_PERCENT = 0.005
FX_PERCENT = 0.02
IVA_RATE = 0.16
BILLING_PERCENT = 0.007

# Stripe's minimum charge amounts (minor units) for the currencies we accept.
STRIPE_MIN_CENTS: dict[str, int] = {"usd": 50, "eur": 50, "mxn": 1000}

# Rounding step for the published minimum: whole units for USD/EUR, 5 MXN.
ROUND_STEP_CENTS: dict[str, int] = {"usd": 100, "eur": 100, "mxn": 500}

# Minor units per major unit (every currency we accept is 2-decimal).
UNIT_CENTS = 100


def fx_rate(currency: str) -> float:
    """MXN per one unit of ``currency``; raises for unknown currencies."""
    currency = currency.lower()
    if currency == "mxn":
        return 1.0
    try:
        return float(config.fx_rates_mxn[currency])
    except KeyError as err:
        raise ValueError(f"no FX rate for {currency!r}") from err


def to_mxn(amount_cents: int, currency: str) -> float:
    """``amount_cents`` of ``currency`` as MXN (major units, float)."""
    return amount_cents / UNIT_CENTS * fx_rate(currency)


def estimate(amount: int, currency: str, kind: str = "donation", domestic: bool | None = None) -> dict:
    """Cost breakdown of one charge of ``amount`` minor units of ``currency``.

    ``domestic`` (card issued in Mexico) defaults to ``currency == "mxn"``.
    Returns ``{amount, currency, gross_mxn, fee_mxn, tax_mxn, isr_mxn,
    net_mxn, retention}``; ``fee_mxn`` is Stripe's fee before IVA.
    """
    currency = currency.lower()
    if amount <= 0:
        raise ValueError("amount must be positive")
    if domestic is None:
        domestic = currency == "mxn"
    gross = to_mxn(amount, currency)
    percent = STRIPE_PERCENT
    if not domestic:
        percent += INTERNATIONAL_CARD_PERCENT
    if currency != "mxn":
        percent += FX_PERCENT
    if kind == "subscription":
        percent += BILLING_PERCENT
    fee = gross * percent + STRIPE_FIXED_MXN
    tax = fee * IVA_RATE
    isr = gross * config.isr_rate
    net = gross - fee - tax - isr
    return {
        "amount": amount,
        "currency": currency,
        "gross_mxn": round(gross, 2),
        "fee_mxn": round(fee, 2),
        "tax_mxn": round(tax, 2),
        "isr_mxn": round(isr, 2),
        "net_mxn": round(net, 2),
        "retention": round(net / gross, 4) if gross else 0.0,
    }


def _round_up(cents: int, step: int) -> int:
    return int(math.ceil(cents / step) * step)


def min_amount(currency: str, kind: str = "donation", ratio: float | None = None) -> int:
    """Smallest amount (minor units) whose retention is ≥ ``ratio``
    (``MIN_NET_RATIO``), rounded up to the currency's step and never below
    Stripe's charge minimum."""
    currency = currency.lower()
    ratio = config.min_net_ratio if ratio is None else ratio
    step = ROUND_STEP_CENTS.get(currency, UNIT_CENTS)
    floor = STRIPE_MIN_CENTS.get(currency, 50)
    rate = fx_rate(currency)
    # Solve gross*(1 - p - p*IVA - isr) - fixed*(1+IVA) >= ratio*gross for gross (MXN).
    percent = STRIPE_PERCENT + (0 if currency == "mxn" else INTERNATIONAL_CARD_PERCENT + FX_PERCENT)
    if kind == "subscription":
        percent += BILLING_PERCENT
    variable = 1 - percent * (1 + IVA_RATE) - config.isr_rate - ratio
    if variable <= 0:
        raise ValueError("MIN_NET_RATIO is unreachable with the current fee table")
    gross_mxn = STRIPE_FIXED_MXN * (1 + IVA_RATE) / variable
    cents = int(math.ceil(gross_mxn / rate * UNIT_CENTS))
    cents = max(cents, floor)
    cents = _round_up(cents, step)
    # Rounding is monotonic, but guard against float noise with one check.
    while estimate(cents, currency, kind)["retention"] < ratio - 1e-9:
        cents += step
    return cents


def max_amount(currency: str) -> int | None:
    """``DONATION_MAX_CENTS`` for the currency (None when unset)."""
    value = config.donation_max_cents.get(currency.lower())
    return int(value) if value is not None else None


def presets(catalog_presets: dict | None, currency: str) -> list[int]:
    """Donation presets of ``currency`` from the catalog, each raised to at
    least ``min_amount`` so the page never offers an invalid amount."""
    currency = currency.lower()
    floor = min_amount(currency)
    raw = (catalog_presets or {}).get(currency) or []
    out: list[int] = []
    for value in raw:
        cents = max(int(value), floor)
        if cents not in out:
            out.append(cents)
    return out or [floor]
