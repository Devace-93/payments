"""Tiny management CLI used by the `migrate` compose service (and cron).

    python -m dbcore.cli upgrade              # create_all + alembic upgrade head
    python -m dbcore.cli migrate              # alembic upgrade head only
    python -m dbcore.cli create-all           # SQLAlchemy create_all only
    python -m dbcore.cli sync-catalog         # catalog.json → apps/products (+ Stripe price ids)
    python -m dbcore.cli create-prices        # create the missing Stripe products/prices
    python -m dbcore.cli app-key <slug> [webhook_url]   # new service key + webhook secret (printed once)
    python -m dbcore.cli seed-completed <cs_id>         # fake-mode: run the checkout.session.completed path
    python -m dbcore.cli prune                # old outbox rows, stale checkouts/events, dead claim codes
    python -m dbcore.cli geoip-update         # download GeoLite2-Country (MAXMIND_LICENSE_KEY)

Schema lifecycle: ``create_all`` bootstraps a fresh database in one shot, then
Alembic (``db/migrations``) evolves it. Migrations are written idempotently so
the two can run back to back on both fresh and existing databases.
"""
from __future__ import annotations

import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, or_, select

from . import models  # noqa: F401  (register models on Base.metadata)
from .db import Base, engine, session_scope

SERVICE_KEY_PREFIX = "m4pay_sk_"


def create_all() -> None:
    Base.metadata.create_all(engine)
    print("✓ tables ensured")


def _db_dir() -> Path:
    for candidate in (Path(__file__).resolve().parents[1] / "db", Path("/app/db")):
        if (candidate / "alembic.ini").is_file():
            return candidate
    raise FileNotFoundError("db/alembic.ini not found")


def migrate() -> None:
    """``alembic upgrade head`` via the Python API (no CLI/cwd assumptions)."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    db_dir = _db_dir()
    cfg = AlembicConfig(str(db_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(db_dir / "migrations"))
    command.upgrade(cfg, "head")
    print("✓ migrations applied")


def sync_catalog() -> None:
    from .catalog import sync_catalog as _sync
    from .stripe_client import client, is_fake

    stripe = client()
    with session_scope() as session:
        counts = _sync(session, stripe)
    mode = "fake price ids" if is_fake(stripe) else "Stripe lookup keys"
    print(f"✓ catalog synced: {counts['apps']} app(s), {counts['products']} product(s) ({mode})")


def create_prices() -> None:
    from .catalog import create_prices as _create
    from .stripe_client import client, is_fake

    stripe = client()
    if is_fake(stripe):
        print("STRIPE_SECRET_KEY is empty: nothing to create (fake Stripe)")
        return
    created = _create(stripe)
    print(f"✓ created {len(created)} price(s): {', '.join(created) or 'none missing'}")


def generate_service_key() -> str:
    """``m4pay_sk_`` + 40 url-safe chars."""
    return SERVICE_KEY_PREFIX + secrets.token_urlsafe(30)[:40]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def app_key(slug: str, webhook_url: str | None = None) -> None:
    """Rotate the service key and webhook secret of an app; print both once."""
    from .models import App

    key = generate_service_key()
    secret = "whsec_m4pay_" + secrets.token_hex(24)
    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == slug))
        if app is None:
            raise SystemExit(f"unknown app {slug!r} (run sync-catalog first)")
        app.service_key_hash = hash_key(key)
        app.webhook_secret = secret
        if webhook_url is not None:
            app.webhook_url = webhook_url.strip() or None
        url = app.webhook_url
    print(f"app:            {slug}")
    print(f"service key:    {key}")
    print(f"webhook secret: {secret}")
    print(f"webhook url:    {url or '(none: push disabled)'}")
    print("Store them in the app's .env now: they are not shown again.")


def _stripe_events_module():
    """``api.stripe_events`` (the webhook handlers live in the API package;
    importable as ``api`` in the image and from ``services/api`` locally)."""
    try:
        from api import stripe_events
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
        from api import stripe_events
    return stripe_events


def seed_completed(cs_id: str) -> None:
    """Fake-mode helper: run the ``checkout.session.completed`` handler for
    one of our sessions as if Stripe had delivered it."""
    from .stripe_client import client, synthesize_completed_session

    obj = synthesize_completed_session(cs_id)
    if obj is None:
        raise SystemExit(f"no checkout session with stripe id {cs_id!r}")
    handlers = _stripe_events_module()
    with session_scope() as session:
        outcome = handlers.handle_event(session, client(), "checkout.session.completed", obj)
    print(f"✓ {cs_id}: {outcome}")


def prune(days: int = 7) -> None:
    """Delete finished outbox rows, abandoned/expired checkout sessions,
    processed Stripe events and dead claim codes older than ``days``
    (checkouts/events use 30 days)."""
    from .models import CheckoutSession, ClaimCode, Outbox, StripeEvent

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    month = now - timedelta(days=30)
    with session_scope() as session:
        outbox = session.execute(
            delete(Outbox).where(Outbox.status.in_(("sent", "skipped", "failed")), Outbox.created_at < cutoff)
        ).rowcount
        checkouts = session.execute(
            delete(CheckoutSession).where(
                CheckoutSession.status.in_(("created", "open", "expired")), CheckoutSession.created_at < month
            )
        ).rowcount
        events = session.execute(delete(StripeEvent).where(StripeEvent.received_at < month)).rowcount
        codes = session.execute(
            delete(ClaimCode).where(
                or_(ClaimCode.expires_at < cutoff, ClaimCode.used_at < cutoff, ClaimCode.voided_at < cutoff)
            )
        ).rowcount
    print(
        f"✓ pruned {outbox or 0} outbox row(s), {checkouts or 0} checkout(s), "
        f"{events or 0} stripe event(s), {codes or 0} claim code(s)"
    )


def geoip_update() -> None:
    from .geo import update_database

    path = update_database()
    print(f"✓ GeoLite2-Country written to {path}")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "upgrade"
    args = argv[2:]
    if cmd == "upgrade":
        create_all()
        migrate()
    elif cmd == "migrate":
        migrate()
    elif cmd == "create-all":
        create_all()
    elif cmd == "sync-catalog":
        sync_catalog()
    elif cmd == "create-prices":
        create_prices()
    elif cmd == "app-key":
        if not args:
            print("usage: app-key <slug> [webhook_url]")
            return 2
        app_key(args[0], args[1] if len(args) > 1 else None)
    elif cmd == "seed-completed":
        if not args:
            print("usage: seed-completed <cs_id>")
            return 2
        seed_completed(args[0])
    elif cmd == "prune":
        prune()
    elif cmd == "geoip-update":
        geoip_update()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
