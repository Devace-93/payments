"""Mail templates: ``verify``, ``magic``, ``magic_no_account``,
``password_changed`` in English and Spanish (other locales fall back to
English). Each renders to ``(subject, text, html)``.

Links always point at the hosted *pages* (``/verify?token=``,
``/magic?token=``), which POST the token; a GET never consumes anything.
"""
from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from .config import config

SUPPORTED_LANGS = ("en", "es")


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


def verify_link(token: str, return_to: str | None = None) -> str:
    params = {"token": token}
    if return_to:
        params["return_to"] = return_to
    return f"{config.accounts_url}/verify?{urlencode(params)}"


def magic_link(token: str, return_to: str | None = None) -> str:
    params = {"token": token}
    if return_to:
        params["return_to"] = return_to
    return f"{config.accounts_url}/magic?{urlencode(params)}"


def signup_link() -> str:
    return f"{config.accounts_url}/signup"


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "brand": "3m4 accounts",
        "verify.subject": "Confirm your email for 3m4",
        "verify.body": "Hi {name},\n\nConfirm this address to finish setting up your 3m4 account:",
        "verify.cta": "Confirm my email",
        "verify.expires": "The link works for {hours} hours. If you did not create an account, ignore this message.",
        "magic.subject": "Your sign-in link for 3m4",
        "magic.body": "Hi {name},\n\nClick the link below to sign in. It works once, for {minutes} minutes.",
        "magic.cta": "Sign in to 3m4",
        "magic.ignore": "If you did not ask for this link, you can ignore this message; nobody can sign in without it.",
        "noaccount.subject": "No 3m4 account for this address yet",
        "noaccount.body": "Someone (probably you) asked for a sign-in link for {email}, but there is no 3m4 account with that address.\n\nCreate one in a minute:",
        "noaccount.cta": "Create an account",
        "noaccount.ignore": "If that was not you, ignore this message.",
        "pwd.subject": "Your 3m4 password was changed",
        "pwd.body": "Hi {name},\n\nThe password of your 3m4 account was just changed and every other session was signed out.\n\nIf that was you, there is nothing else to do. If it was not, request a sign-in link right away and change the password from your profile:",
        "pwd.cta": "Open my profile",
        "footer": "This message was sent by {brand} ({url}) because of an action involving {email}.",
        "fallback": "If the button does not work, copy this address into your browser:",
    },
    "es": {
        "brand": "Cuentas 3m4",
        "verify.subject": "Confirma tu correo para 3m4",
        "verify.body": "Hola {name}:\n\nConfirma esta dirección para terminar de crear tu cuenta de 3m4:",
        "verify.cta": "Confirmar mi correo",
        "verify.expires": "El enlace funciona durante {hours} horas. Si no creaste una cuenta, ignora este mensaje.",
        "magic.subject": "Tu enlace para entrar a 3m4",
        "magic.body": "Hola {name}:\n\nHaz clic en el enlace para iniciar sesión. Funciona una sola vez, durante {minutes} minutos.",
        "magic.cta": "Entrar a 3m4",
        "magic.ignore": "Si no pediste este enlace, ignora este mensaje; nadie puede entrar sin él.",
        "noaccount.subject": "Aún no hay una cuenta de 3m4 con este correo",
        "noaccount.body": "Alguien (probablemente tú) pidió un enlace de acceso para {email}, pero no existe una cuenta de 3m4 con esa dirección.\n\nCrea una en un minuto:",
        "noaccount.cta": "Crear una cuenta",
        "noaccount.ignore": "Si no fuiste tú, ignora este mensaje.",
        "pwd.subject": "Se cambió la contraseña de tu cuenta de 3m4",
        "pwd.body": "Hola {name}:\n\nSe acaba de cambiar la contraseña de tu cuenta de 3m4 y se cerraron las demás sesiones.\n\nSi fuiste tú, no tienes que hacer nada más. Si no, pide un enlace de acceso de inmediato y cambia la contraseña desde tu perfil:",
        "pwd.cta": "Abrir mi perfil",
        "footer": "Este mensaje lo envió {brand} ({url}) por una acción relacionada con {email}.",
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
            f'<p style="margin:20px 0"><a href="{escape(url)}" style="display:inline-block;background:#4f46e5;'
            f'color:#fff;text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px">{escape(cta)}</a></p>'
        )
        link_line = (
            f'<p style="color:#64748b;font-size:12px;margin:0 0 12px">{escape(fallback)}<br>'
            f'<a href="{escape(url)}" style="color:#4f46e5;word-break:break-all">{escape(url)}</a></p>'
        )
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.5;'
        'color:#1e293b;max-width:520px;margin:0 auto;padding:24px">'
        f"{paragraphs}{button}{link_line}"
        f'<p style="color:#64748b;font-size:13px;margin:16px 0 0">{escape(tail)}</p>'
        f'<hr style="border:0;border-top:1px solid #e2e8f0;margin:20px 0">'
        f'<p style="color:#94a3b8;font-size:12px;margin:0">{escape(footer)}</p></div>'
    )


def render(template: str, *, lang: str, to: str, name: str | None = None, token: str | None = None,
           return_to: str | None = None) -> tuple[str, str, str]:
    """``(subject, text, html)`` for one of the four templates."""
    lang = lang if lang in SUPPORTED_LANGS else "en"
    display = name or to.split("@", 1)[0]
    footer = _s(lang, "footer", brand=_s(lang, "brand"), url=config.accounts_url, email=to)
    fallback = _s(lang, "fallback")

    if template == "verify":
        url = verify_link(token or "", return_to)
        body = _s(lang, "verify.body", name=display)
        tail = _s(lang, "verify.expires", hours=config.verify_token_ttl_hours)
        cta = _s(lang, "verify.cta")
        subject = _s(lang, "verify.subject")
    elif template == "magic":
        url = magic_link(token or "", return_to)
        body = _s(lang, "magic.body", name=display, minutes=config.magic_token_ttl_min)
        tail = _s(lang, "magic.ignore")
        cta = _s(lang, "magic.cta")
        subject = _s(lang, "magic.subject")
    elif template == "magic_no_account":
        url = signup_link()
        body = _s(lang, "noaccount.body", email=to)
        tail = _s(lang, "noaccount.ignore")
        cta = _s(lang, "noaccount.cta")
        subject = _s(lang, "noaccount.subject")
    elif template == "password_changed":
        url = f"{config.accounts_url}/profile"
        body = _s(lang, "pwd.body", name=display)
        tail = ""
        cta = _s(lang, "pwd.cta")
        subject = _s(lang, "pwd.subject")
    else:
        raise ValueError(f"unknown mail template {template!r}")

    text = f"{body}\n\n{cta}: {url}\n\n{tail}\n\n-- \n{footer}\n".replace("\n\n\n", "\n\n")
    html = _html(body=body, cta=cta, url=url, tail=tail, footer=footer, fallback=fallback)
    return subject, text, html
