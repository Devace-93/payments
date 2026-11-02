"""Test fixtures: a real Postgres (``TEST_DATABASE_URL``), tables truncated
and the catalog re-synced before every test, rate limits off, mail disabled
(mails stay in the outbox, whose payload carries the claim code the tests
need), fake Stripe (empty ``STRIPE_SECRET_KEY``) and a throwaway Ed25519
JWKS so :func:`session_cookie` can mint sessions the API accepts.

Environment must be set BEFORE ``dbcore`` is imported: its config is frozen
at import time.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT, ROOT / "services" / "api", ROOT / "packages" / "relying-party" / "python"):
    sys.path.insert(0, str(p))

_db_url = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://payments:payments@localhost:55432/payments_test"
)
os.environ["DATABASE_URL"] = _db_url
os.environ.setdefault("RATE_LIMITS_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("MAIL_ENABLED", "false")
os.environ.setdefault("ACCOUNTS_URL", "http://localhost:8085")
os.environ.setdefault("ACCOUNTS_INTERNAL_URL", "http://accounts-api-1:5000")
os.environ.setdefault("PAYMENTS_URL", "http://localhost:8086")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")
os.environ["STRIPE_SECRET_KEY"] = ""
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
os.environ["STRIPE_INTEGRATION_IDENTIFIER"] = "3m4-payments-testtest"
os.environ["POSTHOG_API_KEY"] = ""
os.environ["FEATURE_FLAG_OVERRIDES"] = ""
os.environ["GEOIP_DB_PATH"] = "/nonexistent/GeoLite2-Country.mmdb"
os.environ.pop("ALLOWED_ORIGINS", None)
for var in ("CURRENCIES", "DEFAULT_CURRENCY", "MIN_NET_RATIO", "ISR_RATE", "FX_RATES_MXN", "DONATION_MAX_CENTS", "CLAIM_CODE_TTL_DAYS"):
    os.environ.pop(var, None)

import jwt
import pytest
from api.app import create_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, text

from dbcore import m4session, models, stripe_client
from dbcore.catalog import sync_catalog
from dbcore.config import config
from dbcore.db import Base, engine, session_scope
from dbcore.models import Outbox

TABLES = (
    "outbox",
    "stripe_events",
    "claim_codes",
    "payments",
    "checkout_sessions",
    "subscriptions",
    "customers",
    "products",
    "apps",
)

# --- fake accounts JWKS --------------------------------------------------- #
_PRIVATE = Ed25519PrivateKey.generate()
_PUBLIC = _PRIVATE.public_key()
KID = "test-kid"
JWKS_URL = f"{config.accounts_internal_url}/.well-known/jwks.json"
_PEM = _PRIVATE.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
)


def _install_jwks() -> None:
    """Pre-populate m4session's cache so it never fetches."""
    m4session._cache._keys[JWKS_URL] = {"fetched": time.time() + 10**9, "keys": {KID: _PUBLIC}}


def make_identity(**overrides) -> dict:
    sub = overrides.pop("sub", None) or str(uuid.uuid4())
    identity = {
        "sub": sub,
        "sid": str(uuid.uuid4()),
        "email": f"{sub[:8]}@example.com",
        "email_verified": True,
        "handle": f"user{sub[:6]}",
        "name": "Ana Test",
        "avatar_url": f"{config.accounts_url}/avatars/{sub}",
    }
    identity.update(overrides)
    return identity


def session_token(identity: dict, *, ttl: int = 900) -> str:
    now = int(time.time())
    claims = {**identity, "iat": now, "exp": now + ttl, "iss": config.accounts_url, "aud": "3m4"}
    return jwt.encode(claims, _PEM, algorithm="EdDSA", headers={"kid": KID})


def session_cookie(client, identity: dict) -> dict:
    """Set the ``3m4_session`` cookie on ``client`` and return the identity."""
    client.set_cookie(m4session.COOKIE_NAME, session_token(identity), domain="localhost")
    return identity


def bearer(identity: dict) -> dict:
    return {"Authorization": f"Bearer {session_token(identity)}"}


# --- Stripe signatures ---------------------------------------------------- #
def signed_event(event: dict, *, secret: str | None = None, timestamp: int | None = None) -> tuple[bytes, dict]:
    """``(body, headers)`` with a real ``Stripe-Signature`` for the payload."""
    secret = secret or config.stripe_webhook_secret
    body = json.dumps(event).encode()
    ts = timestamp or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={ts},v1={mac}", "Content-Type": "application/json"}


def stripe_event(event_type: str, obj: dict, *, event_id: str | None = None, created: int | None = None) -> dict:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "object": "event",
        "type": event_type,
        "created": created or int(time.time()),
        "livemode": False,
        "data": {"object": obj},
    }


def post_event(client, event_type: str, obj: dict, **kwargs):
    body, headers = signed_event(stripe_event(event_type, obj, **kwargs))
    return client.post("/api/stripe/webhook", data=body, headers=headers)


# --- fixtures ------------------------------------------------------------- #
@pytest.fixture(scope="session")
def app():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _install_jwks()
    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def client(app):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    stripe_client.reset()
    with session_scope() as session:
        sync_catalog(session, stripe_client.client())
    return app.test_client()


@pytest.fixture
def fake_stripe(client):
    return stripe_client.client()


def outbox_rows(kind: str | None = None, template: str | None = None) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(Outbox).order_by(Outbox.created_at)).all()
        out = []
        for r in rows:
            if kind is not None and r.kind != kind:
                continue
            if template is not None and r.payload.get("template") != template:
                continue
            out.append({"id": r.id, "kind": r.kind, "app_id": r.app_id, "status": r.status, **dict(r.payload)})
        return out


def app_row(slug: str):
    with session_scope() as session:
        app = session.scalar(select(models.App).where(models.App.slug == slug))
        session.expunge(app)
        return app


def set_webhook(slug: str, url: str = "https://retro.example/api/billing/webhook", secret: str = "whsec_retro") -> None:
    with session_scope() as session:
        app = session.scalar(select(models.App).where(models.App.slug == slug))
        app.webhook_url = url
        app.webhook_secret = secret


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
