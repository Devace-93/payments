"""Stripe webhook: signature, dedupe, and the handlers end to end."""
from __future__ import annotations

import time
import uuid

from conftest import app_row, make_identity, outbox_rows, post_event, session_cookie, set_webhook, signed_event, stripe_event
from sqlalchemy import select

from dbcore.db import session_scope
from dbcore.models import CheckoutSession, ClaimCode, Payment, StripeEvent, Subscription


def _donation_row(client, **overrides) -> tuple[str, str]:
    body = {"app": "retro", "kind": "donation", "amount": 500, "currency": "usd", "public": True, "display_name": "Ana", "lang": "es"}
    body.update(overrides)
    resp = client.post("/api/checkout", json=body)
    assert resp.status_code == 201, resp.get_json()
    row_id = resp.get_json()["id"]
    with session_scope() as session:
        return row_id, session.get(CheckoutSession, uuid.UUID(row_id)).stripe_session_id


def completed_session(cs_id: str, row_id: str, *, email="guest@example.com", identity_id=None, pi="pi_1", amount=500, currency="usd") -> dict:
    metadata = {"app": "retro", "kind": "donation", "checkout_id": row_id}
    if identity_id:
        metadata["identity_id"] = identity_id
    return {
        "id": cs_id,
        "object": "checkout.session",
        "mode": "payment",
        "status": "complete",
        "payment_status": "paid",
        "client_reference_id": row_id,
        "metadata": metadata,
        "amount_total": amount,
        "currency": currency,
        "customer": "cus_1",
        "customer_details": {"email": email},
        "payment_intent": pi,
    }


def test_bad_signature_rejected(client):
    body, headers = signed_event(stripe_event("checkout.session.completed", {"id": "cs_x"}), secret="wrong")
    resp = client.post("/api/stripe/webhook", data=body, headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_signature"
    assert client.post("/api/stripe/webhook", data=body, headers={"Content-Type": "application/json"}).status_code == 400


def test_unknown_event_ignored_and_deduped(client):
    resp = post_event(client, "customer.created", {"id": "cus_1"}, event_id="evt_1")
    assert resp.status_code == 200 and resp.get_json() == {"status": "ignored"}
    resp = post_event(client, "customer.created", {"id": "cus_1"}, event_id="evt_1")
    assert resp.get_json() == {"status": "duplicate"}
    with session_scope() as session:
        row = session.get(StripeEvent, "evt_1")
        assert row.type == "customer.created" and row.status == "ignored"


def test_guest_donation_completed(client):
    row_id, cs_id = _donation_row(client)
    resp = post_event(client, "checkout.session.completed", completed_session(cs_id, row_id), event_id="evt_done")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json() == {"status": "guest_donation"}
    with session_scope() as session:
        payment = session.scalar(select(Payment))
        assert payment.stripe_payment_intent_id == "pi_1" and payment.amount == 500 and payment.status == "paid"
        assert payment.email == "guest@example.com" and payment.identity_id is None
        assert payment.public is True and payment.display_name == "Ana"
        code = session.scalar(select(ClaimCode))
        assert code.payment_id == payment.id and code.used_at is None
        assert session.get(CheckoutSession, uuid.UUID(row_id)).status == "completed"
    mails = outbox_rows(kind="email", template="donation_receipt")
    assert len(mails) == 1
    mail = mails[0]
    assert mail["to"] == "guest@example.com" and mail["lang"] == "es"
    code = mail["params"]["code"]
    assert len(code) == 19 and code.count("-") == 3
    assert mail["params"]["amount"] == 500 and mail["params"]["app_name"] == "Retro"
    # no push for guests, and a replay is a duplicate
    assert outbox_rows(kind="webhook") == []
    assert post_event(client, "checkout.session.completed", completed_session(cs_id, row_id), event_id="evt_done").get_json() == {"status": "duplicate"}
    # a second delivery under a new event id is idempotent on the payment intent
    assert post_event(client, "checkout.session.async_payment_succeeded", completed_session(cs_id, row_id)).get_json() == {"status": "duplicate"}
    with session_scope() as session:
        assert session.scalar(select(Payment.id).where(Payment.stripe_payment_intent_id == "pi_1")) is not None
        assert len(session.scalars(select(Payment)).all()) == 1
    status = client.get(f"/api/checkout/{row_id}").get_json()
    assert status["status"] == "completed" and status["needs_claim"] is True and status["claimed"] is False


def test_unpaid_completed_waits_for_async_payment(client):
    row_id, cs_id = _donation_row(client)
    cs = completed_session(cs_id, row_id)
    cs["payment_status"] = "unpaid"
    assert post_event(client, "checkout.session.completed", cs).get_json() == {"status": "pending_payment"}
    with session_scope() as session:
        assert session.scalar(select(Payment)) is None
    cs["payment_status"] = "paid"
    assert post_event(client, "checkout.session.async_payment_succeeded", cs).get_json() == {"status": "guest_donation"}


def test_logged_in_donation_pushes_and_mails_without_code(client):
    set_webhook("retro")
    identity = session_cookie(client, make_identity())
    row_id, cs_id = _donation_row(client, public=False)
    cs = completed_session(cs_id, row_id, email=identity["email"], identity_id=identity["sub"], pi="pi_2")
    assert post_event(client, "checkout.session.completed", cs).get_json() == {"status": "donation"}
    with session_scope() as session:
        payment = session.scalar(select(Payment))
        assert str(payment.identity_id) == identity["sub"]
        assert session.scalar(select(ClaimCode)) is None
    mail = outbox_rows(kind="email")[0]
    assert "code" not in mail["params"] and mail["to"] == identity["email"]
    hooks = outbox_rows(kind="webhook")
    assert len(hooks) == 1
    event = hooks[0]["event"]
    assert event["type"] == "payment.succeeded" and event["app"] == "retro" and event["identity_id"] == identity["sub"]
    assert event["data"]["entitlements"] == [] and event["data"]["payment"]["amount"] == 500
    assert event["data"]["payment"]["kind"] == "donation"
    me = client.get("/api/me").get_json()
    assert me["customer"]["has_stripe_customer"] is True
    assert me["payments"][0]["amount"] == 500 and me["payments"][0]["app"] == "retro"


def test_refund_voids_code_and_public(client):
    set_webhook("retro")
    row_id, cs_id = _donation_row(client)
    post_event(client, "checkout.session.completed", completed_session(cs_id, row_id, pi="pi_3"))
    code = outbox_rows(kind="email")[0]["params"]["code"]
    resp = post_event(client, "charge.refunded", {"id": "ch_1", "object": "charge", "payment_intent": "pi_3", "refunded": True, "amount_refunded": 500, "amount": 500})
    assert resp.get_json() == {"status": "refunded"}
    with session_scope() as session:
        payment = session.scalar(select(Payment))
        assert payment.status == "refunded" and payment.public is False and payment.amount_refunded == 500
        assert payment.stripe_charge_id == "ch_1"
        assert session.scalar(select(ClaimCode)).voided_at is not None
    identity = session_cookie(client, make_identity())
    resp = client.post("/api/claim", json={"code": code})
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid_code"
    assert client.get("/api/public/supporters?app=retro").get_json()["items"] == []
    # partial refund keeps it paid-ish
    row_id2, cs_id2 = _donation_row(client)
    post_event(client, "checkout.session.completed", completed_session(cs_id2, row_id2, pi="pi_4", identity_id=identity["sub"]))
    post_event(client, "charge.refunded", {"id": "ch_2", "payment_intent": "pi_4", "refunded": False, "amount_refunded": 100, "amount": 500})
    with session_scope() as session:
        p = session.scalar(select(Payment).where(Payment.stripe_payment_intent_id == "pi_4"))
        assert p.status == "partially_refunded" and p.amount_refunded == 100
    pushes = [h["event"]["type"] for h in outbox_rows(kind="webhook")]
    assert pushes == ["payment.succeeded", "payment.refunded"]


def test_dispute_marks_disputed(client):
    row_id, cs_id = _donation_row(client)
    post_event(client, "checkout.session.completed", completed_session(cs_id, row_id, pi="pi_5"))
    resp = post_event(client, "charge.dispute.created", {"id": "dp_1", "charge": "ch_9", "payment_intent": "pi_5"})
    assert resp.get_json() == {"status": "disputed"}
    with session_scope() as session:
        payment = session.scalar(select(Payment))
        assert payment.status == "disputed" and payment.public is False


def test_checkout_expired(client):
    row_id, cs_id = _donation_row(client)
    assert post_event(client, "checkout.session.expired", {"id": cs_id, "object": "checkout.session"}).get_json() == {"status": "expired"}
    assert client.get(f"/api/checkout/{row_id}").get_json()["status"] == "expired"


# --------------------------------------------------------------------------- #
# subscriptions
# --------------------------------------------------------------------------- #
def sub_object(sub_id: str, identity_id: str, *, status="active", cancel=False, lookup_key="retro_pro_monthly", now=None) -> dict:
    now = now or int(time.time())
    return {
        "id": sub_id,
        "object": "subscription",
        "status": status,
        "customer": "cus_sub",
        "cancel_at_period_end": cancel,
        "canceled_at": now if cancel else None,
        "metadata": {"app": "retro", "kind": "subscription", "identity_id": identity_id},
        "items": {"data": [{"price": {"id": f"price_fake_{lookup_key}", "lookup_key": lookup_key}, "current_period_start": now, "current_period_end": now + 30 * 86400}]},
    }


def test_subscription_lifecycle(client):
    set_webhook("retro")
    identity = session_cookie(client, make_identity())
    uid = uuid.UUID(identity["sub"])
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_monthly", "currency": "usd", "lang": "en"})
    assert resp.status_code == 201
    row_id = resp.get_json()["id"]
    with session_scope() as session:
        cs_id = session.get(CheckoutSession, uuid.UUID(row_id)).stripe_session_id
    now = int(time.time())
    # created arrives first (out of order with completed is fine)
    resp = post_event(client, "customer.subscription.created", sub_object("sub_1", identity["sub"], now=now), created=now)
    assert resp.get_json() == {"status": "created"}
    cs = {
        "id": cs_id,
        "object": "checkout.session",
        "mode": "subscription",
        "status": "complete",
        "payment_status": "paid",
        "metadata": {"app": "retro", "kind": "subscription", "checkout_id": row_id, "identity_id": identity["sub"]},
        "amount_total": 500,
        "currency": "usd",
        "customer": "cus_sub",
        "customer_details": {"email": identity["email"]},
        "subscription": sub_object("sub_1", identity["sub"], now=now),
    }
    assert post_event(client, "checkout.session.completed", cs, created=now + 1).get_json() == {"status": "subscription"}
    ent = client.get("/api/entitlements?app=retro").get_json()
    assert ent["app"] == "retro" and ent["entitlements"] == ["pro"]
    assert ent["subscription"]["status"] == "active" and ent["subscription"]["cancel_at_period_end"] is False
    assert client.get("/api/entitlements?app=info").get_json()["entitlements"] == []
    status = client.get(f"/api/checkout/{row_id}").get_json()
    assert status["status"] == "completed" and status["entitlements"] == ["pro"]
    # mail: started once, on the checkout completion (not on the created event)
    assert [m["template"] for m in outbox_rows(kind="email")] == ["subscription_started"]
    hooks = outbox_rows(kind="webhook")
    assert all(h["event"]["type"] == "subscription.updated" for h in hooks)
    assert hooks[-1]["event"]["data"]["entitlements"] == ["pro"]
    assert hooks[-1]["event"]["data"]["subscription"]["status"] == "active"

    # invoice.paid → history row
    inv = {"id": "in_1", "object": "invoice", "amount_paid": 500, "currency": "usd", "customer_email": identity["email"], "payment_intent": "pi_inv", "parent": {"subscription_details": {"subscription": "sub_1"}}, "billing_reason": "subscription_cycle"}
    assert post_event(client, "invoice.paid", inv, created=now + 2).get_json() == {"status": "invoice"}
    assert post_event(client, "invoice.paid", inv, created=now + 3).get_json() == {"status": "duplicate"}
    me = client.get("/api/me").get_json()
    assert me["payments"][0]["kind"] == "invoice" and me["payments"][0]["amount"] == 500
    assert me["subscriptions"][0]["entitlement"] == "pro" and me["subscriptions"][0]["label"] == "Pro"

    # cancel at period end: still entitled, mail queued once
    assert post_event(client, "customer.subscription.updated", sub_object("sub_1", identity["sub"], cancel=True, now=now), created=now + 4).get_json() == {"status": "updated"}
    ent = client.get("/api/entitlements?app=retro").get_json()
    assert ent["entitlements"] == ["pro"] and ent["subscription"]["cancel_at_period_end"] is True
    assert [m["template"] for m in outbox_rows(kind="email")] == ["subscription_started", "subscription_cancelled"]
    assert outbox_rows(kind="email")[1]["to"] == identity["email"]

    # stale event (older than what we have) is ignored
    assert post_event(client, "customer.subscription.updated", sub_object("sub_1", identity["sub"], cancel=False, now=now), created=now + 1).get_json() == {"status": "stale"}
    assert client.get("/api/entitlements?app=retro").get_json()["subscription"]["cancel_at_period_end"] is True

    # payment failed → mail
    assert post_event(client, "invoice.payment_failed", {"id": "in_2", "object": "invoice", "customer_email": identity["email"], "parent": {"subscription_details": {"subscription": "sub_1"}}}, created=now + 5).get_json() == {"status": "payment_failed"}
    assert [m["template"] for m in outbox_rows(kind="email")][-1] == "payment_failed"

    # deleted → no entitlement (period end in the past)
    gone = sub_object("sub_1", identity["sub"], status="canceled", cancel=True, now=now - 60 * 86400)
    assert post_event(client, "customer.subscription.deleted", gone, created=now + 6).get_json() == {"status": "deleted"}
    ent = client.get("/api/entitlements?app=retro").get_json()
    assert ent["entitlements"] == [] and ent["subscription"]["status"] == "canceled"
    assert outbox_rows(kind="webhook")[-1]["event"]["data"]["entitlements"] == []
    with session_scope() as session:
        sub = session.scalar(select(Subscription))
        assert sub.identity_id == uid and sub.status == "canceled" and sub.app_id == app_row("retro").id
    # and the subscriptions flag never gates entitlement reads
    assert client.get("/api/entitlements?app=retro").status_code == 200


def test_subscription_without_identity_is_ignored(client):
    obj = sub_object("sub_x", "")
    obj["metadata"] = {}
    assert post_event(client, "customer.subscription.created", obj).get_json() == {"status": "no_identity"}
    with session_scope() as session:
        assert session.scalar(select(Subscription)) is None


def test_subscription_started_mail_from_checkout(client):
    identity = session_cookie(client, make_identity())
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_annual", "currency": "eur"})
    row_id = resp.get_json()["id"]
    with session_scope() as session:
        cs_id = session.get(CheckoutSession, uuid.UUID(row_id)).stripe_session_id
    cs = {
        "id": cs_id,
        "mode": "subscription",
        "status": "complete",
        "payment_status": "paid",
        "metadata": {"checkout_id": row_id},
        "amount_total": 5000,
        "currency": "eur",
        "customer": "cus_sub2",
        "customer_details": {"email": identity["email"]},
        "subscription": sub_object("sub_2", identity["sub"], lookup_key="retro_pro_annual"),
    }
    assert post_event(client, "checkout.session.completed", cs).get_json() == {"status": "subscription"}
    mails = outbox_rows(kind="email")
    assert len(mails) == 1 and mails[0]["template"] == "subscription_started"
    assert mails[0]["params"]["label"] == "Pro (annual)" and mails[0]["params"]["amount"] == 5000 and mails[0]["params"]["currency"] == "eur"
    assert mails[0]["params"]["interval"] == "year"
    # seed-completed style replay via the same handler is a no-op for the mail
    assert post_event(client, "checkout.session.completed", cs).get_json() == {"status": "subscription"}
    assert len(outbox_rows(kind="email")) == 1


def test_invoice_paid_before_subscription_created(client, monkeypatch):
    """Stripe often delivers ``invoice.paid`` before ``customer.subscription.created``.
    In real mode the handler builds the mirror row from Stripe's current
    subscription instead of dropping the invoice."""
    from api import stripe_events as se

    set_webhook("retro")
    identity = make_identity()
    now = int(time.time())
    sub = sub_object("sub_first", identity["sub"], now=now)
    monkeypatch.setattr(se, "is_fake", lambda _stripe: False)
    monkeypatch.setattr(se, "_retrieve_subscription", lambda _stripe, sid: sub if sid == "sub_first" else None)
    inv = {
        "id": "in_first", "object": "invoice", "amount_paid": 500, "currency": "usd",
        "customer_email": identity["email"], "payment_intent": "pi_first",
        "parent": {"subscription_details": {"subscription": "sub_first"}}, "billing_reason": "subscription_create",
    }
    with session_scope() as session:
        assert se.handle_invoice_paid(session, object(), inv) == "invoice"
    with session_scope() as session:
        row = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == "sub_first"))
        assert row is not None and row.entitlement == "pro" and str(row.identity_id) == identity["sub"]
        pay = session.scalar(select(Payment).where(Payment.stripe_invoice_id == "in_first"))
        assert pay is not None and pay.kind == "invoice" and pay.subscription_id == row.id
    # a later subscription.created event is a no-op upsert, not a duplicate row
    assert post_event(client, "customer.subscription.created", sub, created=now + 1).status_code == 200
    with session_scope() as session:
        assert session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == "sub_first").with_only_columns(Subscription.id)) is not None


def test_invoice_refund_matches_by_invoice_id(client):
    """A refund of a subscription invoice carries the invoice id but no payment
    intent we stored (current API versions drop invoice.payment_intent)."""
    set_webhook("retro")
    identity = session_cookie(client, make_identity())
    now = int(time.time())
    assert post_event(client, "customer.subscription.created", sub_object("sub_r", identity["sub"], now=now), created=now).status_code == 200
    inv = {"id": "in_r", "object": "invoice", "amount_paid": 500, "currency": "usd", "customer_email": identity["email"],
           "parent": {"subscription_details": {"subscription": "sub_r"}}, "billing_reason": "subscription_create"}
    assert post_event(client, "invoice.paid", inv, created=now + 1).get_json() == {"status": "invoice"}
    charge = {"id": "ch_r", "object": "charge", "invoice": "in_r", "payment_intent": "pi_r", "amount": 500, "amount_refunded": 500, "refunded": True}
    assert post_event(client, "charge.refunded", charge, created=now + 2).get_json() == {"status": "refunded"}
    with session_scope() as session:
        pay = session.scalar(select(Payment).where(Payment.stripe_invoice_id == "in_r"))
        assert pay.status == "refunded" and pay.amount_refunded == 500 and pay.stripe_charge_id == "ch_r" and pay.stripe_payment_intent_id == "pi_r"


def test_portal_cancel_at_marks_cancel_at_period_end(client):
    """The Customer Portal cancels with ``cancel_at`` set and
    ``cancel_at_period_end`` false; we treat it as cancel-at-period-end."""
    set_webhook("retro")
    identity = session_cookie(client, make_identity())
    assert client.get("/api/me").status_code == 200  # mirrors the customer (email) from the claims
    now = int(time.time())
    sub = sub_object("sub_ca", identity["sub"], now=now)
    assert post_event(client, "customer.subscription.created", sub, created=now).status_code == 200
    sub2 = dict(sub, cancel_at=now + 20 * 86400, canceled_at=now, cancel_at_period_end=False)
    assert post_event(client, "customer.subscription.updated", sub2, created=now + 1).status_code == 200
    ent = client.get("/api/entitlements?app=retro").get_json()
    assert ent["entitlements"] == ["pro"]
    assert ent["subscription"]["status"] == "active" and ent["subscription"]["cancel_at_period_end"] is True
    assert [m["template"] for m in outbox_rows(kind="email")][-1] == "subscription_cancelled"
