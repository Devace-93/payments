"""Transactional outbox: enqueue a mail inside the caller's transaction.

The API calls :func:`enqueue_mail` from inside ``session_scope``; the row
commits together with the user / token it belongs to, so a crash between the
business write and the side effect is impossible. ``dbcore.worker`` renders
and delivers the mail later. The payload never contains the token's hash,
only the plaintext token that the link needs (the row is deleted 7 days
after delivery and the token itself is single-use and short-lived).
"""
from __future__ import annotations

from .models import Outbox


def enqueue_mail(session, *, template: str, to: str, lang: str = "en", user_id=None,
                 name: str | None = None, token: str | None = None, return_to: str | None = None) -> Outbox:
    job = Outbox(
        kind="email",
        user_id=user_id,
        payload={
            "template": template,
            "to": to,
            "lang": lang,
            "name": name,
            "token": token,
            "return_to": return_to,
        },
    )
    session.add(job)
    return job
