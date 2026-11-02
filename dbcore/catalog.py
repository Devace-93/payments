"""The catalog: ``packages/shared/catalog.json`` mirrored into ``apps`` and
``products`` (CONTRACT.md §3).

- :func:`load` reads the JSON.
- :func:`sync_catalog` upserts apps/products and resolves each product's
  ``stripe_price_id`` by ``lookup_key`` (fails listing the missing keys; the
  fake Stripe gets ``price_fake_<lookup_key>`` ids so CI never needs an
  account).
- :func:`create_prices` creates the missing Stripe products/prices from the
  JSON (run once per sandbox and once live).
- :func:`origin_matcher` builds an :class:`OriginMatcher` from an app's
  origins for ``return_to`` / postMessage ``origin`` checks.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select

from . import fees
from ._shared import load_shared
from .models import App, Product
from .origins import OriginMatcher

log = logging.getLogger("payments.catalog")

DONATION_APP = "3m4"


def load() -> dict:
    return load_shared("catalog.json")


def currencies() -> tuple[str, ...]:
    from .config import config

    return config.currencies


def donation_presets() -> dict[str, list[int]]:
    return {k.lower(): list(v) for k, v in load().get("donation", {}).get("presets", {}).items()}


def donation_lookup_keys() -> dict[str, str]:
    return {k.lower(): v for k, v in load().get("donation", {}).get("lookup_keys", {}).items()}


def origin_matcher(app: App) -> OriginMatcher:
    return OriginMatcher(tuple(app.origins or ()))


def stripe_image(url: str | None) -> bool:
    """Stripe product images must be public PNG/JPEG URLs (SVG is not rendered)."""
    return bool(url) and bool(re.search(r"\.(png|jpe?g)(\?.*)?$", url, re.IGNORECASE))


def _upsert_app(session, entry: dict) -> App:
    app = session.scalar(select(App).where(App.slug == entry["slug"]))
    if app is None:
        app = App(slug=entry["slug"], name=entry["name"])
        session.add(app)
    app.name = entry.get("name") or app.slug
    app.origins = list(entry.get("origins") or [])
    app.icon = (entry.get("icon") or None)
    app.treat = "beer" if (entry.get("treat") or "").lower() == "beer" else "coffee"
    app.active = bool(entry.get("active", True))
    session.flush()
    return app


def _upsert_product(session, app: App, key: str, **fields) -> Product:
    product = session.scalar(select(Product).where(Product.app_id == app.id, Product.key == key))
    if product is None:
        product = Product(app_id=app.id, key=key, kind=fields["kind"], lookup_key=fields["lookup_key"])
        session.add(product)
    for name, value in fields.items():
        setattr(product, name, value)
    session.flush()
    return product


def _price_index(stripe, lookup_keys: list[str]) -> dict[str, dict]:
    """``{lookup_key: {"price": id, "product": id}}`` from Stripe."""
    from .stripe_client import as_dict

    found: dict[str, dict] = {}
    if not lookup_keys:
        return found
    for i in range(0, len(lookup_keys), 50):
        chunk = lookup_keys[i : i + 50]
        page = as_dict(stripe.v1.prices.list(params={"lookup_keys": chunk, "limit": 100, "active": True}))
        for price in page.get("data", []):
            key = price.get("lookup_key")
            if key:
                product = price.get("product")
                found[key] = {"price": price["id"], "product": product["id"] if isinstance(product, dict) else product}
    return found


def _resolve(stripe, lookup_keys: list[str], *, strict: bool = True) -> dict[str, dict]:
    from .stripe_client import is_fake

    found = _price_index(stripe, lookup_keys)
    missing = [k for k in lookup_keys if k not in found]
    if missing and is_fake(stripe):
        for key in missing:
            found[key] = {"price": f"price_fake_{key}", "product": f"prod_fake_{key}"}
        missing = []
    if missing and strict:
        raise RuntimeError(
            "catalog lookup keys without a Stripe price: " + ", ".join(missing) + " (run `python -m dbcore.cli create-prices`)"
        )
    if missing:
        log.warning(
            "catalog lookup keys without a Stripe price (products kept without price ids): %s — run `python -m dbcore.cli create-prices`",
            ", ".join(missing),
        )
    return found


def sync_catalog(session, stripe, *, strict: bool = True) -> dict:
    """Mirror the JSON into the DB; returns ``{apps, products}`` counts.

    ``strict=False`` (the boot-time run in the ``migrate`` service) tolerates
    lookup keys that Stripe does not have yet: the products are still written
    (without price ids) so the stack always starts; checkout answers
    ``unknown_price`` for them until ``create-prices`` + a strict sync."""
    data = load()
    apps = 0
    products = 0
    wanted: list[tuple[App, str, dict]] = []  # (app, key, fields)
    for entry in data.get("apps", []):
        app = _upsert_app(session, entry)
        apps += 1
        for sort, item in enumerate(entry.get("products", [])):
            amounts = {k.lower(): int(v) for k, v in (item.get("amounts") or {}).items()}
            wanted.append(
                (
                    app,
                    item["key"],
                    {
                        "kind": item.get("kind", "subscription"),
                        "entitlement": item.get("entitlement"),
                        "lookup_key": item["lookup_key"],
                        "interval": item.get("interval"),
                        "label": item.get("label") or item["key"],
                        "amounts": amounts,
                        "unit_amount": None,
                        "currency": None,
                        "sort": sort,
                        "active": bool(item.get("active", True)),
                    },
                )
            )
    donation = data.get("donation") or {}
    if donation:
        host = session.scalar(select(App).where(App.slug == DONATION_APP))
        if host is None:
            host = _upsert_app(session, {"slug": DONATION_APP, "name": "3m4", "origins": []})
            apps += 1
        for sort, (cur, lookup_key) in enumerate(sorted(donation.get("lookup_keys", {}).items())):
            wanted.append(
                (
                    host,
                    f"donation_{cur.lower()}",
                    {
                        "kind": "donation",
                        "entitlement": None,
                        "lookup_key": lookup_key,
                        "interval": None,
                        "label": donation.get("product_name") or "Support 3m4",
                        "amounts": {},
                        "unit_amount": None,
                        "currency": cur.lower(),
                        "sort": sort,
                        "active": True,
                    },
                )
            )
    resolved = _resolve(stripe, [fields["lookup_key"] for _, _, fields in wanted], strict=strict)
    for app, key, fields in wanted:
        ids = resolved.get(fields["lookup_key"]) or {"price": None, "product": None}
        _upsert_product(session, app, key, stripe_price_id=ids["price"], stripe_product_id=ids["product"], **fields)
        products += 1
    return {"apps": apps, "products": products}


def create_prices(stripe) -> list[str]:
    """Create the Stripe products/prices the JSON names but Stripe lacks.
    Returns the lookup keys created."""
    from .stripe_client import as_dict

    data = load()
    created: list[str] = []
    subs: list[tuple[dict, dict]] = [
        (entry, item) for entry in data.get("apps", []) for item in entry.get("products", [])
    ]
    donation = data.get("donation") or {}
    keys = [item["lookup_key"] for _, item in subs] + list(donation.get("lookup_keys", {}).values())
    existing = _price_index(stripe, keys)

    for entry, item in subs:
        key = item["lookup_key"]
        if key in existing:
            continue
        amounts = {k.lower(): int(v) for k, v in (item.get("amounts") or {}).items()}
        base_currency = next((c for c in currencies() if c in amounts), next(iter(amounts)))
        product = as_dict(
            stripe.v1.products.create(
                params={
                    "name": f"{entry['name']} {item.get('label') or item['key']}",
                    "metadata": {"app": entry["slug"], "key": item["key"], "entitlement": item.get("entitlement") or ""},
                    **({"images": [entry["icon"]]} if stripe_image(entry.get("icon")) else {}),
                }
            )
        )
        params = {
            "product": product["id"],
            "currency": base_currency,
            "unit_amount": amounts[base_currency],
            "lookup_key": key,
            "transfer_lookup_key": True,
            "recurring": {"interval": item.get("interval") or "month"},
            "metadata": {"app": entry["slug"], "key": item["key"]},
        }
        options = {cur: {"unit_amount": cents} for cur, cents in amounts.items() if cur != base_currency}
        if options:
            params["currency_options"] = options
        stripe.v1.prices.create(params=params)
        created.append(key)

    lookup_keys = {k.lower(): v for k, v in donation.get("lookup_keys", {}).items()}
    missing = {cur: key for cur, key in lookup_keys.items() if key not in existing}
    if missing:
        product_id = next((v["product"] for k, v in existing.items() if k in lookup_keys.values()), None)
        if product_id is None:
            product = as_dict(
                stripe.v1.products.create(
                    params={"name": donation.get("product_name") or "Support 3m4", "metadata": {"app": DONATION_APP, "kind": "donation"}}
                )
            )
            product_id = product["id"]
        presets = donation_presets()
        for cur, key in sorted(missing.items()):
            preset_list = fees.presets(presets, cur)
            preset = preset_list[1] if len(preset_list) > 1 else preset_list[0]
            stripe.v1.prices.create(
                params={
                    "product": product_id,
                    "currency": cur,
                    "lookup_key": key,
                    "transfer_lookup_key": True,
                    "custom_unit_amount": {"enabled": True, "minimum": fees.min_amount(cur), "preset": preset},
                    "metadata": {"app": DONATION_APP, "kind": "donation"},
                }
            )
            created.append(key)
    return created
