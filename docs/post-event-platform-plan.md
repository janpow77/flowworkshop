# Plan: Workshop-Plattform nach der Veranstaltung

> **Status:** v3.2 (final, freigabebereit)
> **Stand:** 2026-05-07
> **Autor:** Jan Riener · Konzept gemeinsam mit Claude Opus 4.7
> **Nicht implementiert.** Dieses Dokument beschreibt nur, *was* gebaut werden soll.

---

## 0. Kontext

Heute läuft die Plattform unter `workshop.flowaudit.de` als Live-Demo-Umgebung
für den **Prüferworkshop 2026 in Hannover** (19./20. Mai 2026). 22 Teilnehmer
aus deutschen und einer österreichischen Behörde haben Workshop-Tokens.

Nach der Veranstaltung soll die Plattform weiterleben als **Wissensplattform
mit Forum, Dokumenten-Bereich und Tagesordnungs-Archiv**, weiterhin unter
derselben Domain.

Dieses Dokument beschreibt die Architektur, die Phasen und die offenen Punkte.

---

## 1. Entscheidungen aus den Anwender-Antworten

| # | Entscheidung |
|---|---|
| Domain | Bleibt `workshop.flowaudit.de` (kein Subdomain-Split) |
| Login | **Neu**: Selbstanmeldung + Admin-Approval, Passwort-basiert |
| Daten-Lebenszeit | Nicht löschen, aber DSGVO-Rechte (Auskunft, manuelle Löschung) bleiben erfüllt |
| Newsletter / Mailings | Erstmal nein — nur Auth-Mails (Verify, Reset, Approval) |
| RAG-Indexierung | Phase 7 / „später" |
| Storage-Cap | 5 GB lokal, Quota 200 MB / User (1 GB Mod, unlimitiert Admin) |
| Export zentral | Ja — `useExport`-Hook, Wechsel von `html2canvas` auf OKLCH-fähige Lib |
| Initial-Admin | `jan.riener@wirtschaft.hessen.de` |
| Pflichtfelder bei Anmeldung | E-Mail, Passwort, Vor-/Nachname, Behörde, Bundesland, Funktion |
| Avatare | Upload max 2 MB + Initialen-Fallback (deterministische Farbe) |
| Geteilt-Bereich | Flach, ein Ordner mit Filter-Chips (Bundesland, Tags, Typ) |
| Phase-Wechsel `live ↔ post` | Manuell durch Admin-Klick |
| Bestehende Nutzer | In-place-Migration, alter Token gilt 30 Tage parallel |
| Bundesländer-Liste | DE (16) + Bund + AT (9) + Bund (Österreich) = **27 Optionen** |

---

## 2. Architektur-Übersicht

```
┌─────────────────────────── workshop.flowaudit.de ──────────────────────────┐
│                                                                             │
│  Frontend (React 19, Tailwind 4, Vite 8)                                    │
│  ├── Public  : /, /agenda, /forum (read), /register, /login, /vorstellung  │
│  └── Member  : /docs, /scenario/*, /admin/*, …                             │
│                                                                             │
│  Backend (FastAPI)                                                          │
│  ├── /api/auth/*     ← NEU: signup, login, verify-email, reset-pw          │
│  ├── /api/users/*    ← NEU: admin-approval, profile, sessions              │
│  ├── /api/forum/*    ← NEU: kategorien, threads, posts, reactions, tags    │
│  ├── /api/docs/*     ← NEU: folders, files, versions, quota                │
│  ├── /api/event/*       (bestehend, erweitert um phase/archive-mode)       │
│  ├── /api/beneficiaries/* (bestehend)                                      │
│  └── …                                                                      │
│                                                                             │
│  PostgreSQL 16 + pgvector       (bestehend, erweitert um 11 neue Tabellen) │
│  Storage Local Bucket            backend/data/documents/  (5 GB cap)       │
│  ClamAV-Sidecar (Phase 3)        scannt Uploads via socket                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Auth-System (Phase 0) — **OHNE Mail-Schicht**

> **Entscheidung 2026-05-07:** Kein SMTP, kein Mail-Versand aus der App.
> Begründung: zu viel Setup-Aufwand (DNS/DKIM/Reputation) für 22 Teilnehmer.
>
> **Konsequenzen:**
> - Keine E-Mail-Verifikation beim Signup (E-Mail wird trotzdem als
>   Pflichtfeld gespeichert; Admin prüft sie beim Approval)
> - Passwort-Reset läuft über Admin-Generated-Token, nicht per Mail
> - Migration der bestehenden Nutzer ohne automatische Setup-Mail
> - Notifications nur intern (Bell-Icon), keine Mailbenachrichtigung

### 3.1 Flows

#### Selbstregistrierung (ohne Mail-Verify)
```
1. /register → Formular:
     E-Mail (Pflicht, validiert)
     Passwort (≥10 Z., ≥1 Sonderz., ≥1 Ziffer)
     Vor-/Nachname · Behörde · Bundesland · Funktion
     Begründung der Anmeldung (Pflichtfeld bei externer Domain, sonst optional)
     Einwilligung Datenschutz (Checkbox, Pflicht)
2. POST /api/auth/signup
     Backend: User-Eintrag mit status='pending_approval'
     KEIN Mail-Versand — Antwort: „Anmeldung eingegangen, wird vom
     Admin geprüft. Nach Freischaltung können Sie sich einloggen."
3. Admin sieht in /admin/users die Pending-Queue mit allen Daten,
   inkl. Cross-Check der E-Mail-Domain
4. Admin klickt „Genehmigen" → status='active'
   (Optional: Admin kann Magic-Login-Link generieren + manuell per
    Outlook/Slack an den User schicken — One-Click-Variante)
5. User loggt sich unter /login mit E-Mail + Passwort ein → Session-Cookie
```

#### Login
- E-Mail + Passwort (Argon2id-gehasht, 64 MB / 3 iterations / 4 parallelism)
- Rate-Limit: 5 Versuche / 15 Min pro IP, 10 / Stunde pro E-Mail
- Lockout nach 10 fehlgeschlagenen Versuchen für 30 Min, mit Reset-Mail-Hinweis

#### Passwort-Reset (ohne Mail)
- User klickt auf `/login` „Passwort vergessen?" → Modal:
  „Bitte den Admin (jan.riener@…) kontaktieren. Sie erhalten dann
  einen einmaligen Reset-Link."
- Admin sieht in `/admin/users` Spalten-Aktion „Passwort-Reset-Link
  generieren" → Link mit 24-h-Token wird **nicht versendet**, sondern
  in einem Modal angezeigt zum Kopieren
- Admin schickt Link manuell per Outlook/Slack/persönlich
- User öffnet Link → setzt neues Passwort → alle Sessions werden invalidiert
- Aufwand für Admin: ~30 Sek pro Reset, bei 22 Teilnehmern handhabbar

#### Sessions
- DB-backed (Tabelle `user_session`), Cookie `auditworkshop_sid` HttpOnly + Secure + SameSite=Lax
- Lifetime: 30 Tage Sliding Expiration; Refresh bei jedem authenticated Request
- Logout: Cookie clearen + DB-Eintrag löschen
- Admin kann fremde Sessions invalidieren

#### 2FA (optional, Phase 0.5)
- TOTP per Authenticator-App, **Pflicht für Admin-Rolle**, freiwillig für andere

### 3.2 Datenmodell

```python
class User(Base):
    id: UUID  PK
    email: str  UNIQUE
    email_verified_at: datetime | None
    password_hash: str  # Argon2id
    first_name: str
    last_name: str
    organization: str
    bundesland: str | None  # DE+AT+Bund
    function_role: str | None
    signup_reason: str | None
    role: Enum('attendee'|'moderator'|'admin')  default='attendee'
    status: Enum('email_unverified'|'pending_approval'|'active'|'rejected'|'suspended')
    rejection_reason: str | None
    created_at, approved_at, last_login_at: datetime
    avatar_path: str | None
    quota_bytes: int  default=200*1024*1024
    used_bytes: int  default=0
    totp_secret: str | None  # bei 2FA aktiv
    deleted_at: datetime | None  # Soft-Delete; Daten bleiben anonymisiert

class UserSession(Base):
    id: str  # zufälliger Token, in Cookie
    user_id: UUID  FK
    created_at, last_seen_at, expires_at: datetime
    user_agent, ip_hash: str

class EmailToken(Base):
    id, user_id, kind ('verify'|'reset'|'invite'), token_hash,
    expires_at, used_at: datetime

class AuditLog(Base):
    id, user_id (actor), action, target_type, target_id,
    metadata_json, ip_hash, created_at
```

### 3.3 Berechtigungs-Matrix

| Aktion | attendee | moderator | admin |
|---|:-:|:-:|:-:|
| Forum lesen (öffentliche Threads) | ✓ | ✓ | ✓ |
| Forum lesen ohne Login | ✓ (read-only) | ✓ | ✓ |
| Thread/Post schreiben | ✓ | ✓ | ✓ |
| Thread anpinnen / sperren / `solved` markieren | – | ✓ | ✓ |
| Fremden Post löschen | – | ✓ | ✓ |
| Eigene Datei hochladen (in „Geteilt"-Bereich) | ✓ | ✓ | ✓ |
| Datei in beliebigem Ordner hochladen | – | ✓ | ✓ |
| Ordner anlegen | – | ✓ | ✓ |
| Eigene Datei löschen (≤24 h) | ✓ | ✓ | ✓ |
| Fremde Datei löschen | – | ✓ | ✓ |
| User genehmigen / suspendieren | – | – | ✓ |
| Rollen ändern | – | – | ✓ |
| Audit-Log einsehen | – | eigener Bereich | ✓ |
| Phase-Schalter (`live` ↔ `post`) | – | – | ✓ |

### 3.4 Bundesland-Whitelist (Pflichtfeld)

```
Deutschland:
  Baden-Württemberg, Bayern, Berlin, Brandenburg, Bremen, Hamburg, Hessen,
  Mecklenburg-Vorpommern, Niedersachsen, Nordrhein-Westfalen, Rheinland-Pfalz,
  Saarland, Sachsen, Sachsen-Anhalt, Schleswig-Holstein, Thüringen,
  Bund (BMI, BAMF, BKA, etc.)

Österreich:
  Burgenland, Kärnten, Niederösterreich, Oberösterreich, Salzburg, Steiermark,
  Tirol, Vorarlberg, Wien, Bund (Österreich)
```

`services/country_profiles.py` ist die Single Source of Truth — nutzt
sowohl der Begünstigtenkarten-Filter (`BL_COLORS`), die Geocoding-Heuristik
(`_state_from_proper_nouns`), als auch das neue Auth-Profil-Feld.

### 3.5 Edge Cases & Sicherheit

- Passwort-Strength: zxcvbn-Score ≥3 als Anforderung
- HIBP-Check: optional Pwned-Passwords via k-Anonymity-API
- CSRF: Double-Submit-Cookie für state-changing Requests
- HTTPS-only: Cookies `Secure`, HSTS-Header
- Mail: SPF + DKIM + DMARC für `noreply@workshop.flowaudit.de`
- Brute-Force: stets 200 ms Delay bei Login-Antwort
- DSGVO: Audit-Log enthält gehashte IP (SHA256+Salt)

### 3.6 Mail-Schicht — **ENTFÄLLT**

Bewusste Entscheidung: kein Mail-Versand aus der App. Stattdessen:
- Approval-Hinweis erscheint im Web-UI nach Signup
- Magic-Login-Link / Reset-Link werden im Admin-UI generiert und
  manuell an den User weitergeleitet (Outlook/Slack/persönlich)
- Notifications laufen über Bell-Icon im UI (siehe §6 / Phase 6)

Spart: SMTP-Provider, DNS-DKIM-Setup, Reputation-Aufbau, Mail-Queue,
Bounce-Handling — insgesamt geschätzt ~6 h Plan-/Setup-Aufwand.

---

## 4. Migration der bestehenden Nutzer

**Stand DB heute:** 23 Workshop-Registrierungen, alle mit E-Mail + Token,
**niemand hat bisher ein Passwort** (Token-only), 11 sind mindestens einmal
eingeloggt.

### 4.1 Strategie: in-place erweitern, nicht kopieren

`workshop_registrations` hat schon `email`, `password_hash`, `last_login_at`.
Sie wird **erweitert zur neuen `users`-Tabelle**.

```sql
-- 1. Spalten erweitern
ALTER TABLE workshop_registrations
  ADD COLUMN role          varchar(16)   DEFAULT 'attendee',
  ADD COLUMN status        varchar(20)   DEFAULT 'active',
  ADD COLUMN bundesland    varchar(64),
  ADD COLUMN function_role varchar(80),
  ADD COLUMN signup_reason text,
  ADD COLUMN avatar_path   varchar(255),
  ADD COLUMN quota_bytes   bigint        DEFAULT 209715200,    -- 200 MB
  ADD COLUMN used_bytes    bigint        DEFAULT 0,
  ADD COLUMN totp_secret   varchar(64),
  ADD COLUMN email_verified_at timestamp DEFAULT now(),
  ADD COLUMN approved_at   timestamp     DEFAULT now(),
  ADD COLUMN deleted_at    timestamp,
  ADD COLUMN rejection_reason text;

-- 2. Existing-User-Defaults
UPDATE workshop_registrations
   SET role     = 'attendee',
       status   = 'active',
       email_verified_at = COALESCE(last_login_at, created_at),
       approved_at       = COALESCE(created_at, now());

-- 3. Initial-Admin
UPDATE workshop_registrations
   SET role = 'admin',
       quota_bytes = 9223372036854775807   -- ~unlimitiert
 WHERE lower(email) = 'jan.riener@wirtschaft.hessen.de';

-- 4. Tabelle umbenennen, View für Backwards-Compat
ALTER TABLE workshop_registrations RENAME TO users;
CREATE VIEW workshop_registrations AS SELECT * FROM users;
```

### 4.2 Übergangs-Auth

```
                                                    [Phase-0-Deploy]
        vor Migration              währenddessen              danach
   ────────────────────────  ────────────────────────  ────────────────────────
   Login: invite_token       Login: invite_token       Login: 1) E-Mail+Passwort
                                  ODER                          2) ODER alter
                              E-Mail+Passwort                       invite_token
                                                                    (gilt 30 Tage)
```

- Backend akzeptiert für 30 Tage **beide** Auth-Mechanismen parallel
- Beim Login mit altem Token zeigt Frontend einen Banner: „Bitte einmalig ein
  Passwort vergeben (5 Min) — alter Login läuft in N Tagen ab."
- Nach 30 Tagen Auto-Redirect auf Setup-Seite
- Kein Datenverlust, kein Zwang sofort zu reagieren

### 4.3 Profil-Pflichtfelder bei alten Nutzern

Bestehende Nutzer haben kein `bundesland` und kein `function_role`. Lösung:
**sanfter Profil-Komplettierungs-Flow:**

- Login ohne diese Felder weiter möglich
- Beim **ersten Schreib-Vorgang** (Forum-Post, Datei-Upload) wird ein Modal
  vorgeschaltet: „Bitte einmalig dein Profil vervollständigen"
- Lesen + Ansehen ohne Profil-Vervollständigung möglich
- Bestehende `department`-Werte wandern als Vorschlag automatisch ins
  Funktion-Feld

### 4.4 Setup-Link-Verteilung an die 23 Bestandsnutzer

Ohne Mail bleiben drei Optionen:

**A) Banner beim alten Login**
- Bestandsnutzer loggt sich mit altem Token ein
- Banner: „Bitte einmalig Passwort vergeben (5 Min)"
- Klick → `/account/setup-password` → Passwort setzen → fertig
- Funktioniert organisch, keine Admin-Aktion

**B) Admin generiert Setup-Links + verschickt manuell**
- `/admin/users` → Bulk-Aktion „Setup-Links generieren"
- Liste mit 23 Links erscheint (Klartext, nicht gehasht)
- Admin kopiert die Liste → in Outlook-Serien-Mail einpflegen → versenden
- Aufwand: ~10 Min einmalig

**C) Übergangs-Modus über die volle 30-Tage-Frist**
- Alter Token bleibt 30 Tage parallel gültig
- Wer es schafft, das Passwort in der Zeit zu setzen — gut
- Wer nicht: nach 30 Tagen erscheint beim Login Aufforderung „Passwort
  vergeben" → User setzt es da, ohne Admin-Hilfe

**Empfehlung:** A + C kombinieren. B nur wenn Admin proaktiv informieren
will. Kein zwingender Mailrun, alles asynchron + freundlich.

---

## 5. Hub-Startseite (Phase 1)

Kachel-Grid 3×3 Desktop, 1-spaltig mobil:

```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  📚 FORUM   │ │  📁 DOCS    │ │  🗓 ARCHIV  │
│  152 Posts  │ │  89 Dateien │ │  Programm   │
│  3 unread   │ │  Letzte: …  │ │  Tag 1+2    │
└─────────────┘ └─────────────┘ └─────────────┘
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 🗺 BEGÜNST. │ │ 🛡 SANKTION.│ │ 📖 WISSEN   │
│ 72k Vorhaben│ │  EU FSF     │ │  RAG (soon) │
└─────────────┘ └─────────────┘ └─────────────┘
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 🧪 SZENARIEN│ │ 👥 TEILN.   │ │ 🔔 NEUES    │
│ Demo 1–7    │ │  22 aktiv   │ │  3 Beiträge │
└─────────────┘ └─────────────┘ └─────────────┘
```

Im **Live-Modus** bleibt die jetzige HomePage; im **Archiv-Modus** wird sie
durch die Hub-Kacheln ersetzt. Schalter: `event.phase` (`live` | `post`).

### 5.4 Landing-Page (öffentliche Startseite)

Die heutige Login-Seite ist nur ein E-Mail-Eingabefeld. Sie wird zur
**öffentlichen Landing-Page** umgebaut mit drei Bereichen:

```
┌─────────────────────────────────────────────────────────────┐
│        [EU-Logo]   Prüferworkshop 2026 · Plattform          │
│                                                             │
│  ┌──────────────────────┐    ┌───────────────────────────┐ │
│  │ ANMELDEN             │    │ ÖFFENTLICHE AUSWERTUNGEN  │ │
│  │ E-Mail   [______]    │    │ ─────────────────────────  │ │
│  │ Passwort [______]    │    │  ┌──────────┐ ┌─────────┐│ │
│  │       [ Anmelden ]   │    │  │  🗺      │ │  🛡    ││ │
│  │ ─ oder ─             │    │  │BEGÜNST.  │ │SANKTION.││ │
│  │ Noch kein Konto?     │    │  │ Karte    │ │ Suche   ││ │
│  │  → Registrieren      │    │  │ 72k VH   │ │ EU FSF  ││ │
│  │ Passwort vergessen?  │    │  └──────────┘ └─────────┘│ │
│  │  → Reset             │    │  Frei zugänglich nach     │ │
│  └──────────────────────┘    │  Art. 49 VO (EU) 2021/1060 │ │
│                              └───────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Verhalten:**
- Nicht-eingeloggte Nutzer landen auf `/` → sehen Landing
- Klick auf Begünstigten-Kachel → öffentliches `/scenario/6` (read-only)
- Klick auf Sanktionslisten-Kachel → öffentliches `/sanktionslisten`
- Eingeloggte Nutzer: sofort zum Hub (Live oder Archiv, je nach Phase)

### 5.5 Public vs. Member: klare Trennung

| Pfad | Public | Member |
|---|:-:|:-:|
| `/` (Landing) | ✓ | ✓ → Hub-Redirect |
| `/scenario/6` (Begünstigte) | ✓ | ✓ |
| `/sanktionslisten` (Sanktionen) | ✓ | ✓ |
| `/agenda` | ✓ | ✓ |
| `/forum` (lesen) | ✓ | ✓ |
| `/forum/new`, Posten/Reagieren | – | ✓ |
| `/scenario/1–5` (LLM-Compute) | – | ✓ |
| `/docs` | – | ✓ |
| `/account/*`, `/admin/*` | – | ✓ |

**Banner auf Public-Pages** (wenn nicht eingeloggt):
> ℹ Sie sehen die öffentliche Ansicht. Mit Workshop-Konto: Forum-
> Diskussion, Dokumente, Demo-Szenarien, eigene Auswertungen
> speichern. [Anmelden] [Registrieren]

### 5.6 Drosseln im Public-Modus

| Funktion | Drossel |
|---|---|
| Begünstigtenkarte | keine — Daten sind öffentlich nach Art. 49 |
| Sanktions-Suche | 30 Anfragen pro IP / Stunde (gegen Bot-Scraping) |
| LLM-Endpoints (`/api/workshop/stream`) | bleibt member-only — Compute-Kosten |

### 5.7 Backend-Auth-Anpassungen

| Endpoint | heute | Plan |
|---|---|---|
| `GET /api/beneficiaries/map` | requires Token | **public öffnen** |
| `GET /api/beneficiaries/sources` | requires Token | **public öffnen** |
| `GET /api/sanctions/lists` | public ✓ | bleibt |
| `GET /api/sanctions/search` | public ✓ + Rate-Limit | bleibt |
| `POST /api/workshop/stream` | requires Token | bleibt member |
| `GET /api/forum/threads` | requires Token | **public öffnen** (read-only) |
| `POST /api/forum/threads` | requires Token | bleibt member |

**Admin-UI für den Phase-Wechsel:**

```
┌────────────────────────────────────────────────────────────┐
│ Veranstaltungs-Modus                            ● LIVE     │
├────────────────────────────────────────────────────────────┤
│ Aktuell: LIVE-Modus                                        │
│   Sidebar mit Szenarien · Hub-Kacheln deaktiviert          │
│   Tagesordnung interaktiv · Anmeldung offen                │
│                                                            │
│ Wenn du auf ARCHIV umstellst:                              │
│   • Hub-Kacheln werden Startseite                          │
│   • Tagesordnung wird read-only                            │
│   • Forum + Dokumente bleiben aktiv                        │
│   • Szenarien bleiben als Demo-Lernumgebung                │
│   • Live-Anmeldung schließt; neue Anmeldung weiterhin      │
│     möglich, läuft durch Admin-Approval                    │
│                                                            │
│              [ Auf ARCHIV-Modus umstellen ]                │
└────────────────────────────────────────────────────────────┘
```

---

## 6. Forum (Phase 2) — professioneller Diskurs-Stil

### 6.1 Hierarchie

```
Forum
├── Kategorie  (z. B. "Workshop 5 · KI für EFRE-Prüfung")
│   ├── Thread (Topic)
│   │   ├── Eröffnungspost (Top-Post)
│   │   ├── Reply 1 (mit Quote, Reactions, Edit-Historie)
│   │   ├── Reply 2
│   │   └── ...
│   └── Thread 2
└── Kategorie ...
```

### 6.2 Übersicht (`/forum`)

```
┌─────────────────────────────────────────────────────┐
│ Forum                                  [+Neuer Thread]│
├─────────────────────────────────────────────────────┤
│ Filter: Latest · Top · Unread · Mine    [🔍 Suche…] │
├─────────────────────────────────────────────────────┤
│ [📌][✓] Wie umgehen mit … (Workshop 5)             │
│        12 Antworten · 47 Aufrufe · vor 2 Std       │
│                              👍 8  💡 3  🤔 1       │
├─────────────────────────────────────────────────────┤
│       Welche Spalten in der … (Tag 1)               │
│        4 Antworten · 23 Aufrufe · vor 1 Tag         │
└─────────────────────────────────────────────────────┘
```

### 6.3 Thread-Ansicht

- Eröffnungspost prominent oben (Titel, Tags, Autor, Datum, Kategorie-Breadcrumb)
- Antworten chronologisch, Avatar links, Inhalt rechts
- Pro Post: Reaktionen (👍 Hilfreich, 💡 Aha, 🤔 Frage, ❤️ Danke), Quote-Button,
  Antworten-auf-Post, Bearbeiten (eigene), Melden
- Markdown + Code-Blöcke + Tabellen + `@mention`
- Lese-Position-Tracking
- Sticky Reply-Box mit Markdown-Editor + Datei-Anhang per Drop

### 6.4 Datenmodell

```python
class ForumCategory:
  id, slug, name, description, icon, color, parent_id, order, archived

class ForumThread:
  id, slug, category_id, title, body_md, author_user_id,
  created_at, last_post_at, post_count, view_count,
  pinned, locked, solved, agenda_item_id (optional, für Migration)

class ForumPost:
  id, thread_id, parent_post_id (für quoting), author_user_id,
  body_md, created_at, updated_at, edit_count, deleted_at

class ForumReaction:
  post_id, user_id, kind ("hilfreich"|"aha"|"frage"|"danke")

class ForumTag, ForumThreadTag (m:n)
class ForumReadState: thread_id, user_id, last_read_post_id, last_read_at
class ForumPostRevision: post_id, revision_no, body_md, edited_at
```

### 6.5 URL-Schema

```
/forum                                       Übersicht aller Kategorien + Latest
/forum/c/:category-slug                      Threads einer Kategorie
/forum/t/:thread-slug-:id                    Thread-Detail
/forum/u/:username                           Profil + Beiträge eines Nutzers
/forum/tags/:tag                             Threads mit Tag
/forum/new?c=…                               Neuer Thread im Kontext
```

### 6.6 API

```
GET    /api/forum/categories
GET    /api/forum/threads?category=X&tag=Y&filter=unread&sort=latest&q=...
GET    /api/forum/threads/:id
POST   /api/forum/threads                     (auth)
PATCH  /api/forum/threads/:id                 (eigene oder Mod)
POST   /api/forum/threads/:id/posts           (auth)
PATCH  /api/forum/posts/:id                   (eigene)
DELETE /api/forum/posts/:id                   (eigene oder Mod)
POST   /api/forum/posts/:id/react             (auth)
DELETE /api/forum/posts/:id/react             (auth)
POST   /api/forum/threads/:id/read            (read-state update)
POST   /api/forum/threads/:id/pin             (mod)
POST   /api/forum/threads/:id/lock            (mod)
POST   /api/forum/threads/:id/solved          (mod oder Threadstarter)
```

### 6.7 Migration

Bestehende `AgendaForumPost` → neue `forum_threads` + `forum_posts` in
Default-Kategorie „Workshop 2026". 1 Agenda-Item = 1 Thread.
Alte Route `/agenda/forum/:itemId` redirected auf neuen Thread.

---

## 7. Dokumente (Phase 3) — CIRCABC-Stil

### 7.1 Standard-Ordnerstruktur

```
📁 Workshop-Material 2026                    public_read, mod-upload
   ├── 📁 Folien
   ├── 📁 Templates (CL, Berichtsvorlagen, Anschreiben)
   ├── 📁 Aufzeichnungen
   └── 📁 Auswertungen
📁 Rechtsgrundlagen                          public_read, mod-upload
   └── (Spiegel der Wissensbasis-PDFs)
📁 Geteilt von Teilnehmern                   members_read, members-upload
   └── (FLACH, mit Filter-Chips: Bundesland, Tags, Typ)
📁 Persönlich                                Sondertyp pro User, members-upload-eigener
   └── 📁 <Vor- Nachname>                    is_user_bucket=True, owner=user
                                             nur lesbar für Owner + Admins
```

### 7.2 Storage-Architektur (5 GB Cap)

```
backend/data/documents/
├── _trash/                                  Soft-Deleted (30 d)
└── <uuid-folder>/<uuid-file>/
    ├── v1.bin                               Original
    ├── v1.meta.json                         {sha256, mime, size, uploader, …}
    ├── v2.bin                               Neue Version
    └── v2.meta.json
```

- Hash-basierter Pfad verhindert Pfad-Traversal
- Versionen Append-only — alte Versionen bleiben (kein Auto-Delete)
- Trash: bei `DELETE /api/docs/files/:id` → Soft-Delete (30 d)
- Versionen-Cap: max 10 Versionen pro Datei → ältere in `_archive/`

### 7.3 Quota & Monitoring

- **attendee**: 200 MB
- **moderator**: 1 GB
- **admin**: unlimitiert
- Quota-Check vor Upload: `400 Quota Exceeded`
- `GET /api/docs/system/usage` für Admin-Dashboard
- Warn-Schwelle: 80 % → Admin-Notification
- Hard-Cap: 5 GB total — bei 95 % blockt Backend Uploads

### 7.4 Datenmodell

```python
class DocumentFolder:
    id, parent_id, name, slug, description, sort_order,
    visibility ('public_read'|'members_read'|'moderators_only'),
    upload_policy ('members'|'moderators'|'none'),
    is_user_bucket: bool   # True bei "Geteilt von <Name>"
    owner_user_id: UUID | None
    created_at, created_by

class DocumentFile:
    id, folder_id, name, slug, mime_type, size_bytes,
    description, tags (jsonb),
    uploader_bundesland: str | None  # snapshot, sticky
    storage_dir, current_version_no,
    uploader_id, uploaded_at,
    download_count: int
    locked_by: UUID | None  # Edit-Lock
    deleted_at, deleted_by

class DocumentVersion:
    id, file_id, version_no, storage_key, size_bytes,
    sha256, uploader_id, uploaded_at, change_note

class DocumentDownloadLog:
    file_id, version_no, user_id, ip_hash, downloaded_at

class DocumentShareToken:
    file_id, token_hash, created_by, expires_at, max_downloads,
    download_count
```

### 7.5 „Geteilt"-Bereich-UI (flach mit Filter-Chips)

```
┌────────────────────────────────────────────────────────────────┐
│ 📁 Dokumente / Geteilt von Teilnehmern        [⤴ Hochladen]   │
├────────────────────────────────────────────────────────────────┤
│ Filter:  [Alle BL ▾]  [Alle Tags ▾]  [Alle Typen ▾]  🔍 …      │
│  Hessen ✕  PDF ✕                                              │
├────────────────────────────────────────────────────────────────┤
│ ☐ Name                              BL    Größe Datum   Vers   │
│ ☐ 📄 Prüfvermerk-Vorlage v3.docx    Hessen 320 KB 14.05 v2 [⋯]│
│ ☐ 📄 PIAV-Stufe-5-Auswertung.xlsx   Bayern 1,2 MB 13.05 v1 [⋯]│
│ ☐ 📄 Zertifikat-Template.pdf        Bund   85 KB  12.05 v1 [⋯]│
└────────────────────────────────────────────────────────────────┘
```

**Filter:**
- `bundesland` (vom Uploader, automatisch gesetzt aus dessen Profil)
- `tags` (vom Uploader frei vergebbar, Auto-Suggest)
- `mime` (PDF, XLSX, DOCX …)
- Volltext-Suche (Name + Tags + Beschreibung)

### 7.6 Vorschau

| Typ | Vorschau |
|---|---|
| PDF | PDF.js (Mozilla, on-page) |
| Bild (JPG/PNG/WebP) | Lightbox |
| XLSX | erste Tabelle als HTML (openpyxl-Renderer) |
| DOCX/PPTX | Vorschaubild (libreoffice, async, Phase 3.5) |
| CSV | rendered Tabelle (Papa Parse) |
| TXT/MD | code-styled |
| Sonstiges | Icon + Download-Button |

### 7.7 API

```
GET    /api/docs/folders                       (Tree)
POST   /api/docs/folders                       (mod)
GET    /api/docs/folders/:id/files
POST   /api/docs/folders/:id/files             (multipart)
GET    /api/docs/files/:id                     (Metadaten)
GET    /api/docs/files/:id/download            (Blob, mit Audit-Log)
GET    /api/docs/files/:id/versions
POST   /api/docs/files/:id/versions            (neue Version)
PATCH  /api/docs/files/:id                     (Name, Tags, Beschreibung)
DELETE /api/docs/files/:id                     (Soft-Delete, 30 d Trash)
POST   /api/docs/files/:id/share               (Share-Token)
GET    /api/docs/system/usage                  (admin only)
```

---

## 8. Tagesordnungs-Archiv (Phase 4)

### 8.1 Was ändert sich

- Read-only-View, klar als „Vergangenheit" markiert
- Pro Punkt: Sprecher, Zeit, **Material-Schublade** (verknüpfte Dokumente
  + Foren-Threads)
- Statistiken oben: Teilnehmerzahl, Anzahl Beiträge, Anzahl hochgeladener
  Dateien
- Zeitstrahl-Layout pro Tag, Vortrag-Notizen, Aufzeichnungen verlinkt

### 8.2 Verknüpfung

- `agenda_item.related_thread_ids[]` (m:n)
- `agenda_item.related_file_ids[]` (m:n)
- Tab-Reiter pro Item: **Beiträge** (n) · **Dateien** (n) · **Notizen**

### 8.3 Layout

```
┌─────────────────────────────────────────────────────┐
│ Tag 1 — Dienstag, 19.05.2026                        │
├─────────────────────────────────────────────────────┤
│ 09:00–09:30  Begrüßung                              │
│              Sprecher: Jan Riener                   │
│              [📂 2 Dateien] [💬 0 Beiträge]         │
├─────────────────────────────────────────────────────┤
│ 09:30–10:30  Workshop 1: Methoden                   │
│              [📂 5 Dateien] [💬 12 Beiträge] [▶]   │
└─────────────────────────────────────────────────────┘
```

---

## 9. Zentraler Export (Phase 5)

### 9.1 Library-Wechsel

`html2canvas@1.4.1` versteht keine OKLCH-Farbfunktionen (Tailwind v4).
Wechsel auf **`html-to-image`**:

- nativ OKLCH-fähig (nutzt SVG `foreignObject`)
- 70 % kleinerer Bundle (kein eigenes DOM-Re-Rendering)
- Async-API, ähnliche Aufruf-Form

Alternativ: `html2canvas-pro` (Fork mit OKLCH-Support).

### 9.2 Custom Hook

```ts
// useExport.ts
function useExport() {
  return {
    toPng: async (ref: RefObject<HTMLElement>, opts) => …,
    toJpeg: async (ref, opts) => …,
    toPdf: async (ref, opts: { title, headerLine? }) => …,
    toCsv: (rows, header, filename) => …,
    toZip: async (files) => …,  // für Bulk-Download in Documents
  };
}
```

### 9.3 Wo verwendet

- `BeneficiaryMap` (Karte) — bestehender OKLCH-Bug
- `ForumThreadView` → PDF-Export der Diskussion
- `DocumentsTable` → CSV/PDF der Dateiliste, ZIP-Download für Bulk-Select
- `AgendaArchive` → PDF der Tagesordnung mit allen Ressourcen

---

## 10. DSGVO ohne Auto-Löschung

| Recht | Umsetzung |
|---|---|
| Auskunft (Art. 15) | Self-Service unter `/account/data-export` → ZIP mit JSON aller Daten + Dateien |
| Löschung (Art. 17) | User kann eigenen Account löschen → Beiträge bleiben pseudonymisiert (Author=„Anonym"), Uploads gehen in Admin-Trash |
| Datenübertragbarkeit (Art. 20) | derselbe Export wie Art. 15 |
| Widerspruch (Art. 21) | Kontakt-Mail im Footer + Admin kann Account suspendieren |
| AVV | Vertrag mit Hosting + SMTP-Provider |
| Datenschutzerklärung | aktualisierte `/datenschutz`-Seite |

Audit-Log behält gehashte IPs für 6 Monate; danach Auto-Anonymisierung
(IP-Hash → null), Aktion bleibt.

---

## 11. Avatare

**Drei Quellen, deterministischer Fallback:**

1. **Hochgeladenes Bild** (User-Profil → „Avatar ändern")
   - Max 2 MB, JPG/PNG/WebP
   - Server-side resize 256×256, EXIF strip
   - Pfad `data/avatars/<user_id>.<ext>`, gecached durch nginx
2. **Gravatar als Bonus** (optional Checkbox „Gravatar nutzen")
   - MD5 der E-Mail → `https://gravatar.com/avatar/<hash>?s=256&d=identicon`
3. **Initialen-Tile** als Fallback
   - Vor- + Nachname-Initialen
   - Hintergrundfarbe deterministisch aus `sha256(email).hex[:6]` → HSL pastell
   - 100 % statisch im Frontend, kein Backend-Roundtrip

```
POST   /api/users/me/avatar   (multipart)
DELETE /api/users/me/avatar
```

Frontend-Komponente `<Avatar user={…} size="sm|md|lg" />`.

---

## 12. Phasenplan

| Sprint | Inhalt | h | DoD |
|---|---|---:|---|
| ~~A1~~ | ~~Mail-Setup-Klärung~~ | — | **entfällt** (kein Mail) |
| **A2** | **Phase 0 Auth-System** (User, Sessions, Approval, Magic-Link via Admin-UI, Migration alter Tokens) | 7–9 | Login End-to-End, Admin generiert Setup-Links, alter Token migriert |
| **A3** | **Phase 5 Export-Lib** (parallel) — `html-to-image` + `useExport` | 2–3 | Karten-Export erzeugt PNG + PDF |
| **B1** | **Phase 1 Hub-Kacheln** + `event.phase`-Toggle + Admin-UI + Landing-Page | 5–6 | Phase-Wechsel sichtbar, Hub live, Public-Tools auf Landing |
| **B2** | **Phase 2 Forum-Redesign** | 6–7 | Diskurs-Stil, Migration alter Posts |
| **C1** | **Phase 3 Dokumente** | 7–8 | Upload, Versionen, Download, Quota |
| **C2** | **Phase 3.5 Auto-Harvest** (Beneficiaries monatlich + Sanktionen täglich + LLM-Frage-Log) | 5–6 | Cron läuft, Admin-Dashboard zeigt Verlauf |
| **D1** | **Phase 4 Archiv-Tagesordnung** mit Material-Verknüpfung | 3–4 | Klick auf Programm-Punkt zeigt Material |
| **D2** | **Phase 6 Notification-Center** (Bell, intern) | 2 | Ungelesen-Indikator in Hub-Kacheln |
| ~~E~~ | Phase 7 RAG (später) | 4–6 | semantische Suche |
| ~~E~~ | Phase 8 Optional 2FA für Admin | 2 | TOTP+Recovery |

**Total bis Phase 6:** ~37–45 h Entwicklung über 6–8 Werktage. Mail-Wegfall
spart ~2 h direkten Setup-Aufwand, Auto-Harvest und LLM-Logging kommen
zusätzlich rein.

---

## 13. Risiken & Mitigations

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|
| Mail-Versand klappt nicht | mittel | hoch (Login blockiert) | externer SMTP mit SPF/DKIM/DMARC; Magic-Link-Resend; Stub-Mode für Dev |
| 5 GB reichen nicht | mittel | mittel | Hard-Cap + Admin-Notification bei 80 %; Migration zu MinIO bleibt offen |
| Markdown-XSS | mittel | hoch | DOMPurify; kein raw-HTML; Image-Loader per Same-Origin-Proxy |
| ClamAV-Komplexität | mittel | niedrig | Phase 3.5 — MVP mit MIME-Allowlist + sha256-Blocklist |
| Migration alter Tokens | mittel | hoch | Skript dry-run + Rollback; alter Token bleibt 30 d parallel |
| Forum-Spam | niedrig | niedrig | Approval-Flow + Post-Rate-Limit |
| OKLCH-Bug pflanzt sich fort | niedrig | mittel | Phase 5 zentrale Export-Lib |
| DB-Performance | niedrig | mittel | Indexe + PostgreSQL-FTS |

---

## 14. Anti-Goals

- Echtzeit-Chat / WebSockets — Forum reicht
- Volltextsuche jenseits PG-FTS — keine Elasticsearch
- DAM mit Bildbearbeitung — nur Storage + Vorschau
- Wiki — Forum + Dokumente erfüllen den Zweck
- OAuth/SSO — eigenes Login reicht
- Mobile App — responsive Web reicht

---

## 15. Offene Fragen, bevor Implementation startet

1. SMTP-Provider final (Brevo / Hetzner / Mailgun)?
2. Sender-Adresse final (`noreply@workshop.flowaudit.de`?)
3. Sprint A2 jetzt starten mit Magic-Link-Stub (Mail kommt nach)?
4. Sprint A3 (Export-Lib) parallel als Hot-Fix?

---

## 16. Begünstigtenverzeichnisse — Schutz & automatische Aktualisierung

### 16.1 Upload-Schutz (Status & Plan)

**Status heute:**
- Backend: `POST /api/beneficiaries/upload` schon mit `Depends(require_moderator)` gesichert → User ohne Mod-Rolle bekommen 403
- Frontend: das Upload-Widget (Drag-and-Drop-Zone) wird **allen Nutzern** angezeigt — auch wenn der Upload dann scheitert, ist das verwirrend

**Plan:**
- Upload-Widget in `BeneficiaryMap.tsx` nur sichtbar bei `role IN ('moderator','admin')`
- Public-User (nicht eingeloggt) sehen die Karte und Auswertungen, aber **keine Upload-Zone**, **keine Quellen-Lösch-Buttons**
- Eingeloggte attendees sehen die Quellen-Pillen, aber ohne Lösch-Aktionen
- Moderatoren/Admins sehen die volle UI inkl. Upload + Löschen

**Berechtigungs-Matrix (ergänzt):**

| Aktion | public | attendee | moderator | admin |
|---|:-:|:-:|:-:|:-:|
| Karte ansehen | ✓ | ✓ | ✓ | ✓ |
| Karte filtern, exportieren (PNG/PDF) | ✓ | ✓ | ✓ | ✓ |
| Begünstigten-Auswertungen abrufen | ✓ | ✓ | ✓ | ✓ |
| Eigenes Verzeichnis hochladen | – | – | – | – |
| Begünstigtenverzeichnis hochladen | – | – | ✓ | ✓ |
| Quelle löschen | – | – | ✓ | ✓ |
| Manuellen Refresh aller Quellen triggern | – | – | – | ✓ |

> ⚠ **Bewusste Entscheidung:** auch normale Mitglieder (`attendee`) dürfen
> **kein** Begünstigtenverzeichnis hochladen. Die Datenqualität (richtige
> Bundesland-Zuordnung, korrekte Spalten-Erkennung, Schema-Konsistenz) ist
> für die Karten-/Auswertungs-Integrität kritisch — das bleibt bei Mods/
> Admins. Wer Daten beisteuern möchte, kann die XLSX über den Dokumente-
> Bereich hochladen, ein Mod migriert sie dann offiziell.

### 16.2 Automatischer monatlicher Harvest

Heute existiert das Skript `scripts/harvest_transparenzlisten.py`, das die
URL-Registry `data/transparenzlisten_urls.json` liest, alle 35 Quellen
herunterlädt und über die Backend-API einliest. Es wird aktuell **manuell**
auf Bedarf aufgerufen.

**Plan: monatlich automatisch ausführen.**

#### Zeitsteuerung

- Standardzeitpunkt: **erster Sonntag des Monats, 03:00 UTC** (geringe Last)
- Konfigurierbar in `.env`: `HARVEST_CRON="0 3 1-7 * 0"` (Cron-Notation)
- Manuell triggerbar via Admin-UI-Button

#### Implementierung

**Option A — Celery-Beat (mittelschwer):**
- `flowinvoice` nutzt bereits Celery; im Workshop-Stack analog
- Beat-Schedule in `tasks.py`:
  ```python
  @celery_app.task
  def harvest_beneficiaries_task():
      from scripts.harvest_transparenzlisten import run_full_harvest
      return run_full_harvest()

  beat_schedule = {
      "monthly-harvest": {
          "task": "tasks.harvest_beneficiaries_task",
          "schedule": crontab(minute=0, hour=3, day_of_week=0,
                              day_of_month="1-7"),
      },
  }
  ```
- Vorteil: integriert, retry-fähig, sichtbar im Admin-Dashboard
- Nachteil: Celery-Worker zusätzlich nötig (in docker-compose)

**Option B — System-Cron im Container (leichtgewichtig):**
- Cron-Job im Backend-Container:
  ```cron
  0 3 1-7 * 0 cd /app && python scripts/harvest_transparenzlisten.py >> /data/logs/harvest.log 2>&1
  ```
- Vorteil: keine Zusatz-Infrastruktur
- Nachteil: Backend-Container muss `cron` mitbringen (Dockerfile-Update)

**Option C — Externer GitHub-Action / Hetzner-Cronjob (entkoppelt):**
- Cron auf dem Host oder via GitHub Actions Schedule
- Ruft `POST /api/admin/harvest` auf der Plattform auf
- Vorteil: voll entkoppelt, kein Worker im Container nötig
- Nachteil: API-Token-Pflege, weniger transparent für Admin

**Empfehlung: Option A (Celery-Beat)** — wir haben das Pattern aus
flowinvoice schon stabil und wollen ohnehin später Async-Tasks für
RAG-Reindex, Notification-Versand, Mail-Queue.

#### Datenmodell

```python
class HarvestRun(Base):
    id: int
    started_at, finished_at: datetime
    triggered_by: str   # 'cron' | 'admin:user_id'
    status: enum('running'|'success'|'partial'|'failed')
    sources_total: int
    sources_ok: int
    sources_skipped: int   # 304 Not Modified
    sources_failed: int
    errors: jsonb         # {url: error_message}
    log_excerpt: text     # letzte ~100 Log-Zeilen

class HarvestSourceUpdate(Base):
    id: int
    run_id: int  FK
    source: str   # z. B. 'sachsen_efre_2021_2027'
    bundesland: str
    fonds: str
    url: str
    status: enum('updated'|'unchanged'|'failed'|'new')
    rows_before, rows_after: int  # Δ-Tracking
    file_size_bytes: int
    sha256_old, sha256_new: str   # Audit
    error: str | None
    updated_at: datetime
```

#### Admin-UI: Harvest-Übersicht

Neuer Tab in `/admin`:

```
┌─────────────────────────────────────────────────────────────┐
│ Begünstigtenverzeichnisse — Aktualisierung                  │
├─────────────────────────────────────────────────────────────┤
│ Letzter Lauf: 02.05.2026, 03:00 (cron) · ✓ erfolgreich     │
│   33 von 35 Quellen aktualisiert · 2 unverändert · 0 Fehler │
│   Dauer: 4 Min 12 Sek                                       │
│                                                             │
│ Nächster Lauf (cron): 07.06.2026, 03:00                    │
│                                                             │
│         [ Jetzt manuell ausführen ]                         │
├─────────────────────────────────────────────────────────────┤
│ Verlauf der letzten 12 Monate                               │
│   Jun 26  Mai 26  Apr 26  Mär 26  Feb 26  Jan 26 …         │
│    ✓       ✓       ✓       ⚠       ✓       ✓                │
│                                                             │
│ Δ-Statistik je Quelle (letzter Lauf)                        │
│   Sachsen EFRE         5763 → 5891   (+128 Vorhaben)        │
│   Bayern ESF           2862 → 2862   (unverändert)          │
│   Thüringen EFRE       2153 → 2249   (+96)                  │
│   …                                                          │
└─────────────────────────────────────────────────────────────┘
```

Klick auf einen Monatseintrag → Detail-Modal mit:
- Allen Quellen, deren Status (updated/unchanged/failed)
- Bei Failed: Fehlermeldung + Retry-Button
- SHA256 vor/nach (Audit)
- Volltext-Log

#### API

```
GET   /api/admin/harvest/runs               (admin)
GET   /api/admin/harvest/runs/:id           Detail mit allen Source-Updates
POST  /api/admin/harvest/run                Trigger sofort (admin)
GET   /api/admin/harvest/schedule           Cron-Konfiguration anzeigen
POST  /api/admin/harvest/schedule           Cron ändern
```

#### Verhalten beim Lauf

1. Lock erstellen (`flag in redis or DB lock` — verhindert parallele Runs)
2. URL-Registry laden (35 Quellen)
3. Pro Quelle:
   a. **HEAD-Request** mit `If-Modified-Since` → bei 304 als `unchanged` markieren
   b. **GET** + Größen-Limit (max 50 MB)
   c. SHA256 berechnen, mit Vorgänger vergleichen → `unchanged`
      bei gleichem Hash trotz 200
   d. **Upload** über interne Funktion (`ingest_dataframe`, gleiche Logik
      wie der Manual-Upload) — überschreibt die alte Tabelle
   e. **Geocoding** läuft automatisch nach (`get_beneficiary_map_data`)
   f. Δ-Statistik (rows_before/rows_after) speichern
4. **Geocode-Cache** wird inkrementell aktualisiert — nur neue PLZ/Standorte
   neu über Nominatim aufgelöst (Rate-Limit 1 Req/s, Cache persistent)
5. Bei Fehler je Quelle: weiter mit der nächsten, Lauf endet als `partial`
6. Nach Lauf: Notification an Admin (interne Bell oder Mail)
7. **Veröffentlichung der neuen Daten** ist sofort wirksam — die `/api/
   beneficiaries/map`-Antwort liefert die neuen Records

#### Schutz vor unerwartetem Verhalten

- **Quell-Plausibilität**: wenn neue Datei < 50 % der Vorgänger-Größe,
  Warnstatus + Admin-Verifikation, **kein automatisches Überschreiben**
- **Schema-Drift**: wenn die Spalten-Erkennung plötzlich keine `name`/
  `kosten`-Spalte findet, Quelle als `failed` markieren, alte Tabelle
  bleibt
- **Quota auf Storage**: jede heruntergeladene XLSX wird **nicht** dauerhaft
  gespeichert — nur Hash + Δ → kein Storage-Wachstum
- **Audit-Spur**: HarvestRun + HarvestSourceUpdate sind unveränderlich;
  Recall der Daten (welche Datei wurde wann eingelesen) ist möglich
- **Manueller Override**: Admin kann eine Quelle „pausieren" (kein
  Harvest mehr für diese URL) — nützlich wenn die Quelle länger umzieht

### 16.3 Sanktionslisten — täglicher Auto-Refresh

**Heutige Lage:** Backend-Endpoint `POST /api/sanctions/refresh` ist da, lädt
die EU-FSF-CSV von OpenSanctions und baut den In-Memory-Index neu auf. Wird
**nur manuell** aufgerufen. Aktueller CSV-Stand: 5. Mai 2026, 2,5 MB,
~3.000 Einträge.

**OpenSanctions-Quelle**:
`https://data.opensanctions.org/datasets/latest/eu_fsf/targets.simple.csv`
→ wird **täglich** aktualisiert (laut OpenSanctions-Crawl-Plan).

**Plan: täglich automatisch refreshen.**

#### Zeitsteuerung
- **Täglich 04:00 UTC** (kurz vor 03:00 Workshop-Harvest-Slot, wenn
  monatlicher Begünstigten-Harvest läuft, bleibt Zeit-Konflikt-frei)
- Konfigurierbar: `SANCTIONS_REFRESH_CRON="0 4 * * *"`
- Manuell triggerbar via Admin-Dashboard

#### Implementierung
- Identische Celery-Beat-Schicht wie für Begünstigten-Harvest (siehe §16.2)
- Task: `sanctions_refresh_task()` ruft `get_index().refresh_from_source()`
- Bei Fehler (HTTP 503, Netzwerk, kaputtes CSV): alter Index bleibt geladen,
  Fehler wird im Audit geloggt, Admin-Notification

#### Datenmodell
```python
class SanctionsRefreshRun(Base):
    id: int
    started_at, finished_at: datetime
    triggered_by: str   # 'cron' | 'admin:user_id'
    status: enum('running'|'success'|'failed')
    source_url: str
    file_size_bytes: int
    sha256_old, sha256_new: str
    rows_before, rows_after: int
    persons_before, persons_after: int
    organizations_before, organizations_after: int
    error: str | None
```

#### Admin-Dashboard (eigener Tab)
```
┌─────────────────────────────────────────────────────────┐
│ Sanktionslisten (EU FSF) — Aktualisierung               │
├─────────────────────────────────────────────────────────┤
│ Letzter Lauf: 07.05.2026, 04:00 (cron) · ✓ erfolgreich  │
│   3.177 → 3.181 Einträge (+4 Personen, +0 Orgs)         │
│   CSV: 2,52 MB · Quelle: OpenSanctions                  │
│                                                         │
│ Nächster Lauf (cron): 08.05.2026, 04:00                 │
│         [ Jetzt manuell ausführen ]                     │
├─────────────────────────────────────────────────────────┤
│ Verlauf der letzten 30 Tage  (Heatmap-Streifen)         │
│   ✓✓✓✓✓✓⚠✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓                          │
│ Letzte Δ:                                               │
│   06.05  +0 / -0 (unverändert)                          │
│   05.05  +12 / -0 (Iran-Listenupdate)                   │
│   04.05  +3 / -1                                        │
└─────────────────────────────────────────────────────────┘
```

#### API
```
GET   /api/admin/sanctions/runs               (admin)
GET   /api/admin/sanctions/runs/:id           Detail
POST  /api/admin/sanctions/refresh            Trigger sofort (admin)
```

#### Schutz
- ETag/Last-Modified im HTTP-Request → bei 304 als `unchanged` markieren
- SHA256-Vergleich → wenn identisch, kein Index-Rebuild nötig
- HTTP-Timeout 30 s, 3 Retries mit Backoff
- Lock-Mechanismus verhindert parallele Läufe
- Bei Fehler: alter Index bleibt — Suche bleibt verfügbar

### 16.4 LLM-Frage-Logging (für spätere Optimierung)

**Anforderung:** Bei der Begünstigten-Auswertung (Szenario 6) sollen alle
Fragen geloggt werden — sowohl die deterministisch beantworteten als auch
die LLM-Pfade. Ziel: Datengrundlage für die Verbesserung der
Mode-Erkennung, der Trigger und der LLM-Prompts.

**Umfang:** Logging gilt für **alle Workshop-LLM-Streams** (`/api/workshop/
stream`, alle Szenarien 1–6), nicht nur Szenario 6 — so bekommt man auch
die Halluzinations-Demo, die Berichts-Entwürfe etc. zur Auswertung.

#### Datenmodell

```python
class LlmQuestionLog(Base):
    id: int  PK
    created_at: datetime
    user_id: UUID | None        # NULL bei Public-Pfad
    session_id: str | None      # Anonymes Tracking-Cookie
    ip_hash: str                # SHA256+Salt
    scenario: int               # 1..6
    prompt: str                 # Originaltext, max 2000 Z.
    prompt_normalized: str      # für Frequenz-Analyse (lower, ohne Stoppwörter)
    documents_count: int        # wie viele Demo-Docs angehängt
    with_context: bool          # Szenario 3-Flag

    # Ergebnis-Kategorisierung
    answer_path: enum('deterministic_top_beneficiaries' |
                      'deterministic_top_sectors' |
                      'deterministic_top_locations' |
                      'deterministic_state_fund_totals' |
                      'deterministic_repeat_beneficiaries' |
                      'deterministic_multi_state_beneficiaries' |
                      'llm_with_context' | 'llm_without_context' |
                      'llm_fallback' | 'static_response' | 'error')
    matched_mode: str | None    # bei deterministisch: welcher Mode
    name_filter_label: str | None  # bei Eigenname/Typ-Filter
    items_returned: int         # wie viele Treffer
    fallback_used: bool         # ob LLM-Fallback bei 0 Treffern lief

    # Performance
    elapsed_ms: int
    model_name: str | None      # qwen3:14b, qwen3.5:35b, beneficiary-analytics
    token_count: int | None
    tok_per_s: float | None
    ttfb_ms: int | None         # time-to-first-byte (LLM-Latenz)

    # Antwort (für spätere Review, gekürzt)
    response_excerpt: str       # erste 500 Zeichen
    response_total_chars: int
    error_message: str | None

    # Feedback (optional, später)
    user_feedback: enum('helpful'|'unhelpful'|'wrong'|null)
    user_feedback_at: datetime | None
```

#### Admin-Dashboard

```
┌─────────────────────────────────────────────────────────┐
│ LLM-Auswertung — Szenario 6 (letzte 30 Tage)            │
├─────────────────────────────────────────────────────────┤
│ Anfragen total: 247 · Eindeutige Nutzer: 18             │
│                                                         │
│ Pfad-Verteilung:                                        │
│   deterministic_top_beneficiaries     ████████ 41%      │
│   deterministic_top_sectors           █████ 23%         │
│   deterministic_multi_state           ███ 12%           │
│   deterministic_state_fund_totals     ██ 8%             │
│   llm_with_context                    ███ 11% ⏱ 65 s   │
│   llm_fallback (kein Treffer)         █ 3%   ⏱ 84 s    │
│   error                               · 2%              │
│                                                         │
│ Top-10 häufigste Fragen (normalisiert):                 │
│  1. "wer sind die größten begünstigten" (28×)           │
│  2. "welche universitäten in bayern" (12×)              │
│  3. "kreis düren" (9×)                                  │
│  4. "wirtschaftszweige niedersachsen" (7×)              │
│  …                                                       │
│                                                         │
│ Slow Queries (>30 s):                                   │
│  • "fh gießen" → llm_fallback, 87 s, ✓ erfolgreich      │
│  • "polizei it-projekte" → llm_with_context, 64 s       │
│                                                         │
│ Failed Queries (no items):                              │
│  • "ehemalige PH Heidelberg" → 0 Treffer                │
│  • "Behörden im Saarland" → 0 Treffer                   │
│                                                         │
│         [ CSV-Export für Detail-Analyse ]               │
└─────────────────────────────────────────────────────────┘
```

#### API

```
GET   /api/admin/llm/logs?scenario=6&since=…       (admin)
GET   /api/admin/llm/stats?scenario=6&since=…      Aggregated
GET   /api/admin/llm/top-questions?n=20            Frequency
GET   /api/admin/llm/slow-queries?gt_ms=30000      Performance-Outlier
GET   /api/admin/llm/failed-queries                items_returned=0
GET   /api/admin/llm/export.csv                    CSV-Download
```

#### Privacy

- Fragen können personenbezogen sein („wieviel bekommt Müller?") — daher
  `user_id` + IP-Hash, kein Klartext-IP
- Anzeige nur an Admins
- Nutzer-Recht auf Auskunft: eigene Logs in `/account/data-export` mit drin
- Nutzer-Recht auf Löschung: bei Account-Löschung wird `user_id`
  pseudonymisiert (`prompt` bleibt für Optimierung erhalten)

#### Wo wird geloggt

In `routers/workshop.py` `workshop_stream()`:
- Vor dem Stream-Start: `LlmQuestionLog`-Eintrag mit `prompt`, `scenario`, etc.
- Während des Streams: `answer_path` setzen sobald klar
  (deterministisch vs. LLM-Pfad)
- Nach Stream-Ende: `elapsed_ms`, `token_count`, `response_excerpt`
- Bei Error: `error_message`

Implementierung als **non-blocking**: Schreibt async, blockiert die LLM-
Antwort nicht. Falls DB-Schreiben fehlschlägt, wird der Stream nicht
abgebrochen.

#### Phase im Plan

Eingegliedert als Teil von **Phase 3.5** (Auto-Harvest), gemeinsamer Sprint:

| Sprint | Inhalt | h |
|---|---|---:|
| **C2** | Auto-Harvest Begünstigte (monatlich) + Sanktionen (täglich) + LLM-Frage-Log + Admin-Dashboards | 5–6 |

---

## 17. Änderungs-Historie

- **2026-05-07 v3.2** — Mail-Schicht entfällt (zu viel Setup-Aufwand);
  Sanktionslisten täglicher Auto-Refresh; LLM-Frage-Logging für alle
  Workshop-Streams mit Admin-Dashboard
- **2026-05-07 v3.1** — Landing-Page mit Public-Tools (Begünstigte + Sanktionen);
  Upload-Schutz nur für Mods; automatischer monatlicher Harvest mit
  Admin-Dashboard
- **2026-05-07 v3** — Final, alle Anwender-Antworten konsolidiert, Migration der bestehenden Nutzer beschrieben
- **2026-05-07 v2** — Login-System detailliert, Phase 0 hinzugefügt
- **2026-05-07 v1** — Erstentwurf nach Anwender-Auftrag „GUI für Post-Event-Modus planen"
