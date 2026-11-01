"""Origin allow-list used for credentialed CORS and ``return_to`` redirects.

Patterns come from ``ALLOWED_ORIGINS`` (comma-separated). Each pattern is
``scheme://host[:port]`` where ``*`` matches exactly one DNS label in the
host (``https://*.3m4.net`` matches ``https://app.3m4.net`` but not
``https://a.b.3m4.net`` nor ``https://3m4.net``) and ``:*`` matches any
port or none (``http://localhost:*``). Matching is case-insensitive on the
whole origin and never partial.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .config import config


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.strip().rstrip("/")
    scheme, _, rest = pattern.partition("://")
    host, _, port = rest.partition(":")
    host_re = r"\.".join(
        r"[a-z0-9-]+" if label == "*" else re.escape(label.lower()) for label in host.split(".")
    )
    if port == "*":
        port_re = r"(?::\d{1,5})?"
    elif port:
        port_re = ":" + re.escape(port)
    else:
        port_re = ""
    return re.compile(rf"^{re.escape(scheme.lower())}://{host_re}{port_re}$")


class OriginMatcher:
    def __init__(self, patterns: tuple[str, ...] | list[str]):
        self._regexes = [_pattern_to_regex(p) for p in patterns if p and "://" in p]

    def allows(self, origin: str | None) -> bool:
        if not origin:
            return False
        origin = origin.strip().rstrip("/").lower()
        return any(r.match(origin) for r in self._regexes)

    def allows_url(self, url: str | None) -> bool:
        """True when ``url`` is absolute and its origin is allowed."""
        if not url:
            return False
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return False
        return self.allows(f"{parts.scheme}://{parts.netloc}")


matcher = OriginMatcher(config.allowed_origins)
