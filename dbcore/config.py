"""Environment-driven configuration. No secrets in code.

Every variable is documented in the repo-root ``.env.example`` and in
``CONTRACT.md → Environment``. A few internal knobs (``RATE_LIMITS_ENABLED``,
``RATE_LIMIT_STORAGE_URI``, ``WORKER_POLL_SECONDS``, ``GEOIP_DB_PATH``) exist
mainly for tests and have safe defaults.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "", lower: bool = False) -> tuple[str, ...]:
    parts = (p.strip() for p in os.getenv(name, default).split(","))
    return tuple(p.lower() if lower else p for p in parts if p)


def _json_dict(name: str, default: str) -> dict:
    raw = os.getenv(name, "").strip() or default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError(f"{name} must be a JSON object: {err}") from err
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(k).lower(): v for k, v in value.items()}


@dataclass(frozen=True)
class Config:
    # database / cache
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://payments:payments@localhost:5432/payments",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # urls
    payments_url: str = os.getenv("PAYMENTS_URL", "http://localhost:8086").rstrip("/")
    accounts_url: str = os.getenv("ACCOUNTS_URL", "http://localhost:8085").rstrip("/")
    accounts_internal_url: str = os.getenv("ACCOUNTS_INTERNAL_URL", "http://accounts-api-1:5000").rstrip("/")
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "ALLOWED_ORIGINS",
            "https://3m4.net,https://*.3m4.net,http://localhost:*,http://127.0.0.1:*",
        )
    )
    secret_key: str = os.getenv("SECRET_KEY", "dev-insecure-change-me")
    jwt_audience: str = "3m4"

    # stripe (empty secret key = FakeStripe, see dbcore/stripe_client.py)
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    stripe_automatic_tax: bool = _bool("STRIPE_AUTOMATIC_TAX", False)
    stripe_portal_configuration: str = os.getenv("STRIPE_PORTAL_CONFIGURATION", "").strip()
    stripe_integration_identifier: str = os.getenv("STRIPE_INTEGRATION_IDENTIFIER", "3m4-payments-xxxxxxxx").strip()
    stripe_api_version: str = "2026-10-28.endive"

    # money
    currencies: tuple[str, ...] = field(default_factory=lambda: _csv("CURRENCIES", "usd,mxn,eur", lower=True))
    default_currency: str = os.getenv("DEFAULT_CURRENCY", "usd").strip().lower()
    min_net_ratio: float = float(os.getenv("MIN_NET_RATIO", "0.80"))
    isr_rate: float = float(os.getenv("ISR_RATE", "0.01"))
    fx_rates_mxn: dict = field(
        default_factory=lambda: _json_dict("FX_RATES_MXN", '{"usd":18.5,"eur":21.5,"mxn":1}')
    )
    donation_max_cents: dict = field(
        default_factory=lambda: _json_dict("DONATION_MAX_CENTS", '{"usd":50000,"mxn":1000000,"eur":50000}')
    )
    claim_code_ttl_days: int = int(os.getenv("CLAIM_CODE_TTL_DAYS", "90"))

    # integrations
    github_sponsors_url: str = os.getenv("GITHUB_SPONSORS_URL", "").strip()
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
    maxmind_license_key: str = os.getenv("MAXMIND_LICENSE_KEY", "").strip()
    geoip_db_path: str = os.getenv("GEOIP_DB_PATH", "/data/GeoLite2-Country.mmdb")

    # outbound mail
    mail_enabled: bool = _bool("MAIL_ENABLED", False)
    smtp_url: str = os.getenv("SMTP_URL", "")
    mail_from: str = os.getenv("MAIL_FROM", "3m4 payments <no-reply@3m4.net>")
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "5"))

    # posthog
    posthog_api_key: str = os.getenv("POSTHOG_API_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    posthog_personal_api_key: str = os.getenv("POSTHOG_PERSONAL_API_KEY", "")
    posthog_flag_prefix: str = os.getenv("POSTHOG_FLAG_PREFIX", "payments-")

    # rate limiting
    rate_limit_default: str = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
    rate_limits_enabled: bool = _bool("RATE_LIMITS_ENABLED", True)
    rate_limit_storage_uri: str = os.getenv("RATE_LIMIT_STORAGE_URI", "") or os.getenv(
        "REDIS_URL", "redis://localhost:6379/0"
    )

    @property
    def stripe_fake(self) -> bool:
        """True when no Stripe key is configured (CI, local without an account)."""
        return not self.stripe_secret_key

    def fallback_currency(self) -> str:
        """``DEFAULT_CURRENCY`` when it is one of ``CURRENCIES``, else the first."""
        if self.default_currency in self.currencies:
            return self.default_currency
        return self.currencies[0] if self.currencies else "usd"


config = Config()
