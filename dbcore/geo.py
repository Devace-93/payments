"""IP → country → currency (``GET /api/geo``), the last fallback of the
currency resolution order (CONTRACT.md §7).

Uses MaxMind's GeoLite2-Country database at ``GEOIP_DB_PATH`` when present;
``python -m dbcore.cli geoip-update`` downloads it with
``MAXMIND_LICENSE_KEY``. Without the file every lookup is ``(None,
DEFAULT_CURRENCY)``: this must never error.
"""
from __future__ import annotations

import io
import logging
import os
import tarfile
import threading
from pathlib import Path

from .config import config

log = logging.getLogger("payments.geo")

EURO_COUNTRIES = frozenset(
    "AT BE HR CY EE FI FR DE GR IE IT LV LT LU MT NL PT SK SI ES "
    "AD MC SM VA ME XK".split()
)
COUNTRY_CURRENCY = {"MX": "mxn", "US": "usd"}

_reader = None
_reader_lock = threading.Lock()
_reader_mtime: float | None = None


def currency_for_country(country: str | None) -> str:
    """Currency for a country code, restricted to ``CURRENCIES``."""
    fallback = config.fallback_currency()
    if not country:
        return fallback
    country = country.upper()
    cur = COUNTRY_CURRENCY.get(country) or ("eur" if country in EURO_COUNTRIES else None)
    return cur if cur in config.currencies else fallback


def _get_reader():
    global _reader, _reader_mtime
    path = Path(config.geoip_db_path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    with _reader_lock:
        if _reader is None or _reader_mtime != mtime:
            try:
                import geoip2.database

                _reader = geoip2.database.Reader(str(path))
                _reader_mtime = mtime
            except Exception as err:  # pragma: no cover - corrupt file
                log.warning("geoip database unusable: %s", err)
                _reader = None
        return _reader


def country_for_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        return reader.country(ip).country.iso_code
    except Exception:
        return None


def lookup(ip: str | None) -> dict:
    """``{"country": "MX"|None, "currency": "mxn"}``; never raises."""
    try:
        country = country_for_ip(ip)
    except Exception:  # pragma: no cover
        country = None
    return {"country": country, "currency": currency_for_country(country)}


def update_database() -> Path:
    """Download GeoLite2-Country into ``GEOIP_DB_PATH`` (needs
    ``MAXMIND_LICENSE_KEY``). Returns the path written."""
    import requests

    if not config.maxmind_license_key:
        raise RuntimeError("MAXMIND_LICENSE_KEY is not set")
    url = (
        "https://download.maxmind.com/app/geoip_download"
        f"?edition_id=GeoLite2-Country&license_key={config.maxmind_license_key}&suffix=tar.gz"
    )
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    target = Path(config.geoip_db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith(".mmdb")), None)
        if member is None:
            raise RuntimeError("archive has no .mmdb file")
        data = tar.extractfile(member)
        if data is None:  # pragma: no cover
            raise RuntimeError("could not read the .mmdb member")
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data.read())
        os.replace(tmp, target)
    return target
