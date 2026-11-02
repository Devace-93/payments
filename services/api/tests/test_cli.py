"""The management CLI: idempotent upgrade, app keys, seed-completed, prune."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from conftest import outbox_rows
from sqlalchemy import select

from dbcore import cli
from dbcore.db import session_scope
from dbcore.models import App, CheckoutSession, ClaimCode, Outbox, Payment, StripeEvent


def test_upgrade_is_idempotent(client, capsys):
    # create_all already ran (conftest); alembic on top must be a no-op, twice.
    assert cli.main(["cli", "upgrade"]) == 0
    assert cli.main(["cli", "migrate"]) == 0
    out = capsys.readouterr().out
    assert "tables ensured" in out and "migrations applied" in out
    with session_scope() as session:
        assert session.scalar(select(App).where(App.slug == "retro")) is not None


def test_app_key_rotates_and_sets_webhook(client, capsys):
    assert cli.main(["cli", "app-key", "retro", "https://retro.3m4.net/api/billing/webhook"]) == 0
    out = capsys.readouterr().out
    key = next(line.split()[-1] for line in out.splitlines() if line.startswith("service key:"))
    secret = next(line.split()[-1] for line in out.splitlines() if line.startswith("webhook secret:"))
    assert key.startswith("m4pay_sk_") and len(key) == len("m4pay_sk_") + 40
    assert secret.startswith("whsec_m4pay_")
    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == "retro"))
        assert app.service_key_hash == cli.hash_key(key) and app.webhook_secret == secret
        assert app.webhook_url == "https://retro.3m4.net/api/billing/webhook"
    assert client.get(f"/api/v1/entitlements/{uuid.uuid4()}?app=retro", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    # rotating keeps the url and invalidates the old key
    assert cli.main(["cli", "app-key", "retro"]) == 0
    assert client.get(f"/api/v1/entitlements/{uuid.uuid4()}?app=retro", headers={"Authorization": f"Bearer {key}"}).status_code == 401
    with session_scope() as session:
        assert session.scalar(select(App).where(App.slug == "retro")).webhook_url == "https://retro.3m4.net/api/billing/webhook"


def test_seed_completed_runs_guest_donation_path(client, capsys):
    resp = client.post("/api/checkout", json={"app": "info", "kind": "donation", "amount": 2500, "currency": "mxn", "lang": "es"})
    assert resp.status_code == 201
    with session_scope() as session:
        cs_id = session.get(CheckoutSession, uuid.UUID(resp.get_json()["id"])).stripe_session_id
    assert cli.main(["cli", "seed-completed", cs_id]) == 0
    assert "guest_donation" in capsys.readouterr().out
    with session_scope() as session:
        payment = session.scalar(select(Payment))
        assert payment.amount == 2500 and payment.currency == "mxn" and payment.identity_id is None
        assert session.scalar(select(ClaimCode)).payment_id == payment.id
    mail = outbox_rows(kind="email", template="donation_receipt")[0]
    assert mail["params"]["code"] and mail["lang"] == "es" and mail["params"]["app_name"] == "3m4 info"
    assert client.get(f"/api/checkout/{cs_id}").get_json()["needs_claim"] is True
    # replay is harmless
    assert cli.main(["cli", "seed-completed", cs_id]) == 0
    assert "duplicate" in capsys.readouterr().out


def test_seed_completed_subscription(client, capsys):
    from conftest import make_identity, session_cookie

    identity = session_cookie(client, make_identity())
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_monthly", "currency": "usd"})
    assert resp.status_code == 201
    with session_scope() as session:
        cs_id = session.get(CheckoutSession, uuid.UUID(resp.get_json()["id"])).stripe_session_id
    assert cli.main(["cli", "seed-completed", cs_id]) == 0
    assert client.get("/api/entitlements?app=retro").get_json()["entitlements"] == ["pro"]
    assert client.get("/api/me").get_json()["subscriptions"][0]["entitlement"] == "pro"
    assert [m["template"] for m in outbox_rows(kind="email")] == ["subscription_started"]
    assert identity["sub"]


def test_prune(client, capsys):
    old = datetime.now(timezone.utc) - timedelta(days=40)
    retro_id = None
    with session_scope() as session:
        retro_id = session.scalar(select(App).where(App.slug == "retro")).id
        session.add(Outbox(kind="email", status="sent", payload={}, created_at=old))
        session.add(Outbox(kind="email", status="pending", payload={}, created_at=old))
        session.add(CheckoutSession(app_id=retro_id, kind="donation", currency="usd", status="expired", created_at=old))
        session.add(CheckoutSession(app_id=retro_id, kind="donation", currency="usd", status="completed", created_at=old))
        session.add(StripeEvent(id="evt_old", type="x", received_at=old))
        payment = Payment(app_id=retro_id, kind="donation", amount=500, currency="usd")
        session.add(payment)
        session.flush()
        session.add(ClaimCode(code_hash="a" * 64, payment_id=payment.id, expires_at=old))
    assert cli.main(["cli", "prune"]) == 0
    assert "pruned 1 outbox row(s), 1 checkout(s), 1 stripe event(s), 1 claim code(s)" in capsys.readouterr().out
    with session_scope() as session:
        assert session.scalar(select(Payment)) is not None  # payments are never pruned


def test_unknown_command(capsys):
    assert cli.main(["cli", "wat"]) == 2
