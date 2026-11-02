"""Mail templates (CONTRACT.md §12): ``donation_receipt``,
``subscription_started``, ``subscription_cancelled``, ``payment_failed`` in
English and Spanish (other locales fall back to English). Each renders to
``(subject, text, html)`` from a ``params`` dict:

- ``donation_receipt``: ``amount, currency, app_name, code?``
- ``subscription_started``: ``app_name, label, amount, currency, interval, period_end``
- ``subscription_cancelled``: ``app_name, label, period_end``
- ``payment_failed``: ``app_name, label``

Links point at the hosted pages (``/claim?code=``, ``/me``); Stripe's own
receipts (legal lines) stay enabled in the Dashboard.
"""
from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .config import config

SUPPORTED_LANGS = ("en", "es")

_SYMBOLS = {"usd": "$", "eur": "€", "mxn": "MX$", "gbp": "£"}


def pick_lang(*candidates: str | None) -> str:
    """First supported base language among ``candidates`` (``es-MX`` → ``es``)."""
    for cand in candidates:
        if not cand:
            continue
        for part in cand.split(","):
            base = part.strip().split(";")[0].strip()[:2].lower()
            if base in SUPPORTED_LANGS:
                return base
    return "en"


def fmt_amount(cents: int | None, currency: str | None) -> str:
    """``"$5.00 USD"``, ``"MX$100.00"``, ``"€5.00"`` (unknown → ``"5.00 XYZ"``)."""
    cents = int(cents or 0)
    currency = (currency or "").lower()
    major = f"{cents / 100:,.2f}"
    if currency == "usd":
        return f"${major} USD"
    symbol = _SYMBOLS.get(currency)
    if symbol:
        return f"{symbol}{major}"
    return f"{major} {currency.upper()}".strip()


def claim_link(code: str) -> str:
    return f"{config.payments_url}/claim?{urlencode({'code': code})}"


def me_link(portal: bool = False) -> str:
    return f"{config.payments_url}/me" + ("?portal=1" if portal else "")


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "brand": "3m4 payments",
        "interval.month": "month",
        "interval.year": "year",
        "receipt.subject": "Thank you for supporting {app_name}",
        "receipt.body": "Thank you! Your donation of {amount} to {app_name} went through.",
        "receipt.code": "This donation was made without an account. To attach it to your 3m4 account (supporter badge, history), use this claim code:\n\n{code}",
        "receipt.cta": "Claim this donation",
        "receipt.cta_account": "See my support",
        "receipt.tail": "Stripe sends a separate receipt for your records. Reply to this message if anything looks wrong.",
        "receipt.tail_code": "The code works once and expires in {days} days. Stripe sends a separate receipt for your records.",
        "started.subject": "Your {app_name} {label} subscription is active",
        "started.body": "Thanks for subscribing to {app_name} {label}: {amount} per {interval}.\n\nYour first period ends on {period_end}. You can switch plans, update your card or cancel at any time from your payments page.",
        "started.cta": "Manage my subscription",
        "started.tail": "Stripe emails you an invoice for every renewal.",
        "cancelled.subject": "Your {app_name} {label} subscription has been cancelled",
        "cancelled.body": "Your {app_name} {label} subscription will not renew. {label} stays active until {period_end}; after that your account goes back to the free plan.\n\nChanged your mind? You can resubscribe at any time.",
        "cancelled.cta": "Resubscribe",
        "cancelled.tail": "Sorry to see you go. Reply to this message if something did not work the way you expected.",
        "failed.subject": "Payment failed for {app_name} {label}",
        "failed.body": "We could not charge your card for {app_name} {label}. Stripe will retry a few times; if it keeps failing the subscription will be cancelled.\n\nUpdate your payment method to keep {label}:",
        "failed.cta": "Update my payment method",
        "failed.tail": "If you already updated it, ignore this message.",
        "footer": "This message was sent by {brand} ({url}) to {email} because of a payment to a 3m4 app.",
        "fallback": "If the button does not work, copy this address into your browser:",
    },
    "es": {
        "brand": "Pagos 3m4",
        "interval.month": "mes",
        "interval.year": "año",
        "receipt.subject": "Gracias por apoyar a {app_name}",
        "receipt.body": "¡Gracias! Tu donación de {amount} a {app_name} se realizó correctamente.",
        "receipt.code": "Esta donación se hizo sin cuenta. Para asociarla a tu cuenta de 3m4 (insignia de patrocinador, historial), usa este código:\n\n{code}",
        "receipt.cta": "Reclamar esta donación",
        "receipt.cta_account": "Ver mi apoyo",
        "receipt.tail": "Stripe te envía un recibo aparte. Responde a este mensaje si algo no cuadra.",
        "receipt.tail_code": "El código funciona una sola vez y caduca en {days} días. Stripe te envía un recibo aparte.",
        "started.subject": "Tu suscripción {label} de {app_name} está activa",
        "started.body": "Gracias por suscribirte a {app_name} {label}: {amount} al {interval}.\n\nTu primer periodo termina el {period_end}. Puedes cambiar de plan, actualizar tu tarjeta o cancelar cuando quieras desde tu página de pagos.",
        "started.cta": "Gestionar mi suscripción",
        "started.tail": "Stripe te envía una factura por cada renovación.",
        "cancelled.subject": "Tu suscripción {label} de {app_name} se ha cancelado",
        "cancelled.body": "Tu suscripción {label} de {app_name} no se renovará. {label} sigue activo hasta el {period_end}; después tu cuenta vuelve al plan gratuito.\n\n¿Cambiaste de opinión? Puedes volver a suscribirte cuando quieras.",
        "cancelled.cta": "Volver a suscribirme",
        "cancelled.tail": "Sentimos verte partir. Responde a este mensaje si algo no funcionó como esperabas.",
        "failed.subject": "Falló el pago de {app_name} {label}",
        "failed.body": "No pudimos hacer el cargo a tu tarjeta por {app_name} {label}. Stripe lo reintentará varias veces; si sigue fallando, la suscripción se cancelará.\n\nActualiza tu método de pago para conservar {label}:",
        "failed.cta": "Actualizar mi método de pago",
        "failed.tail": "Si ya lo actualizaste, ignora este mensaje.",
        "footer": "Este mensaje lo envió {brand} ({url}) a {email} por un pago a una app de 3m4.",
        "fallback": "Si el botón no funciona, copia esta dirección en tu navegador:",
    },
}


def _s(lang: str, key: str, **params) -> str:
    text = _STRINGS.get(lang, _STRINGS["en"]).get(key) or _STRINGS["en"][key]
    return text.format(**params) if params else text


def _html(*, body: str, cta: str | None, url: str | None, tail: str, footer: str, fallback: str) -> str:
    paragraphs = "".join(f"<p style=\"margin:0 0 12px\">{escape(p)}</p>" for p in body.split("\n\n"))
    button = ""
    link_line = ""
    if url and cta:
        button = (
            f'<p style="margin:20px 0"><a href="{escape(url)}" style="display:inline-block;background:#d97706;'
            f'color:#fff;text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px">{escape(cta)}</a></p>'
        )
        link_line = (
            f'<p style="color:#64748b;font-size:12px;margin:0 0 12px">{escape(fallback)}<br>'
            f'<a href="{escape(url)}" style="color:#d97706;word-break:break-all">{escape(url)}</a></p>'
        )
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.5;'
        'color:#1e293b;max-width:520px;margin:0 auto;padding:24px">'
        f"{paragraphs}{button}{link_line}"
        f'<p style="color:#64748b;font-size:13px;margin:16px 0 0">{escape(tail)}</p>'
        f'<hr style="border:0;border-top:1px solid #e2e8f0;margin:20px 0">'
        f'<p style="color:#94a3b8;font-size:12px;margin:0">{escape(footer)}</p></div>'
    )


def render(template: str, *, lang: str, to: str, params: dict | None = None) -> tuple[str, str, str]:
    """``(subject, text, html)`` for one of the four templates."""
    lang = lang if lang in SUPPORTED_LANGS else "en"
    p = dict(params or {})
    app_name = p.get("app_name") or "3m4"
    label = p.get("label") or ""
    amount = fmt_amount(p.get("amount"), p.get("currency"))
    period_end = p.get("period_end") or "—"
    footer = _s(lang, "footer", brand=_s(lang, "brand"), url=config.payments_url, email=to)
    fallback = _s(lang, "fallback")

    if template == "donation_receipt":
        subject = _s(lang, "receipt.subject", app_name=app_name)
        body = _s(lang, "receipt.body", amount=amount, app_name=app_name)
        code = p.get("code")
        if code:
            body += "\n\n" + _s(lang, "receipt.code", code=code)
            url = claim_link(code)
            cta = _s(lang, "receipt.cta")
            tail = _s(lang, "receipt.tail_code", days=config.claim_code_ttl_days)
        else:
            url = me_link()
            cta = _s(lang, "receipt.cta_account")
            tail = _s(lang, "receipt.tail")
    elif template == "subscription_started":
        interval = _s(lang, f"interval.{p.get('interval') or 'month'}") if p.get("interval") in ("month", "year") else (p.get("interval") or "")
        subject = _s(lang, "started.subject", app_name=app_name, label=label)
        body = _s(lang, "started.body", app_name=app_name, label=label, amount=amount, interval=interval, period_end=period_end)
        url = me_link()
        cta = _s(lang, "started.cta")
        tail = _s(lang, "started.tail")
    elif template == "subscription_cancelled":
        subject = _s(lang, "cancelled.subject", app_name=app_name, label=label)
        body = _s(lang, "cancelled.body", app_name=app_name, label=label, period_end=period_end)
        url = p.get("resubscribe_url") or me_link()
        cta = _s(lang, "cancelled.cta")
        tail = _s(lang, "cancelled.tail")
    elif template == "payment_failed":
        subject = _s(lang, "failed.subject", app_name=app_name, label=label)
        body = _s(lang, "failed.body", app_name=app_name, label=label)
        url = me_link(portal=True)
        cta = _s(lang, "failed.cta")
        tail = _s(lang, "failed.tail")
    else:
        raise ValueError(f"unknown mail template {template!r}")

    text = f"{body}\n\n{cta}: {url}\n\n{tail}\n\n-- \n{footer}\n".replace("\n\n\n", "\n\n")
    html = _html(body=body, cta=cta, url=url, tail=tail, footer=footer, fallback=fallback)
    return subject, text, html
