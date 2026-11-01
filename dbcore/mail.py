"""Outbound mail. One function, :func:`send`, driven by ``SMTP_URL``
(copied from retro's ``dbcore/mail.py``).

``SMTP_URL`` forms::

    smtp://user:pass@host:587?starttls=1     # submission port with STARTTLS
    smtps://user:pass@host:465               # implicit TLS (Resend: smtps://resend:re_xxx@smtp.resend.com:465)
    smtp://host:1025                         # plain (local Mailpit/MailHog)

When ``MAIL_ENABLED`` is false (the default) nothing leaves the box: the mail
is logged at INFO and the caller gets ``"skipped"`` so it can record that
state instead of pretending.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib.parse import parse_qs, unquote, urlparse

from .config import config

log = logging.getLogger("accounts.mail")


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    user: str | None
    password: str | None
    implicit_tls: bool
    starttls: bool


class MailError(RuntimeError):
    """Transient delivery failure (the outbox retries these)."""


def parse_smtp_url(url: str) -> SmtpSettings:
    parsed = urlparse(url)
    if parsed.scheme not in ("smtp", "smtps"):
        raise ValueError("SMTP_URL must start with smtp:// or smtps://")
    if not parsed.hostname:
        raise ValueError("SMTP_URL has no host")
    implicit_tls = parsed.scheme == "smtps"
    query = parse_qs(parsed.query)
    starttls = query.get("starttls", ["0"])[0].lower() in ("1", "true", "yes")
    return SmtpSettings(
        host=parsed.hostname,
        port=parsed.port or (465 if implicit_tls else 587),
        user=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        implicit_tls=implicit_tls,
        starttls=starttls and not implicit_tls,
    )


def is_enabled() -> bool:
    return bool(config.mail_enabled and config.smtp_url)


def build_message(
    *, to: list[str], subject: str, text: str, html: str | None = None, reply_to: str | None = None
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.mail_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="accounts.3m4.net")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send(*, to: list[str], subject: str, text: str, html: str | None = None, reply_to: str | None = None) -> str:
    """Deliver one message. Returns ``"sent"`` or ``"skipped"``; raises
    :class:`MailError` on a transport failure so the outbox can retry."""
    to = [addr for addr in to if addr]
    if not to:
        return "skipped"
    if not is_enabled():
        log.info("mail disabled; skipped mail subject=%r", subject)
        return "skipped"
    settings = parse_smtp_url(config.smtp_url)
    msg = build_message(to=to, subject=subject, text=text, html=html, reply_to=reply_to)
    try:
        if settings.implicit_tls:
            client = smtplib.SMTP_SSL(settings.host, settings.port, timeout=15, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=15)
        with client:
            client.ehlo()
            if settings.starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.user:
                client.login(settings.user, settings.password or "")
            client.send_message(msg)
    except (smtplib.SMTPException, OSError) as err:
        raise MailError(str(err)) from err
    log.info("mail sent subject=%r", subject)
    return "sent"
