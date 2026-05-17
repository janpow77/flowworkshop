"""
flowworkshop · services/email_service.py

E-Mail-Versand für die Workshop-Plattform.

Use-Cases:
- Anmeldebestätigung an Teilnehmer nach erfolgreicher Registrierung
- Admin-Benachrichtigung an den Veranstalter bei neuer Anmeldung

Versand über SMTP (Default: IONOS smtp.ionos.de:587 STARTTLS) mit der
in config.SMTP_FROM hinterlegten Absenderadresse. Inhalte werden aus
Jinja2-Templates gerendert; optional erzeugt das selbst betriebene LLM
einen kurzen personalisierten Absatz, sofern der Teilnehmer dem zugestimmt
hat (ai_confirmation_consent).

Versand wird nur durchgeführt, wenn config.EMAIL_ENABLED=true UND
SMTP_HOST + SMTP_USER + SMTP_PASSWORD gesetzt sind. Fehler werden geloggt,
aber nie an die HTTP-Anfrage durchgereicht — die Registrierung darf nicht
am Mailversand scheitern.
"""

from __future__ import annotations

import logging
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib
import httpx
from jinja2 import Environment, BaseLoader, select_autoescape

import config

log = logging.getLogger(__name__)


# ── Jinja2-Templates (inline, da nur zwei Mails) ────────────────────────────

_CONFIRM_TEXT = """\
Guten Tag {{ first_name }} {{ last_name }},

vielen Dank für Ihre Anmeldung zum {{ workshop_title }}.

Wir haben Ihre Daten erhalten:
  Name        : {{ first_name }} {{ last_name }}
  Organisation: {{ organization or '–' }}
{% if department %}  Abteilung   : {{ department }}
{% endif %}{% if fund %}  Fonds       : {{ fund }}
{% endif %}  E-Mail      : {{ email }}

{% if ai_paragraph %}{{ ai_paragraph }}

{% endif %}Sie können sich ab sofort über die Workshop-Plattform einloggen:
  {{ public_url }}/login

Die aktuelle Tagesordnung finden Sie unter:
  {{ public_url }}/agenda

Bei Rückfragen erreichen Sie uns unter {{ reply_to }}.

Mit freundlichen Grüßen
{{ organizer }}

—
Hinweis: Diese Nachricht wurde automatisch erzeugt. Datenschutz­erklärung
und Impressum finden Sie unter {{ public_url }}/datenschutz bzw.
{{ public_url }}/impressum.
"""

_ADMIN_NOTIFY_TEXT = """\
Neue Workshop-Anmeldung

Name        : {{ first_name }} {{ last_name }}
Organisation: {{ organization or '–' }}
Abteilung   : {{ department or '–' }}
Fonds       : {{ fund or '–' }}
E-Mail      : {{ email }}

Registrierungs-ID    : {{ registration_id }}
Bestätigungsmail gesendet: {{ 'ja' if confirmation_sent else 'nein' }}
KI-Personalisierung    : {{ 'aktiviert' if ai_consent else 'abgelehnt' }}

Admin-Bereich: {{ public_url }}/admin
"""

_jinja = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(disabled_extensions=("txt",), default=False),
    keep_trailing_newline=True,
)


# ── Konfigurations-Check ────────────────────────────────────────────────────

def is_configured() -> bool:
    """True, wenn die SMTP-Konfiguration vollständig ist."""
    return bool(
        config.EMAIL_ENABLED
        and config.SMTP_HOST
        and config.SMTP_USER
        and config.SMTP_PASSWORD
        and config.SMTP_FROM
    )


# ── LLM-Personalisierung (optional, non-streaming) ──────────────────────────

async def _generate_ai_paragraph(
    first_name: str, organization: str | None, fund: str | None
) -> str | None:
    """Erzeugt einen kurzen freundlichen Personalisierungs-Absatz.

    Nutzt den llm-router (`EGPU_GATEWAY_URL` + `X-App-Id`) non-streaming.
    Bei Timeout / Fehler wird None zurückgegeben — die Mail geht trotzdem.
    """
    if not config.EMAIL_AI_PERSONALIZE:
        return None

    org_hint = f" aus der Organisation »{organization}«" if organization else ""
    fund_hint = f" mit Schwerpunkt {fund}" if fund else ""
    user_prompt = (
        f"Schreibe einen kurzen, freundlichen Absatz (maximal 3 Sätze) für eine "
        f"automatische Anmeldebestätigung. Der Empfänger heißt {first_name}{org_hint}{fund_hint}. "
        f"Der Workshop heißt »KI und LLMs in der EFRE-Prüfbehörde« und richtet sich an "
        f"Prüferinnen und Prüfer. Bedanke dich für das Interesse, schreibe sachlich und "
        f"ohne Floskeln, keine Begrüßung und keine Grußformel — der Absatz wird in ein "
        f"vorhandenes Anschreiben eingefügt. Antworte ausschließlich mit dem Absatz, ohne "
        f"Vor- oder Nachspann."
    )

    payload = {
        "model": config.MODEL_NAME,
        "messages": [
            {"role": "system", "content": "Du bist eine sachliche deutsche Behördenkorrespondenz-Assistenz. Schreibe knapp und ohne Floskeln."},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "max_tokens": config.EMAIL_AI_MAX_TOKENS,
        "temperature": 0.3,
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5, read=config.EMAIL_AI_TIMEOUT_S)
        ) as client:
            resp = await client.post(
                f"{config.EGPU_GATEWAY_URL}/api/llm/chat/completions",
                json=payload,
                headers={"X-App-Id": config.EGPU_GATEWAY_APP_ID},
            )
            if resp.status_code >= 400:
                log.warning(
                    "AI-Personalisierung: Gateway HTTP %s — fahre ohne Absatz fort.",
                    resp.status_code,
                )
                return None
            data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = (message.get("content") or "").strip()
        # <think>…</think>-Blöcke entfernen, falls qwen3-Reasoning eingestreut hat.
        import re as _re
        text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
        if not text:
            return None
        # Sicherheitsnetz: maximal 3 Sätze und 600 Zeichen.
        sentences = _re.split(r"(?<=[.!?])\s+", text)
        text = " ".join(sentences[:3]).strip()
        return text[:600]
    except (httpx.HTTPError, ValueError) as e:
        log.warning("AI-Personalisierung fehlgeschlagen: %s — Mail ohne Absatz.", e)
        return None


# ── SMTP-Versand ─────────────────────────────────────────────────────────────

async def _send_message(msg: EmailMessage) -> bool:
    """Sendet eine fertige EmailMessage. True bei Erfolg, False sonst."""
    if not is_configured():
        log.info("E-Mail-Versand übersprungen: SMTP nicht konfiguriert.")
        return False
    try:
        ctx = ssl.create_default_context()
        await aiosmtplib.send(
            msg,
            hostname=config.SMTP_HOST,
            port=config.SMTP_PORT,
            start_tls=config.SMTP_STARTTLS,
            tls_context=ctx if config.SMTP_STARTTLS else None,
            username=config.SMTP_USER,
            password=config.SMTP_PASSWORD,
            timeout=config.EMAIL_TIMEOUT_S,
        )
        log.info("E-Mail gesendet an %s (Betreff: %s)", msg["To"], msg["Subject"])
        return True
    except (aiosmtplib.SMTPException, OSError, TimeoutError) as e:
        log.error("SMTP-Versand fehlgeschlagen (To=%s): %s", msg.get("To"), e)
        return False


def _build_message(
    *, to_addr: str, subject: str, body_text: str, reply_to: str | None = None
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_FROM))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=config.SMTP_FROM.split("@")[-1] or "flowaudit.de")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text, subtype="plain", charset="utf-8")
    return msg


# ── Öffentliche API ─────────────────────────────────────────────────────────

async def send_registration_confirmation(
    *,
    first_name: str,
    last_name: str,
    email: str,
    organization: str | None,
    department: str | None,
    fund: str | None,
    ai_consent: bool,
    workshop_title: str = "Prüferworkshop EFRE Hessen 2026",
) -> bool:
    """Sendet die Anmeldebestätigung an den Teilnehmer.

    Wenn ai_consent=True und EMAIL_AI_PERSONALIZE=true, wird ein KI-Absatz
    eingebettet — andernfalls bleibt der Absatz leer.
    """
    if not is_configured():
        return False

    ai_paragraph: str | None = None
    if ai_consent and config.EMAIL_AI_PERSONALIZE:
        ai_paragraph = await _generate_ai_paragraph(first_name, organization, fund)

    body = _jinja.from_string(_CONFIRM_TEXT).render(
        first_name=first_name,
        last_name=last_name,
        email=email,
        organization=organization,
        department=department,
        fund=fund,
        ai_paragraph=ai_paragraph,
        workshop_title=workshop_title,
        public_url=config.EMAIL_PUBLIC_URL.rstrip("/"),
        reply_to=config.SMTP_FROM,
        organizer=config.SMTP_FROM_NAME,
    )
    msg = _build_message(
        to_addr=email,
        subject=f"Bestätigung Ihrer Anmeldung — {workshop_title}",
        body_text=body,
        reply_to=config.SMTP_FROM,
    )
    return await _send_message(msg)


async def send_admin_notification(
    *,
    registration_id: str,
    first_name: str,
    last_name: str,
    email: str,
    organization: str | None,
    department: str | None,
    fund: str | None,
    confirmation_sent: bool,
    ai_consent: bool,
) -> bool:
    """Benachrichtigt den in ADMIN_NOTIFY_EMAIL hinterlegten Veranstalter."""
    if not is_configured() or not config.ADMIN_NOTIFY_EMAIL:
        return False

    body = _jinja.from_string(_ADMIN_NOTIFY_TEXT).render(
        registration_id=registration_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        organization=organization,
        department=department,
        fund=fund,
        confirmation_sent=confirmation_sent,
        ai_consent=ai_consent,
        public_url=config.EMAIL_PUBLIC_URL.rstrip("/"),
    )
    msg = _build_message(
        to_addr=config.ADMIN_NOTIFY_EMAIL,
        subject=f"Neue Workshop-Anmeldung: {first_name} {last_name}",
        body_text=body,
        reply_to=email,
    )
    return await _send_message(msg)


async def send_registration_emails(
    *,
    registration_id: str,
    first_name: str,
    last_name: str,
    email: str,
    organization: str | None,
    department: str | None,
    fund: str | None,
    ai_consent: bool,
) -> None:
    """BackgroundTask-Helper: schickt Teilnehmer- und Admin-Mail.

    Schluckt Fehler — die Registrierung muss auch ohne Mailversand stabil
    bleiben. Wird typischerweise via FastAPI BackgroundTasks aufgerufen.
    """
    if not is_configured():
        log.info(
            "Registrierung %s: E-Mail-Versand nicht konfiguriert (EMAIL_ENABLED=%s, host=%s).",
            registration_id, config.EMAIL_ENABLED, bool(config.SMTP_HOST),
        )
        return

    confirmation_sent = False
    try:
        confirmation_sent = await send_registration_confirmation(
            first_name=first_name,
            last_name=last_name,
            email=email,
            organization=organization,
            department=department,
            fund=fund,
            ai_consent=ai_consent,
        )
    except Exception as e:  # noqa: BLE001 — letztes Sicherheitsnetz
        log.exception("Fehler beim Teilnehmer-Mailversand für %s: %s", email, e)

    try:
        await send_admin_notification(
            registration_id=registration_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            organization=organization,
            department=department,
            fund=fund,
            confirmation_sent=confirmation_sent,
            ai_consent=ai_consent,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Fehler beim Admin-Notify für %s: %s", email, e)
