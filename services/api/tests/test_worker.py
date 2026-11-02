"""Outbox worker: webhook delivery + signature round trip with m4pay, mail
rendering."""
from __future__ import annotations

import json
import time
import uuid

import m4pay
import pytest
import requests
from conftest import app_row, outbox_rows, set_webhook

from dbcore import worker
from dbcore.db import session_scope
from dbcore.mail_templates import fmt_amount, pick_lang, render
from dbcore.models import App, Outbox
from dbcore.outbox import enqueue_mail, enqueue_webhook


def _queue_webhook(slug="retro") -> dict:
    with session_scope() as session:
        app = session.get(App, app_row(slug).id)
        job = enqueue_webhook(
            session,
            app=app,
            event={"type": "subscription.updated", "identity_id": str(uuid.uuid4()), "email": "a@b.c", "data": {"entitlements": ["pro"], "subscription": None, "payment": None, "updated_at": "2026-11-01T00:00:00Z"}},
        )
        session.flush()
        return {"id": job.id, "event": dict(job.payload["event"])}


def test_enqueue_webhook_noop_without_url(client):
    with session_scope() as session:
        app = session.get(App, app_row("retro").id)
        assert enqueue_webhook(session, app=app, event={"type": "x", "data": {}}) is None
    assert outbox_rows(kind="webhook") == []


def test_process_webhook_success_and_verify_round_trip(client, monkeypatch):
    set_webhook("retro", url="https://retro.example/hook", secret="whsec_round")
    queued = _queue_webhook()
    captured: dict = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update(url=url, data=data, headers=headers, timeout=timeout)
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    counts = worker.drain()
    assert counts == {"sent": 1}
    assert captured["url"] == "https://retro.example/hook" and captured["timeout"] == 10
    headers = captured["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["X-M4Pay-Event-Id"] == queued["event"]["id"]
    assert headers["X-M4Pay-Signature"].startswith("v1=")
    # the relying-party verifier accepts exactly what the worker signed
    event = m4pay.verify_webhook("whsec_round", captured["data"], headers)
    assert event["type"] == "subscription.updated" and event["app"] == "retro" and event["data"]["entitlements"] == ["pro"]
    assert json.loads(captured["data"]) == queued["event"]
    with pytest.raises(m4pay.WebhookError):
        m4pay.verify_webhook("other", captured["data"], headers)
    with pytest.raises(m4pay.WebhookError):
        m4pay.verify_webhook("whsec_round", captured["data"] + b" ", headers)
    stale = dict(headers, **{"X-M4Pay-Timestamp": str(int(time.time()) - 1000)})
    with pytest.raises(m4pay.WebhookError):
        m4pay.verify_webhook("whsec_round", captured["data"], stale)
    lower = {k.lower(): v for k, v in headers.items()}
    assert m4pay.verify_webhook("whsec_round", captured["data"], lower)["id"] == queued["event"]["id"]
    with session_scope() as session:
        job = session.get(Outbox, queued["id"])
        assert job.status == "sent" and job.sent_at is not None and job.attempts == 1


def test_process_webhook_failure_retries(client, monkeypatch):
    set_webhook("retro")
    queued = _queue_webhook()

    class _Bad:
        status_code = 500
        text = "boom"

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Bad())
    assert worker.drain() == {"retry": 1}
    with session_scope() as session:
        job = session.get(Outbox, queued["id"])
        assert job.status == "pending" and "HTTP 500" in job.last_error and job.attempts == 1
        assert job.next_attempt_at > job.created_at
        job.next_attempt_at = job.created_at  # make it due again
        job.attempts = worker.MAX_ATTEMPTS - 1

    def raise_timeout(*a, **k):
        raise requests.ConnectTimeout("slow")

    monkeypatch.setattr(requests, "post", raise_timeout)
    assert worker.drain() == {"failed": 1}
    with session_scope() as session:
        assert session.get(Outbox, queued["id"]).status == "failed"


def test_webhook_without_secret_is_skipped(client, monkeypatch):
    set_webhook("retro", url="https://retro.example/hook", secret="whsec_tmp")
    _queue_webhook()
    with session_scope() as session:
        session.get(App, app_row("retro").id).webhook_secret = None
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("must not post"))
    assert worker.drain() == {"skipped": 1}


def test_flask_webhook_view_round_trip(client, monkeypatch):
    from flask import Flask

    set_webhook("retro", url="https://retro.example/hook", secret="whsec_flask")
    _queue_webhook()
    seen: list[dict] = []
    receiver = Flask("receiver")
    receiver.add_url_rule("/hook", view_func=m4pay.flask_webhook_view("whsec_flask", lambda ev: seen.append(ev) or "stored"), methods=["POST"])
    rc = receiver.test_client()

    class _Resp:
        def __init__(self, r):
            self.status_code = r.status_code
            self.text = r.get_data(as_text=True)

    monkeypatch.setattr(requests, "post", lambda url, data=None, headers=None, timeout=None: _Resp(rc.post("/hook", data=data, headers=headers)))
    assert worker.drain() == {"sent": 1}
    assert len(seen) == 1 and seen[0]["type"] == "subscription.updated"
    bad = rc.post("/hook", data=b"{}", headers={"X-M4Pay-Timestamp": "1", "X-M4Pay-Signature": "v1=00"})
    assert bad.status_code == 400


def test_process_email_renders_params(client, monkeypatch):
    with session_scope() as session:
        enqueue_mail(session, template="donation_receipt", to="x@example.com", lang="es", params={"amount": 500, "currency": "usd", "app_name": "Retro", "code": "ABCD-EFGH-JKMN-PQRS"})
    monkeypatch.setattr(worker, "mail_is_enabled", lambda: True)
    sent: dict = {}

    def fake_send(*, to, subject, text, html):
        sent.update(to=to, subject=subject, text=text, html=html)
        return "sent"

    monkeypatch.setattr(worker, "send_mail", fake_send)
    assert worker.drain() == {"sent": 1}
    assert sent["to"] == ["x@example.com"]
    assert sent["subject"] == "Gracias por apoyar a Retro"
    assert "ABCD-EFGH-JKMN-PQRS" in sent["text"] and "$5.00 USD" in sent["text"]
    assert "http://localhost:8086/claim?code=ABCD-EFGH-JKMN-PQRS" in sent["html"]


def test_mail_disabled_skips(client):
    with session_scope() as session:
        enqueue_mail(session, template="payment_failed", to="x@example.com", params={"app_name": "Retro", "label": "Pro"})
    assert worker.drain() == {"skipped": 1}


def test_templates_and_amounts():
    assert fmt_amount(500, "usd") == "$5.00 USD"
    assert fmt_amount(10000, "mxn") == "MX$100.00"
    assert fmt_amount(500, "eur") == "€5.00"
    assert fmt_amount(1234567, "gbp") == "£12,345.67"
    assert fmt_amount(None, None) == "0.00"
    assert pick_lang("es-MX,en;q=0.8") == "es" and pick_lang("fr", None) == "en"
    for template, params in (
        ("donation_receipt", {"amount": 300, "currency": "eur", "app_name": "3m4"}),
        ("subscription_started", {"app_name": "Retro", "label": "Pro", "amount": 9900, "currency": "mxn", "interval": "month", "period_end": "2026-12-01"}),
        ("subscription_cancelled", {"app_name": "Retro", "label": "Pro", "period_end": "2026-12-01"}),
        ("payment_failed", {"app_name": "Retro", "label": "Pro"}),
    ):
        for lang in ("en", "es", "de"):
            subject, text, html = render(template, lang=lang, to="a@b.c", params=params)
            assert subject and "http://localhost:8086/" in text and "<a href" in html
    subject, text, _ = render("subscription_started", lang="en", to="a@b.c", params={"app_name": "Retro", "label": "Pro", "amount": 9900, "currency": "mxn", "interval": "month", "period_end": "2026-12-01"})
    assert subject == "Your Retro Pro subscription is active" and "MX$99.00 per month" in text
    _, text, _ = render("payment_failed", lang="es", to="a@b.c", params={"app_name": "Retro", "label": "Pro"})
    assert "/me?portal=1" in text
    with pytest.raises(ValueError):
        render("nope", lang="en", to="a@b.c")
