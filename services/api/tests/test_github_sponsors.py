"""GitHub Sponsors webhook (``POST /api/github/sponsors``) and its effect on
the public supporters list."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from conftest import app_row

from dbcore.db import session_scope
from dbcore.models import GithubEvent, GithubSponsor, Payment

SECRET = "ghsec_test_secret"


def _sponsorship(login="octocat", *, privacy="public", one_time=False, name="The Octocat", cents=500, created="2026-11-02T10:00:00Z"):
    return {
        "sponsor": {"login": login, "node_id": f"U_{login}", "name": name, "avatar_url": f"https://avatars.githubusercontent.com/{login}", "html_url": f"https://github.com/{login}"},
        "sponsorable": {"login": "Devace-93"},
        "tier": {"node_id": "T_1", "name": f"${cents / 100:.0f} a month", "monthly_price_in_cents": cents, "monthly_price_in_dollars": cents // 100, "is_one_time": one_time},
        "privacy_level": privacy,
        "created_at": created,
    }


def post(client, action, sponsorship, *, event="sponsorship", delivery=None, secret=SECRET, headers=None):
    body = json.dumps({"action": action, "sponsorship": sponsorship, "sender": sponsorship.get("sponsor")}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    h = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery or str(uuid.uuid4()),
        "X-Hub-Signature-256": sig,
    }
    h.update(headers or {})
    return client.post("/api/github/sponsors", data=body, headers=h)


def supporters(client, app="info"):
    return client.get(f"/api/public/supporters?app={app}").get_json()["items"]


def test_bad_signature_rejected(client):
    assert post(client, "created", _sponsorship(), secret="wrong").status_code == 400
    assert client.post("/api/github/sponsors", data=b"{}", headers={"Content-Type": "application/json"}).status_code == 400
    assert supporters(client) == []


def test_ping_and_unknown_events(client):
    assert post(client, "", {}, event="ping").get_json()["status"] == "pong"
    assert post(client, "created", _sponsorship(), event="star").get_json()["status"] == "ignored"
    assert supporters(client) == []


def test_created_public_sponsor_listed_on_every_app(client):
    resp = post(client, "created", _sponsorship())
    assert resp.status_code == 200 and resp.get_json()["status"] == "processed"
    for app in ("info", "retro", "all"):
        items = supporters(client, app)
        assert len(items) == 1
        row = items[0]
        assert row["display_name"] == "The Octocat" and row["handle"] == "octocat" and row["tier"] == "supporter"
        assert row["source"] == "github" and row["url"] == "https://github.com/octocat" and row["avatar_url"].endswith("/octocat")
        assert row["since"] == "2026-11"
    with session_scope() as session:
        s = session.scalar(__import__("sqlalchemy").select(GithubSponsor))
        assert s.monthly_cents == 500 and s.status == "active" and s.privacy_level == "public" and not s.one_time


def test_private_sponsor_hidden_until_made_public(client):
    post(client, "created", _sponsorship(privacy="private"))
    assert supporters(client) == []
    post(client, "edited", _sponsorship(privacy="public", name="Octo Public"))
    assert [i["display_name"] for i in supporters(client)] == ["Octo Public"]


def test_cancelled_monthly_sponsor_removed_one_time_kept(client):
    post(client, "created", _sponsorship("monthly"))
    post(client, "created", _sponsorship("once", one_time=True))
    assert {i["handle"] for i in supporters(client)} == {"monthly", "once"}
    post(client, "pending_cancellation", _sponsorship("monthly"))
    assert {i["handle"] for i in supporters(client)} == {"monthly", "once"}
    post(client, "cancelled", _sponsorship("monthly"))
    post(client, "cancelled", _sponsorship("once", one_time=True))
    assert {i["handle"] for i in supporters(client)} == {"once"}
    with session_scope() as session:
        rows = {r.login: r for r in session.query(GithubSponsor).all()}
        assert rows["monthly"].status == "cancelled" and rows["monthly"].ended_at is not None
        assert rows["once"].status == "active"
    # Comes back: active again.
    post(client, "created", _sponsorship("monthly"))
    assert {i["handle"] for i in supporters(client)} == {"monthly", "once"}


def test_cancel_unknown_sponsor_is_ignored(client):
    assert post(client, "cancelled", _sponsorship("ghost")).get_json()["status"] == "ignored"
    with session_scope() as session:
        assert session.query(GithubSponsor).count() == 0


def test_duplicate_delivery(client):
    delivery = str(uuid.uuid4())
    assert post(client, "created", _sponsorship(), delivery=delivery).get_json()["status"] == "processed"
    assert post(client, "created", _sponsorship(), delivery=delivery).get_json()["status"] == "duplicate"
    with session_scope() as session:
        assert session.get(GithubEvent, delivery).status == "processed"
        assert session.query(GithubSponsor).count() == 1


def test_supporters_all_merges_apps_and_github(client):
    retro = app_row("retro")
    exp = app_row("exp")
    with session_scope() as session:
        session.add(Payment(app_id=retro.id, kind="donation", amount=500, currency="usd", identity_id=None, status="paid", public=True, display_name="Retro fan"))
        session.add(Payment(app_id=exp.id, kind="donation", amount=500, currency="usd", identity_id=None, status="paid", public=True, display_name="Exp fan"))
    post(client, "created", _sponsorship())
    assert {i["display_name"] for i in supporters(client, "retro")} == {"Retro fan", "The Octocat"}
    assert {i["display_name"] for i in supporters(client, "exp")} == {"Exp fan", "The Octocat"}
    assert {i["display_name"] for i in supporters(client, "all")} == {"Retro fan", "Exp fan", "The Octocat"}
    stripe_row = next(i for i in supporters(client, "retro") if i["display_name"] == "Retro fan")
    assert stripe_row["source"] == "stripe" and stripe_row["url"] is None
