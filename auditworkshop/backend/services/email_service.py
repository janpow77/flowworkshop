"""
flowworkshop · services/email_service.py

E-Mail-Versand für die Workshop-Plattform.

Use-Cases:
- Anmeldebestätigung an Teilnehmer nach erfolgreicher Registrierung
  (alter Pfad /api/event/register ohne Passwort)
- Admin-Benachrichtigung an den Veranstalter bei neuer Anmeldung
- Einladung mit Setup-Link für Setup-Token (Admin-Workflow)
- Signup-Alert bei Selbst-Registrierung (/api/auth/signup, pending_approval)

Inhalte werden aus Jinja2-Templates gerendert. Pro Template gibt es:
1. Einen hartcodierten Default in `DEFAULT_TEMPLATES` (subject + body).
2. Eine optionale Override-Zeile in der DB-Tabelle workshop_email_templates,
   die der Admin im AdminPage-Tab "Mail-Vorlagen" bearbeiten kann.
DB-Lookup hat Vorrang, Default ist das Sicherheitsnetz.

Versand über SMTP (Default: IONOS smtp.ionos.de:587 STARTTLS) mit der in
config.SMTP_FROM hinterlegten Absenderadresse. Versand ist nur aktiv, wenn
config.EMAIL_ENABLED=true UND SMTP_HOST + SMTP_USER + SMTP_PASSWORD gesetzt.
Fehler werden geloggt, aber nie an die HTTP-Anfrage durchgereicht — die
Registrierung darf nicht am Mailversand scheitern.
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


# ── Default-Templates (Single Source of Truth für Seed + Fallback) ──────────

DEFAULT_TEMPLATES: dict[str, dict[str, str | list[str]]] = {
    "confirmation": {
        "description": (
            "Anmeldebestätigung an Teilnehmer nach Selbst-Registrierung "
            "über /register (alter Pfad, ohne Passwort)."
        ),
        "subject": "Bestätigung Ihrer Anmeldung — {{ workshop_title }}",
        "placeholders": [
            "first_name", "last_name", "email", "organization", "department",
            "fund", "ai_paragraph", "workshop_title", "public_url",
            "reply_to", "organizer",
        ],
        "body": """\
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
""",
    },

    "admin_notify": {
        "description": (
            "Admin-Benachrichtigung an ADMIN_NOTIFY_EMAIL nach einer "
            "Registrierung über /register (alter Pfad)."
        ),
        "subject": "Neue Workshop-Anmeldung: {{ first_name }} {{ last_name }}",
        "placeholders": [
            "first_name", "last_name", "email", "organization", "department",
            "fund", "registration_id", "confirmation_sent", "ai_consent",
            "public_url",
        ],
        "body": """\
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
""",
    },

    "invite": {
        "description": (
            "Einladung mit Setup-Link für Selbst-Passwort-Vergabe. Wird vom "
            "Admin-Button \"Mail senden\" im AdminUsersPanel ausgelöst."
        ),
        "subject": (
            "Erweiterte Recherche- und Auswertungsbereiche der Plattform "
            "„KI und LLM für Prüfbehörden\""
        ),
        "placeholders": ["first_name", "last_name", "setup_url", "public_url"],
        "body": """\
Guten Tag {{ first_name }} {{ last_name }},

ich möchte Sie gerne auf die neuen Recherche- und Auswertungsbereiche der
Plattform „KI und LLM für Prüfbehörden" aufmerksam machen. Sie haben sich
auf der Plattform angemeldet und werden hiermit freigeschaltet. Im Nachgang
zum Prüferworkshop 2026 in Hannover habe ich die Anwendung um mehrere
offene Recherchefunktionen erweitert und freue mich, wenn Sie diese in der
Praxis erproben.


Ihr Zugang zur Plattform
========================

Bitte legen Sie über den folgenden Link Ihr persönliches Passwort fest
(der Link ist 24 Stunden gültig und einmalig nutzbar):

  {{ setup_url }}

Nach der Einrichtung erreichen Sie die Plattform jederzeit unter
{{ public_url }}/login mit Ihrer E-Mail-Adresse und Ihrem gewählten
Passwort.


Die Auswertungsbereiche im Überblick
====================================

• Begünstigtenverzeichnisse: Intelligente Suche und Karten-Visualisierung
  innerhalb der öffentlich zugänglichen EFRE-/ESF-/JTF-Begünstigtenlisten.

• EU-Beihilfe-Register: Gezielte Recherche in den veröffentlichten
  Beihilfedaten (Empfänger, Beträge, Beihilfeinstrumente, Regionen,
  Behörden und Förderziele).

• Sanktionslisten: Lokaler Abgleich gegen mehrere Datenquellen (u. a.
  EU FSF und OFAC). Hinweis: Dies versteht sich als strukturierte
  Recherchehilfe; es ersetzt keine abschließende rechtliche Prüfung,
  liefert jedoch wertvolle erste Hinweise auf Namens- oder
  Organisationsübereinstimmungen. Aus Datenschutzgründen (DSGVO) ist
  eine Fuzzy-/Ähnlichkeitssuche bewusst deaktiviert; gesucht wird
  ausschließlich auf exakte Treffer.

Zusätzlich finden Sie auf der Plattform praxisnahe Beispiele für den
Einsatz eines lokal betriebenen Sprachmodells (LLM) in typischen
Prüfungssituationen (u. a. Dokumentenanalyse, Checklistenarbeit,
Berichtsentwürfe, Halluzinations-Demonstration und das Durchsuchen
eigener Belege).


Wichtiger Hinweis zur Trägerschaft
==================================

Dieses Angebot ist ein rein privates, nicht-kommerzielles Vorhaben von
Jan Riener als Privatperson. Die Hessische Prüfbehörde EFRE ist weder
Veranstalterin noch Verantwortliche und tritt nicht als
Datenverarbeiterin auf. Die Inhalte und die Plattform stehen in keinem
dienstlichen Zusammenhang.

Datensicherheit: Bitte geben Sie auf der Plattform keine echten
produktiven Vorhabens- oder Begünstigtendaten ein. Alle Recherchen
arbeiten ausschließlich mit öffentlich zugänglichen Datenquellen.


Datenschutz, Auswertung und Widerruf
====================================

Verantwortlicher (i.S.d. Art. 4 Nr. 7 DSGVO): Jan Riener,
administration@vwvg.de.

Datenverarbeitung: Verarbeitet werden ausschließlich die von Ihnen selbst
eingegebenen Daten (Name, E-Mail, Behörde, Bundesland, Funktion sowie ggf.
eingegebene Texte).

Infrastruktur: Server- und LLM-Aufrufe werden zu Auswertungszwecken
pseudonymisiert protokolliert. Die LLM-Verarbeitung selbst erfolgt
ausschließlich auf privater Hardware (EVO-X2 in Deutschland) und explizit
nicht in einer Cloud.

Widerruf: Sie können Ihre Einwilligung jederzeit widerrufen und die
Löschung Ihres Kontos verlangen — formlos per E-Mail an
administration@vwvg.de.

Weitere Details unter {{ public_url }}/datenschutz und
{{ public_url }}/impressum.


Sollten Sie diese E-Mail unerwartet erhalten haben oder die Plattform
nicht nutzen wollen, antworten Sie einfach auf diese Nachricht — ich
werde Ihr Konto dann umgehend löschen.

Mit freundlichen Grüßen
Jan Riener

—
Diese Nachricht wurde automatisch erzeugt, der Absender ist privat.
Bei technischen Rückfragen: administration@vwvg.de.
""",
    },

    "signup_alert": {
        "description": (
            "Benachrichtigung an ADMIN_NOTIFY_EMAIL bei Selbst-Registrierung "
            "über /api/auth/signup (Status pending_approval). Der Admin muss "
            "den Account anschließend im AdminPanel freischalten."
        ),
        "subject": "Neue Selbst-Anmeldung: {{ first_name }} {{ last_name }} ({{ organization }})",
        "placeholders": [
            "first_name", "last_name", "email", "organization", "bundesland",
            "function_role", "signup_reason", "user_id", "public_url",
        ],
        "body": """\
Neue Selbst-Anmeldung — wartet auf Freischaltung

Name        : {{ first_name }} {{ last_name }}
E-Mail      : {{ email }}
Organisation: {{ organization or '–' }}
Bundesland  : {{ bundesland or '–' }}
Funktion    : {{ function_role or '–' }}
{% if signup_reason %}
Begründung der/des Anmeldenden:
{{ signup_reason }}
{% endif %}
Registrierungs-ID: {{ user_id }}

Bitte im Admin-Bereich prüfen und freischalten:
{{ public_url }}/admin (Tab „Benutzer", Filter „Wartet auf Freigabe")
""",
    },
}


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


# ── Template-Lookup (DB-Override mit Default-Fallback) ──────────────────────

def get_template(key: str) -> tuple[str, str]:
    """Liefert (subject, body) aus der DB, fällt sonst auf DEFAULT_TEMPLATES.

    Wirft KeyError, falls der Key auch im Default unbekannt ist — das ist ein
    Programmfehler, kein Laufzeit-Fall.
    """
    default = DEFAULT_TEMPLATES.get(key)
    if not default:
        raise KeyError(f"Unbekanntes Mail-Template: {key!r}")

    # DB-Lookup: best-effort, eine Fehlermeldung darf den Mailversand nicht
    # killen. Bei Lookup-Fehler nutzen wir den Default.
    try:
        from database import SessionLocal
        from models.registration import EmailTemplate
        with SessionLocal() as db:
            row = db.query(EmailTemplate).filter(EmailTemplate.key == key).first()
            if row and row.subject and row.body:
                return row.subject, row.body
    except Exception:  # noqa: BLE001 — DB-Hiccup darf Mailversand nicht blocken
        log.exception("DB-Lookup für Mail-Template %r fehlgeschlagen — fahre mit Default fort.", key)

    return str(default["subject"]), str(default["body"])


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


def _render(key: str, context: dict) -> tuple[str, str]:
    """Lädt (subject, body) für `key` und rendert beide mit `context`."""
    subject_tmpl, body_tmpl = get_template(key)
    subject = _jinja.from_string(subject_tmpl).render(**context).strip()
    body = _jinja.from_string(body_tmpl).render(**context)
    return subject, body


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

    subject, body = _render("confirmation", {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "organization": organization,
        "department": department,
        "fund": fund,
        "ai_paragraph": ai_paragraph,
        "workshop_title": workshop_title,
        "public_url": config.EMAIL_PUBLIC_URL.rstrip("/"),
        "reply_to": config.SMTP_FROM,
        "organizer": config.SMTP_FROM_NAME,
    })
    msg = _build_message(
        to_addr=email,
        subject=subject,
        body_text=body,
        reply_to=config.SMTP_FROM,
    )
    return await _send_message(msg)


async def send_account_invite(
    *,
    first_name: str,
    last_name: str,
    email: str,
    setup_url: str,
) -> bool:
    """Sendet die Einladungsmail mit Setup-Link.

    `setup_url` ist die vollständige absolute URL inkl. Token-Query,
    z.B. https://workshop.flowaudit.de/account/setup-password?token=…
    """
    if not is_configured():
        return False

    subject, body = _render("invite", {
        "first_name": first_name,
        "last_name": last_name,
        "setup_url": setup_url,
        "public_url": config.EMAIL_PUBLIC_URL.rstrip("/"),
    })
    msg = _build_message(
        to_addr=email,
        subject=subject,
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

    subject, body = _render("admin_notify", {
        "registration_id": registration_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "organization": organization,
        "department": department,
        "fund": fund,
        "confirmation_sent": confirmation_sent,
        "ai_consent": ai_consent,
        "public_url": config.EMAIL_PUBLIC_URL.rstrip("/"),
    })
    msg = _build_message(
        to_addr=config.ADMIN_NOTIFY_EMAIL,
        subject=subject,
        body_text=body,
        reply_to=email,
    )
    return await _send_message(msg)


async def send_signup_alert(
    *,
    user_id: str,
    first_name: str,
    last_name: str,
    email: str,
    organization: str | None,
    bundesland: str | None,
    function_role: str | None,
    signup_reason: str | None,
) -> bool:
    """Benachrichtigt ADMIN_NOTIFY_EMAIL über eine Selbst-Anmeldung
    (pending_approval). Wird vom /api/auth/signup-Endpoint aufgerufen.
    """
    if not is_configured() or not config.ADMIN_NOTIFY_EMAIL:
        return False

    subject, body = _render("signup_alert", {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "organization": organization,
        "bundesland": bundesland,
        "function_role": function_role,
        "signup_reason": signup_reason,
        "public_url": config.EMAIL_PUBLIC_URL.rstrip("/"),
    })
    msg = _build_message(
        to_addr=config.ADMIN_NOTIFY_EMAIL,
        subject=subject,
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
