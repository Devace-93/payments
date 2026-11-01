"""Thin PostHog wrapper. No-ops when POSTHOG_API_KEY is unset (self-host friendly).

Person id is always the accounts user id, so events line up with the other
3m4 apps once they identify the same id.
"""
from __future__ import annotations

from .config import config

_client = None


def _get():
    global _client
    if not config.posthog_api_key:
        return None
    if _client is None:
        import posthog

        posthog.api_key = config.posthog_api_key
        posthog.host = config.posthog_host
        _client = posthog
    return _client


def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    ph = _get()
    if ph is None:
        return
    try:
        ph.capture(distinct_id=distinct_id, event=event, properties=properties or {})
    except Exception:
        # analytics must never break a request
        pass
