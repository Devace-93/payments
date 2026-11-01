"""Test fixtures: a real Postgres (``TEST_DATABASE_URL``), tables truncated
before every test, rate limits off, mail disabled (mails stay in the outbox,
whose payload carries the plaintext token the tests need).

Environment must be set BEFORE ``dbcore`` is imported: its config is frozen
at import time.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT, ROOT / "services" / "api", ROOT / "packages" / "relying-party" / "python"):
    sys.path.insert(0, str(p))

_db_url = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://postgres:test@localhost:55432/accounts_test"
)
os.environ["DATABASE_URL"] = _db_url
os.environ.setdefault("RATE_LIMITS_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("MAIL_ENABLED", "false")
os.environ.setdefault("ACCOUNTS_URL", "http://localhost:8085")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("COOKIE_DOMAIN", "")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("IP_HASH_SECRET", "test-ip-hash")
os.environ.setdefault("SESSION_SIGNING_KEY", base64.urlsafe_b64encode(b"\x01" * 32).rstrip(b"=").decode())
os.environ["POSTHOG_API_KEY"] = ""
os.environ["FEATURE_FLAG_OVERRIDES"] = ""
os.environ.pop("ALLOWED_ORIGINS", None)
for var in list(os.environ):
    if var.startswith("OAUTH_") and var.endswith(("_CLIENT_ID", "_CLIENT_SECRET")):
        os.environ.pop(var)

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from api.app import create_app  # noqa: E402
from dbcore import models  # noqa: E402,F401
from dbcore.db import Base, engine, session_scope  # noqa: E402
from dbcore.models import Outbox  # noqa: E402

TABLES = ("outbox", "avatars", "email_tokens", "sessions", "identities", "users")


@pytest.fixture(scope="session")
def app():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def client(app):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    return app.test_client()


@pytest.fixture
def signup(client):
    def _signup(email="ana@example.com", password="correct horse battery", c=None, **extra):
        c = c or client
        resp = c.post("/api/auth/signup", json={"email": email, "password": password, **extra})
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["user"]

    return _signup


def outbox_rows(template: str | None = None) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(Outbox).order_by(Outbox.created_at)).all()
        return [dict(r.payload) | {"status": r.status} for r in rows if template is None or r.payload.get("template") == template]


@pytest.fixture
def latest_token():
    def _latest(template: str) -> str:
        rows = outbox_rows(template)
        assert rows, f"no {template} mail queued"
        return rows[-1]["token"]

    return _latest


def cookie(client, name: str, path: str = "/"):
    return client.get_cookie(name, path=path)
