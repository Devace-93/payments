"""Public catalog endpoints and the catalog sync with the fake Stripe."""
from __future__ import annotations

from sqlalchemy import select

from dbcore import stripe_client
from dbcore.catalog import create_prices, sync_catalog
from dbcore.db import session_scope
from dbcore.models import App, Product


def test_catalog_for_retro(client):
    resp = client.get("/api/catalog?app=retro")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["app"] == {"slug": "retro", "name": "Retro", "icon": "https://payments.3m4.net/icons/retro.png"}
    assert body["currencies"] == ["usd", "mxn", "eur"]
    assert body["default_currency"] == "usd"
    assert body["donation"]["min"] == {"usd": 200, "mxn": 2500, "eur": 200}
    assert body["donation"]["presets"]["usd"] == [300, 500, 1000]
    assert body["donation"]["presets"]["mxn"] == [5000, 10000, 20000]
    assert body["donation"]["max"]["usd"] == 50000
    keys = [p["key"] for p in body["products"]]
    assert keys == ["pro_monthly", "pro_annual"]
    assert body["products"][0]["amounts"] == {"usd": 500, "mxn": 9900, "eur": 500}
    assert body["products"][0]["entitlement"] == "pro"
    assert body["fee_hint"] is True
    assert resp.headers["Cache-Control"] == "public, max-age=300"
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_catalog_unknown_app(client):
    resp = client.get("/api/catalog?app=nope")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "unknown_app"
    assert client.get("/api/catalog").status_code == 400


def test_geo_without_database(client):
    resp = client.get("/api/geo", headers={"X-Forwarded-For": "187.189.1.1"})
    assert resp.status_code == 200
    assert resp.get_json() == {"country": None, "currency": "usd"}


def test_fees_endpoint(client):
    resp = client.get("/api/fees?amount=500&currency=usd&kind=donation")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["amount"] == 500 and body["currency"] == "usd"
    assert body["min_amount"] == 200
    assert 0.87 < body["retention"] < 0.89
    assert body["fee"] > 0 and body["net_mxn"] > 0
    assert client.get("/api/fees?amount=abc").get_json()["error"]["code"] == "validation_error"
    assert client.get("/api/fees?amount=500&currency=gbp").get_json()["error"]["code"] == "unsupported_currency"


def test_sync_catalog_with_fake_stripe(client):
    with session_scope() as session:
        apps = {a.slug for a in session.scalars(select(App)).all()}
        assert {"3m4", "retro", "info", "mousetouch"} <= apps
        donation = session.scalars(select(Product).where(Product.kind == "donation")).all()
        assert sorted(p.currency for p in donation) == ["eur", "mxn", "usd"]
        assert all(p.stripe_price_id.startswith("price_fake_donation_") for p in donation)
        assert all(p.stripe_product_id for p in donation)
        retro = session.scalar(select(App).where(App.slug == "retro"))
        assert retro.origins == ["https://retro.3m4.net", "http://localhost:*"]
        pro = session.scalar(select(Product).where(Product.lookup_key == "retro_pro_monthly"))
        assert pro.app_id == retro.id and pro.interval == "month" and pro.entitlement == "pro"
        # idempotent
        counts = sync_catalog(session, stripe_client.client())
        assert counts["products"] == 5
        assert session.scalar(select(Product).where(Product.lookup_key == "retro_pro_monthly")).id == pro.id


def test_create_prices_against_fake(client):
    stripe = stripe_client.FakeStripe()
    created = create_prices(stripe)
    assert set(created) == {"retro_pro_monthly", "retro_pro_annual", "donation_usd", "donation_mxn", "donation_eur"}
    price_params = [c["params"] for c in stripe.prices.calls]
    monthly = next(p for p in price_params if p["lookup_key"] == "retro_pro_monthly")
    assert monthly["currency"] == "usd" and monthly["unit_amount"] == 500
    assert monthly["currency_options"] == {"mxn": {"unit_amount": 9900}, "eur": {"unit_amount": 500}}
    assert monthly["recurring"] == {"interval": "month"}
    donation = next(p for p in price_params if p["lookup_key"] == "donation_mxn")
    assert donation["custom_unit_amount"] == {"enabled": True, "minimum": 2500, "preset": 10000}
    # second run creates nothing: the prices now resolve by lookup key
    assert create_prices(stripe) == []
    # and sync resolves the real-looking ids
    with session_scope() as session:
        sync_catalog(session, stripe)
        pro = session.scalar(select(Product).where(Product.lookup_key == "retro_pro_monthly"))
        assert pro.stripe_price_id.startswith("price_fake_") and "retro_pro_monthly" not in pro.stripe_price_id


def test_cli_sync_catalog(client, capsys):
    from dbcore import cli

    assert cli.main(["cli", "sync-catalog"]) == 0
    assert "catalog synced" in capsys.readouterr().out


def test_sync_catalog_lenient_without_prices(client, monkeypatch):
    """Boot-time sync must never block the stack: with real Stripe lacking the
    lookup keys, lenient mode writes the products without price ids and strict
    mode raises."""
    import pytest

    from dbcore import catalog
    from dbcore.models import Product

    monkeypatch.setattr(catalog, "_price_index", lambda stripe, keys: {})
    monkeypatch.setattr("dbcore.stripe_client.is_fake", lambda s: False)
    with session_scope() as session:
        with pytest.raises(RuntimeError):
            catalog.sync_catalog(session, object(), strict=True)
    with session_scope() as session:
        counts = catalog.sync_catalog(session, object(), strict=False)
        assert counts["products"] >= 5
        assert all(p.stripe_price_id is None for p in session.scalars(select(Product)))
