"""``return_to`` handling: never redirect off the 3m4 family.

An absolute URL is accepted only when its origin matches ``ALLOWED_ORIGINS``;
a root-relative path (``/me``) is resolved against ``PAYMENTS_URL``; anything
else (other hosts, ``//evil``, ``javascript:``) falls back to the ``/me``
page. Checkout additionally requires the URL to match the *app's* origins
(see ``blueprints/checkout.py``).
"""
from __future__ import annotations

from dbcore.config import config
from dbcore.origins import matcher

DEFAULT_PATH = "/me"
MAX_LEN = 2000


def default_return_to() -> str:
    return f"{config.payments_url}{DEFAULT_PATH}"


def is_safe_return_to(url: str | None) -> bool:
    """True when ``url`` is an absolute URL on an allowed origin."""
    if not url or not isinstance(url, str) or len(url) > MAX_LEN:
        return False
    return matcher.allows_url(url.strip())


def safe_return_to(url: str | None) -> str:
    if not url or not isinstance(url, str) or len(url) > MAX_LEN:
        return default_return_to()
    url = url.strip()
    if url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return f"{config.payments_url}{url}"
    if matcher.allows_url(url):
        return url
    return default_return_to()
