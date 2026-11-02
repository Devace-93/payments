"""Badges (tiers, headers, shields JSON) and the public supporters list."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from conftest import app_row, make_identity, session_cookie

from dbcore.db import session_scope
from dbcore.models import Customer, Payment, Subscription


def _customer(handle="ana", public=True, display_name=None) -> uuid.UUID:
    uid = uuid.uuid4()
    with session_scope() as session:
        session.add(Customer(identity_id=uid, handle=handle, email=f"{handle}@example.com", public_supporter=public, display_name=display_name))
    return uid


def test_unknown_badge_is_grey_and_cacheable(client):
    resp = client.get("/badge/nobody.svg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/svg+xml"
    assert resp.headers["Cache-Control"] == "public, max-age=3600"
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert resp.headers["ETag"]
    svg = resp.get_data(as_text=True)
    assert "not a supporter" in svg and "#9f9f9f" in svg and 'height="20"' in svg and ">3m4<" in svg
    etag = resp.headers["ETag"]
    assert client.get("/badge/nobody.svg", headers={"If-None-Match": etag}).status_code == 304
    body = client.get("/badge/nobody.json").get_json()
    assert body == {"schemaVersion": 1, "label": "3m4", "message": "not a supporter", "color": "9f9f9f"}
    assert client.get(f"/badge/u/{uuid.uuid4()}.svg").status_code == 200
    assert client.get("/badge/u/not-a-uuid.json").get_json()["message"] == "not a supporter"


def test_badge_tiers(client):
    retro = app_row("retro")
    supporter = _customer("supp")
    pro = _customer("pro")
    team = _customer("team")
    cancelled_pro = _customer("expro")
    with session_scope() as session:
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=supporter, status="paid"))
        session.add(Subscription(stripe_subscription_id="s1", identity_id=pro, app_id=retro.id, entitlement="pro", status="active"))
        session.add(Subscription(stripe_subscription_id="s2", identity_id=team, app_id=retro.id, entitlement="team", status="past_due"))
        session.add(Subscription(stripe_subscription_id="s3", identity_id=pro, app_id=retro.id, entitlement="team", status="canceled",
                                 current_period_end=datetime.now(timezone.utc) - timedelta(days=1)))
        session.add(Subscription(stripe_subscription_id="s4", identity_id=cancelled_pro, app_id=retro.id, entitlement="pro", status="active",
                                 cancel_at_period_end=True, current_period_end=datetime.now(timezone.utc) + timedelta(days=3)))
    assert client.get("/badge/supp.json").get_json()["message"] == "supporter"
    assert client.get("/badge/pro.json").get_json()["message"] == "pro"
    assert client.get("/badge/team.json").get_json()["message"] == "team"
    assert client.get("/badge/expro.json").get_json()["message"] == "pro"
    # cancelled immediately: Stripe keeps current_period_end in the future, but access ended
    cancelled_now = _customer("cxnow")
    with session_scope() as session:
        session.add(Subscription(stripe_subscription_id="s5", identity_id=cancelled_now, app_id=retro.id, entitlement="pro", status="canceled",
                                 current_period_end=datetime.now(timezone.utc) + timedelta(days=20)))
    assert client.get("/badge/cxnow.json").get_json()["message"] == "not a supporter"
    assert client.get(f"/badge/u/{team}.json").get_json()["color"] == "f59e0b"
    assert "#f59e0b" in client.get("/badge/pro.svg").get_data(as_text=True)
    assert client.get("/badge/SUPP.json").get_json()["message"] == "supporter"
    # refunded payments do not count
    refunded = _customer("refunded")
    with session_scope() as session:
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=refunded, status="refunded"))
    assert client.get("/badge/refunded.json").get_json()["message"] == "not a supporter"


def test_badges_flag_off_serves_grey(client, monkeypatch):
    retro = app_row("retro")
    pro = _customer("flagpro")
    with session_scope() as session:
        session.add(Subscription(stripe_subscription_id="s9", identity_id=pro, app_id=retro.id, entitlement="pro", status="active"))
    assert client.get("/badge/flagpro.json").get_json()["message"] == "pro"
    monkeypatch.setenv("FEATURE_FLAG_OVERRIDES", "badges=off")
    assert client.get("/badge/flagpro.json").get_json()["message"] == "not a supporter"
    session_cookie(client, make_identity(sub=str(pro)))
    assert client.get("/api/me").get_json()["badge"] is None


def test_supporters_only_opted_in(client):
    retro = app_row("retro")
    shown = _customer("shown", public=True, display_name="Ana S.")
    hidden = _customer("hidden", public=False)
    pro = _customer("prouser", public=True)
    with session_scope() as session:
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=shown, status="paid", public=True, message="keep going"))
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=hidden, status="paid", public=True))
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=shown, status="paid", public=False, message="secret"))
        session.add(Payment(app_id=retro.id, kind="donation", amount=300, currency="eur", identity_id=None, status="paid", public=True, display_name="Guest G"))
        session.add(Payment(app_id=retro.id, kind="donation", amount=300, currency="eur", identity_id=None, status="paid", public=False, display_name="Private guest"))
        session.add(Subscription(stripe_subscription_id="s5", identity_id=pro, app_id=retro.id, entitlement="pro", status="active"))
        session.add(Subscription(stripe_subscription_id="s6", identity_id=hidden, app_id=retro.id, entitlement="team", status="active"))
    resp = client.get("/api/public/supporters?app=retro")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "public, max-age=300"
    items = resp.get_json()["items"]
    names = {i["display_name"]: i for i in items}
    assert set(names) == {"Ana S.", "Guest G", "prouser"}
    assert names["Ana S."]["tier"] == "supporter" and names["Ana S."]["handle"] == "shown" and names["Ana S."]["message"] == "keep going"
    assert names["Guest G"]["handle"] is None
    assert names["prouser"]["tier"] == "pro"
    assert items[0]["display_name"] == "prouser"  # higher tiers first
    assert all(len(i["since"]) == 7 for i in items)
    assert client.get("/api/public/supporters?app=retro&limit=1").get_json()["items"][0]["display_name"] == "prouser"
    assert client.get("/api/public/supporters?app=nope").status_code == 400
    assert client.get("/api/public/supporters?app=info").get_json()["items"] == []
