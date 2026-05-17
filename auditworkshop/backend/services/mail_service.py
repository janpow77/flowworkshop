"""
flowworkshop · services/mail_service.py
Transaktions-Mail-Versand ueber SMTP (Hetzner) mit stdlib smtplib.

Versendet kurze Text-Mails fuer:
- Signup-Bestaetigung an den Nutzer
- Neue-Anmeldung-Benachrichtigung an alle Admin-Registrations
- Freischaltungs-Mitteilung an den Nutzer
- Ablehnungs-Mitteilung an den Nutzer
- Passwort-Reset-/Setup-Link an den Nutzer

Konfiguration komplett ueber config.py-Env-Vars. Fehler beim Versand werden
geloggt, brechen aber den aufrufenden Request niemals ab.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from config import (
    MAIL_ENABLED,
    MAIL_FROM,
    MAIL_FROM_NAME,
    PUBLIC_BASE_URL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_STARTTLS,
    SMTP_TIMEOUT,
    SMTP_USE_SSL,
    SMTP_USER,
)

log = logging.getLogger(__name__)


def _build_from() -> str:
    """Liefert den `From:`-Header. Faellt auf SMTP_USER zurueck."""
    addr = MAIL_FROM or SMTP_USER
    if not addr:
        return ""
    if MAIL_FROM_NAME:
        return formataddr((MAIL_FROM_NAME, addr))
    return addr


def send_mail(to: str, subject: str, body: str) -> bool:
    """Sendet eine Text-Mail. Liefert True bei Erfolg, False sonst.

    Fehler werden geloggt, aber niemals geworfen — die aufrufenden
    Auth-Endpunkte sollen durch Mail-Probleme nicht 5xx werden.
    """
    if not MAIL_ENABLED:
        log.info("MAIL_ENABLED=false — unterdruecke Versand an %s (%s)", to, subject)
        return False
    if not to or "@" not in to:
        log.warning("send_mail: ungueltige Empfaenger-Adresse %r", to)
        return False
    sender = _build_from()
    if not sender:
        log.warning("send_mail: kein Absender konfiguriert (MAIL_FROM/SMTP_USER leer)")
        return False
    if not SMTP_HOST:
        log.warning("send_mail: kein SMTP_HOST konfiguriert")
        return False

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=context
            ) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
                if SMTP_STARTTLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        log.info("Mail gesendet an %s: %s", to, subject)
        return True
    except Exception:  # noqa: BLE001 — Mail-Probleme duerfen Request nicht stoppen
        log.exception("Mail-Versand an %s fehlgeschlagen (%s)", to, subject)
        return False


# ── Vorgefertigte Templates ────────────────────────────────────────────────


def send_signup_confirmation(*, to: str, first_name: str) -> bool:
    subject = "Ihre Anmeldung beim FlowAudit-Workshop"
    body = (
        f"Hallo {first_name},\n\n"
        "vielen Dank fuer Ihre Anmeldung beim FlowAudit-Workshop.\n\n"
        "Ihr Konto wartet nun auf die Freischaltung durch einen Admin. "
        "Sobald Ihr Konto aktiviert ist, erhalten Sie eine weitere E-Mail "
        "und koennen sich mit Ihrer E-Mail-Adresse und dem von Ihnen "
        "vergebenen Passwort einloggen unter:\n"
        f"  {PUBLIC_BASE_URL}/login\n\n"
        "Bei Rueckfragen antworten Sie einfach auf diese E-Mail.\n\n"
        "Mit freundlichen Gruessen\n"
        "FlowAudit-Workshop"
    )
    return send_mail(to, subject, body)


def send_admin_new_signup(
    *,
    to: str,
    new_user_name: str,
    new_user_email: str,
    new_user_organization: str,
    new_user_bundesland: str | None,
    new_user_function: str | None,
    new_user_reason: str | None,
) -> bool:
    subject = f"Neue Workshop-Anmeldung: {new_user_name}"
    lines = [
        "Hallo,",
        "",
        "eine neue Anmeldung wartet auf Freischaltung im FlowAudit-Workshop:",
        "",
        f"  Name:         {new_user_name}",
        f"  E-Mail:       {new_user_email}",
        f"  Organisation: {new_user_organization}",
    ]
    if new_user_bundesland:
        lines.append(f"  Bundesland:   {new_user_bundesland}")
    if new_user_function:
        lines.append(f"  Funktion:     {new_user_function}")
    if new_user_reason:
        lines.append("")
        lines.append("  Begruendung:")
        for ln in new_user_reason.splitlines():
            lines.append(f"    {ln}")
    lines.extend(
        [
            "",
            "Freischaltung im Admin-Bereich:",
            f"  {PUBLIC_BASE_URL}/admin",
            "",
            "FlowAudit-Workshop",
        ]
    )
    return send_mail(to, subject, "\n".join(lines))


def send_approval_notification(*, to: str, first_name: str) -> bool:
    subject = "Ihr FlowAudit-Workshop-Konto ist freigeschaltet"
    body = (
        f"Hallo {first_name},\n\n"
        "Ihr Konto fuer den FlowAudit-Workshop wurde soeben freigeschaltet.\n\n"
        "Sie koennen sich jetzt mit Ihrer E-Mail-Adresse und Ihrem Passwort "
        "einloggen:\n"
        f"  {PUBLIC_BASE_URL}/login\n\n"
        "Mit freundlichen Gruessen\n"
        "FlowAudit-Workshop"
    )
    return send_mail(to, subject, body)


def send_rejection_notification(
    *, to: str, first_name: str, reason: str | None
) -> bool:
    subject = "Ihre FlowAudit-Workshop-Anmeldung"
    body_lines = [
        f"Hallo {first_name},",
        "",
        "Ihre Anmeldung fuer den FlowAudit-Workshop wurde leider nicht "
        "freigeschaltet.",
    ]
    if reason:
        body_lines.extend(["", "Begruendung:", reason])
    body_lines.extend(
        [
            "",
            "Bei Rueckfragen antworten Sie einfach auf diese E-Mail.",
            "",
            "Mit freundlichen Gruessen",
            "FlowAudit-Workshop",
        ]
    )
    return send_mail(to, subject, "\n".join(body_lines))


def send_setup_link(
    *, to: str, first_name: str, setup_path: str, expires_iso: str, purpose: str
) -> bool:
    is_setup = purpose == "setup"
    subject = (
        "Passwort fuer Ihren FlowAudit-Workshop-Zugang setzen"
        if is_setup
        else "Passwort fuer Ihren FlowAudit-Workshop-Zugang zuruecksetzen"
    )
    intro = (
        "ein Admin hat einen Link fuer das Setzen Ihres Passworts erstellt."
        if is_setup
        else "ein Admin hat fuer Sie einen Passwort-Reset-Link erstellt."
    )
    full_url = f"{PUBLIC_BASE_URL}{setup_path}"
    body = (
        f"Hallo {first_name},\n\n"
        f"{intro}\n\n"
        f"Bitte klicken Sie innerhalb der naechsten 24 Stunden auf den "
        f"folgenden Link, um Ihr Passwort zu setzen:\n"
        f"  {full_url}\n\n"
        f"Der Link ist gueltig bis: {expires_iso}\n\n"
        "Wenn Sie diesen Link nicht angefordert haben, koennen Sie diese "
        "E-Mail ignorieren.\n\n"
        "Mit freundlichen Gruessen\n"
        "FlowAudit-Workshop"
    )
    return send_mail(to, subject, body)
