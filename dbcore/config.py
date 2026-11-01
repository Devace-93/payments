"""Environment-driven configuration. No secrets in code.

Every variable is documented in the repo-root ``.env.example``. A few
internal knobs (``RATE_LIMITS_ENABLED``, ``RATE_LIMIT_STORAGE_URI``,
``WORKER_POLL_SECONDS``, token TTLs) exist mainly for tests and have safe
defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(p.strip() for p in os.getenv(name, default).split(",") if p.strip())


@dataclass(frozen=True)
class Config:
    # database / cache
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://accounts:accounts@localhost:5432/accounts",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # sessions
    session_signing_key: str = os.getenv("SESSION_SIGNING_KEY", "")
    session_previous_public_keys: tuple[str, ...] = field(
        default_factory=lambda: _csv("SESSION_PREVIOUS_PUBLIC_KEYS")
    )
    session_ttl_min: int = int(os.getenv("SESSION_TTL_MIN", "15"))
    refresh_ttl_days: int = int(os.getenv("REFRESH_TTL_DAYS", "30"))
    cookie_domain: str = os.getenv("COOKIE_DOMAIN", "").strip()
    cookie_secure: bool = _bool("COOKIE_SECURE", False)
    accounts_url: str = os.getenv("ACCOUNTS_URL", "http://localhost:8085").rstrip("/")
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "ALLOWED_ORIGINS",
            "https://3m4.net,https://*.3m4.net,http://localhost:*,http://127.0.0.1:*",
        )
    )
    secret_key: str = os.getenv("SECRET_KEY", "dev-insecure-change-me")
    ip_hash_secret: str = os.getenv("IP_HASH_SECRET", "dev-insecure-ip-salt")
    jwt_audience: str = "3m4"

    # email tokens
    magic_token_ttl_min: int = int(os.getenv("MAGIC_TOKEN_TTL_MIN", "15"))
    verify_token_ttl_hours: int = int(os.getenv("VERIFY_TOKEN_TTL_HOURS", "24"))

    # oauth providers (enabled when both id and secret are set)
    oauth_google_client_id: str = os.getenv("OAUTH_GOOGLE_CLIENT_ID", "")
    oauth_google_client_secret: str = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET", "")
    oauth_github_client_id: str = os.getenv("OAUTH_GITHUB_CLIENT_ID", "")
    oauth_github_client_secret: str = os.getenv("OAUTH_GITHUB_CLIENT_SECRET", "")
    oauth_discord_client_id: str = os.getenv("OAUTH_DISCORD_CLIENT_ID", "")
    oauth_discord_client_secret: str = os.getenv("OAUTH_DISCORD_CLIENT_SECRET", "")

    # outbound mail
    mail_enabled: bool = _bool("MAIL_ENABLED", False)
    smtp_url: str = os.getenv("SMTP_URL", "")
    mail_from: str = os.getenv("MAIL_FROM", "3m4 accounts <no-reply@3m4.net>")
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "5"))

    # posthog
    posthog_api_key: str = os.getenv("POSTHOG_API_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    posthog_personal_api_key: str = os.getenv("POSTHOG_PERSONAL_API_KEY", "")
    posthog_flag_prefix: str = os.getenv("POSTHOG_FLAG_PREFIX", "accounts-")

    # rate limiting
    rate_limit_default: str = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
    rate_limits_enabled: bool = _bool("RATE_LIMITS_ENABLED", True)
    rate_limit_storage_uri: str = os.getenv("RATE_LIMIT_STORAGE_URI", "") or os.getenv(
        "REDIS_URL", "redis://localhost:6379/0"
    )

    def oauth_credentials(self, provider: str) -> tuple[str, str] | None:
        """``(client_id, client_secret)`` for a configured provider, else None."""
        cid = getattr(self, f"oauth_{provider}_client_id", "")
        secret = getattr(self, f"oauth_{provider}_client_secret", "")
        if cid and secret:
            return cid, secret
        return None


config = Config()
