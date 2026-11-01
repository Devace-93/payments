"""Tiny management CLI used by the `migrate` compose service (and cron).

    python -m dbcore.cli upgrade        # create_all + alembic upgrade head
    python -m dbcore.cli migrate        # alembic upgrade head only
    python -m dbcore.cli create-all     # SQLAlchemy create_all only
    python -m dbcore.cli genkey         # print a fresh SESSION_SIGNING_KEY
    python -m dbcore.cli pubkey         # print the public key of SESSION_SIGNING_KEY (rotations)
    python -m dbcore.cli prune         # delete expired tokens / sessions, old outbox rows

Schema lifecycle: ``create_all`` bootstraps a fresh database in one shot, then
Alembic (``db/migrations``) evolves it. Migrations are written idempotently so
the two can run back to back on both fresh and existing databases.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, or_

from . import models  # noqa: F401  (register models on Base.metadata)
from .db import Base, engine, session_scope


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


def genkey() -> None:
    from .keys import generate_seed

    print(generate_seed())


def pubkey() -> None:
    """Base64url public key of SESSION_SIGNING_KEY (what goes into
    SESSION_PREVIOUS_PUBLIC_KEYS when rotating)."""
    from .keys import jwk_for, keyring

    print(jwk_for(keyring().public_key)["x"])


def prune(days: int = 7) -> None:
    """Delete used/expired email tokens, expired or revoked sessions and
    finished outbox rows older than ``days``."""
    from .models import EmailToken, Outbox, Session

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    with session_scope() as session:
        tokens = session.execute(
            delete(EmailToken).where(or_(EmailToken.expires_at < cutoff, EmailToken.used_at < cutoff))
        ).rowcount
        sessions = session.execute(
            delete(Session).where(or_(Session.expires_at < cutoff, Session.revoked_at < cutoff))
        ).rowcount
        outbox = session.execute(
            delete(Outbox).where(Outbox.status.in_(("sent", "skipped", "failed")), Outbox.created_at < cutoff)
        ).rowcount
    print(f"✓ pruned {tokens or 0} token(s), {sessions or 0} session(s), {outbox or 0} outbox row(s)")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "upgrade"
    if cmd == "upgrade":
        create_all()
        migrate()
    elif cmd == "migrate":
        migrate()
    elif cmd == "create-all":
        create_all()
    elif cmd == "genkey":
        genkey()
    elif cmd == "pubkey":
        pubkey()
    elif cmd == "prune":
        prune()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
