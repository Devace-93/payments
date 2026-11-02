"""Session endpoints (/api/me, /api/claim, /api/portal, /api/entitlements) and
the service endpoints (/api/v1/...)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from conftest import app_row, bearer, make_identity, outbox_rows, session_cookie, session_token, set_webhook
from sqlalchemy import select

from dbcore import claims
from dbcore.cli import hash_key
from dbcore.db import session_scope
from dbcore.models import App, ClaimCode, Customer, Payment, Subscription


def test_me_requires_session(client):
    assert client.get("/api/me").get_json()["error"]["code"] == "no_session"
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {session_token(make_identity(), ttl=-7200)}"})
    assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "session_expired"
    resp = client.get("/api/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "invalid_session"


def test_me_upserts_customer_and_badge_links(client):
    identity = session_cookie(client, make_identity(handle="Ana_Dev", currency="eur"))
    resp = client.get("/api/me")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["identity"] == {"id": identity["sub"], "email": identity["email"], "handle": "Ana_Dev", "name": "Ana Test"}
    assert body["customer"] == {"has_stripe_customer": False, "public_supporter": False, "display_name": None, "preferred_currency": "eur"}
    assert body["payments"] == [] and body["subscriptions"] == []
    badge = body["badge"]
    assert badge["svg_url"] == "http://localhost:8086/badge/ana_dev.svg"
    assert badge["json_url"] == "http://localhost:8086/badge/ana_dev.json"
    assert badge["stable_svg_url"] == f"http://localhost:8086/badge/u/{identity['sub']}.svg"
    assert badge["svg_url"] in badge["markdown"] and badge["svg_url"] in badge["html"]
    assert badge["shields_url"].startswith("https://img.shields.io/endpoint?url=http%3A%2F%2Flocalhost%3A8086")
    with session_scope() as session:
        customer = session.get(Customer, uuid.UUID(identity["sub"]))
        assert customer.handle == "ana_dev" and customer.preferred_currency == "eur"
    # bearer beats cookie
    other = make_identity()
    assert client.get("/api/me", headers=bearer(other)).get_json()["identity"]["id"] == other["sub"]


def test_patch_me(client):
    session_cookie(client, make_identity())
    resp = client.patch("/api/me", json={"public_supporter": True, "display_name": "  Ana  ", "preferred_currency": "MXN"})
    assert resp.status_code == 200
    assert resp.get_json()["customer"] == {"has_stripe_customer": False, "public_supporter": True, "display_name": "Ana", "preferred_currency": "mxn"}
    assert client.patch("/api/me", json={"preferred_currency": "gbp"}).get_json()["error"]["code"] == "unsupported_currency"
    assert client.patch("/api/me", json={"public_supporter": "yes"}).get_json()["error"]["code"] == "validation_error"
    assert client.patch("/api/me", json={"display_name": None, "preferred_currency": None}).get_json()["customer"]["display_name"] is None


def _guest_payment(code_kwargs: dict | None = None) -> tuple[uuid.UUID, str]:
    retro = app_row("retro")
    with session_scope() as session:
        payment = Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", email="guest@example.com", public=True)
        session.add(payment)
        session.flush()
        code = claims.issue(session, payment)
        row = session.scalar(select(ClaimCode).where(ClaimCode.payment_id == payment.id))
        for key, value in (code_kwargs or {}).items():
            setattr(row, key, value)
        return payment.id, code


def test_claim_flow(client):
    set_webhook("retro")
    identity = session_cookie(client, make_identity())
    payment_id, code = _guest_payment()
    lax = code.lower().replace("-", " ").replace("0", "o").replace("1", "l")
    resp = client.post("/api/claim", json={"code": lax})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()["payment"]
    assert body["id"] == str(payment_id) and body["app"] == "retro" and body["claimed_at"]
    with session_scope() as session:
        payment = session.get(Payment, payment_id)
        assert str(payment.identity_id) == identity["sub"] and payment.claimed_at is not None
    hooks = outbox_rows(kind="webhook")
    assert len(hooks) == 1 and hooks[0]["event"]["type"] == "payment.claimed"
    assert hooks[0]["event"]["data"]["payment"]["id"] == str(payment_id)
    # used
    resp = client.post("/api/claim", json={"code": code})
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "used_code"
    # badge now says supporter
    me = client.get("/api/me").get_json()
    assert me["payments"][0]["id"] == str(payment_id)


def test_claim_errors(client):
    session_cookie(client, make_identity())
    assert client.post("/api/claim", json={"code": "ABCD-EFGH-JKMN-PQRS"}).get_json()["error"]["code"] == "invalid_code"
    assert client.post("/api/claim", json={"code": "nope"}).get_json()["error"]["code"] == "invalid_code"
    assert client.post("/api/claim", json={}).status_code == 400
    _, expired = _guest_payment({"expires_at": datetime.now(timezone.utc) - timedelta(days=1)})
    resp = client.post("/api/claim", json={"code": expired})
    assert resp.status_code == 410 and resp.get_json()["error"]["code"] == "expired_code"
    _, voided = _guest_payment({"voided_at": datetime.now(timezone.utc)})
    assert client.post("/api/claim", json={"code": voided}).get_json()["error"]["code"] == "invalid_code"
    assert client.post("/api/claim", json={"code": expired}, headers={"Authorization": "Bearer "}).status_code in (401, 410)


def test_claim_rate_limit_key_uses_identity(app):
    from api.extensions import identity_key

    identity = make_identity()
    with app.test_request_context("/api/claim", headers={"Authorization": f"Bearer {session_token(identity)}", "X-Forwarded-For": "1.2.3.4"}):
        assert identity_key() == f"identity:{identity['sub']}"
    with app.test_request_context("/api/claim", headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}):
        assert identity_key() == "1.2.3.4"


def test_claim_code_helpers():
    code = claims.generate()
    assert len(code) == 19
    norm = claims.normalise(code)
    assert len(norm) == 16 and claims.normalise(code.lower()) == norm
    assert claims.normalise("OIL0-1lo0-ABCD-EFGH") == "0110-1100-ABCD-EFGH".replace("-", "")
    assert claims.normalise("UUUU-UUUU-UUUU-UUUU") is None  # U is not Crockford
    assert claims.normalise("short") is None and claims.normalise(None) is None


def test_portal(client, fake_stripe):
    identity = session_cookie(client, make_identity())
    resp = client.post("/api/portal", json={})
    assert resp.status_code == 404 and resp.get_json()["error"]["code"] == "no_customer"
    assert client.get("/api/me").status_code == 200  # creates the mirror row
    with session_scope() as session:
        session.get(Customer, uuid.UUID(identity["sub"])).stripe_customer_id = "cus_p"
    resp = client.post("/api/portal", json={"return_to": "https://retro.3m4.net/billing"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["url"].startswith("http://localhost:8086/me?portal=")
    params = fake_stripe.billing_portal.sessions.calls[-1]["params"]
    assert params == {"customer": "cus_p", "return_url": "https://retro.3m4.net/billing"}
    resp = client.post("/api/portal", json={"return_to": "https://evil.example/"})
    assert fake_stripe.billing_portal.sessions.calls[-1]["params"]["return_url"] == "http://localhost:8086/me"


def test_portal_gated_by_subscriptions_flag(client, monkeypatch):
    session_cookie(client, make_identity())
    monkeypatch.setenv("FEATURE_FLAG_OVERRIDES", "subscriptions=off")
    assert client.post("/api/portal", json={}).status_code == 403


def test_entitlements_unknown_app(client):
    session_cookie(client, make_identity())
    assert client.get("/api/entitlements?app=zzz").get_json()["error"]["code"] == "unknown_app"
    assert client.get("/api/entitlements").get_json()["error"]["code"] == "unknown_app"


# --------------------------------------------------------------------------- #
# service endpoints
# --------------------------------------------------------------------------- #
def _service_key(slug: str) -> str:
    key = f"m4pay_sk_{slug}_" + "x" * 30
    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == slug))
        app.service_key_hash = hash_key(key)
    return key


def test_service_entitlements_scoping(client):
    key = _service_key("retro")
    identity = make_identity()
    uid = uuid.UUID(identity["sub"])
    retro = app_row("retro")
    with session_scope() as session:
        session.add(Customer(identity_id=uid, email=identity["email"]))
        session.add(Subscription(stripe_subscription_id="sub_s", identity_id=uid, app_id=retro.id, entitlement="pro", status="trialing"))
    headers = {"Authorization": f"Bearer {key}"}
    resp = client.get(f"/api/v1/entitlements/{uid}?app=retro", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["entitlements"] == ["pro"] and body["subscription"]["status"] == "trialing" and body["app"] == "retro"
    assert client.get(f"/api/v1/entitlements/{uuid.uuid4()}?app=retro", headers=headers).get_json()["entitlements"] == []
    resp = client.get(f"/api/v1/entitlements/{uid}?app=info", headers=headers)
    assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "forbidden"
    assert client.get(f"/api/v1/entitlements/{uid}?app=retro").status_code == 401
    assert client.get(f"/api/v1/entitlements/{uid}?app=retro", headers={"Authorization": "Bearer m4pay_sk_wrong"}).status_code == 401
    assert client.get("/api/v1/entitlements/notauuid?app=retro", headers=headers).status_code == 400
    # a session token on the service endpoint is not a service key
    assert client.get(f"/api/v1/entitlements/{uid}?app=retro", headers=bearer(identity)).status_code == 401

    # listing
    resp = client.get("/api/v1/subscriptions?app=retro", headers=headers)
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1 and items[0]["identity_id"] == str(uid) and items[0]["email"] == identity["email"]
    assert items[0]["entitlements"] == ["pro"] and resp.get_json()["next_cursor"] is None
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert client.get(f"/api/v1/subscriptions?app=retro&updated_since={future}", headers=headers).get_json()["items"] == []
    assert client.get("/api/v1/subscriptions?app=retro&updated_since=bad", headers=headers).status_code == 400
    assert client.get("/api/v1/subscriptions?app=info", headers=headers).status_code == 403


def test_m4pay_client_against_app(client):
    """The relying-party client talks to the API through a requests shim."""
    import m4pay

    key = _service_key("retro")
    uid = uuid.uuid4()

    class _Resp:
        def __init__(self, r):
            self.status_code = r.status_code
            self._json = r.get_json()
            self.text = r.get_data(as_text=True)

        def json(self):
            return self._json

    class _Http:
        def get(self, url, params=None, headers=None, timeout=None):
            path = url.replace("http://api.test", "")
            return _Resp(client.get(path, query_string=params, headers=headers))

    api = m4pay.M4PayClient("http://api.test", app="retro", service_key=key, session=_Http())
    assert api.entitlements(str(uid))["entitlements"] == []
    assert list(api.subscriptions()) == []
    other = m4pay.M4PayClient("http://api.test", app="info", service_key=key, session=_Http())
    try:
        other.entitlements(str(uid))
    except m4pay.M4PayError as err:
        assert err.status == 403 and err.code == "forbidden"
    else:  # pragma: no cover
        raise AssertionError("expected M4PayError")

    # the Flask gate
    from flask import Flask, g

    gate = m4pay.flask_require_entitlement("pro", client=api, cache_ttl=60, on_error=lambda s, c, m: RuntimeError(f"{s}:{c}"))

    @gate
    def view():
        return "ok"

    probe = Flask("probe")
    with probe.test_request_context("/"):
        g.identity = {"sub": str(uid)}
        try:
            view()
        except RuntimeError as err:
            assert str(err) == "402:entitlement_required"
        retro = app_row("retro")
        with session_scope() as session:
            session.add(Subscription(stripe_subscription_id="sub_g", identity_id=uid, app_id=retro.id, entitlement="pro", status="active"))
        # cached miss for cache_ttl seconds, then granted
        try:
            view()
        except RuntimeError:
            pass
        gate2 = m4pay.flask_require_entitlement("pro", client=api, cache_ttl=0, on_error=lambda s, c, m: RuntimeError(c))
        assert gate2(lambda: "ok")() == "ok"
