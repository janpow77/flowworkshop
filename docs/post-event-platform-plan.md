# Plan: Workshop-Plattform nach der Veranstaltung

> **Status:** v3.1 (final, freigabebereit)
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

## 3. Auth-System (Phase 0)

### 3.1 Flows

#### Selbstregistrierung
```
1. /register → Formular:
     E-Mail (Pflicht, validiert) · Passwort (≥10 Z., ≥1 Sonderz., ≥1 Ziffer)
     Vor-/Nachname · Behörde · Bundesland (Dropdown DE+AT+Bund)
     Funktion · Begründung der Anmeldung (optional)
     Einwilligung Datenschutz (Checkbox, Pflicht)
2. POST /api/auth/signup
     Backend: User-Eintrag mit status='email_unverified'
     Versand „Magic Link" via SMTP
3. /verify-email?token=… → status='pending_approval'
4. Admin sieht in /admin/users die Pending-Queue
5. Admin klickt Genehmigen → status='active', Mail an User
6. User loggt sich unter /login mit E-Mail + Passwort ein → Session-Cookie
```

#### Login
- E-Mail + Passwort (Argon2id-gehasht, 64 MB / 3 iterations / 4 parallelism)
- Rate-Limit: 5 Versuche / 15 Min pro IP, 10 / Stunde pro E-Mail
- Lockout nach 10 fehlgeschlagenen Versuchen für 30 Min, mit Reset-Mail-Hinweis

#### Passwort-Reset
- POST `/api/auth/request-reset` → Mail mit Token (24 h gültig)
- GET `/reset-password?token=…` → Form, POST mit neuem Passwort
- Alle bestehenden Sessions werden invalidiert

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

### 3.6 Mail-Provider

Ohne Mail kein Login. Drei realistische Optionen:

| Option | Kosten | Empfehlung |
|---|---|---|
| Brevo | 300 Mails/Tag gratis, danach 9 €/M | ⭐ einfach, gut für Workshop-Größe |
| Mailgun | 1.000 Mails/Tag gratis 30 d, danach $35/M | bei stark wachsender Nutzerzahl |
| Hetzner-Mailbox-SMTP | inkl. wenn Hosting dort | ⭐⭐ am pragmatischsten wenn die Domain bei Hetzner liegt |

**Setup-Checkliste:**
- DNS-Einträge: SPF, DKIM, DMARC für `workshop.flowaudit.de`
- Sender-Adresse fest, z. B. `noreply@workshop.flowaudit.de`
- Reply-To-Adresse: vermutlich `workshop@wirtschaft.hessen.de` oder eigenes Postfach
- SMTP-Credentials in `.env` (außerhalb Repo)

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

### 4.4 Optionale Komfort-Mail (sobald SMTP läuft)

> **Betreff:** Workshop-Plattform: einmalige Passwort-Vergabe
>
> Hallo {first_name},
>
> die Workshop-Plattform bekommt einen neuen Login-Bereich. Dein Account ist
> bereits eingerichtet, du musst nur einmalig ein Passwort vergeben:
>
> → https://workshop.flowaudit.de/account/setup-password?token=<unique>
>
> Dein bisheriger Einladungslink funktioniert noch 30 Tage parallel.

Opt-out — wer nichts tut, kann weiter mit dem alten Token.

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
| **A1** | Mail-Setup-Klärung + DNS-Einträge | 1–2 | SPF/DKIM/DMARC sichtbar in `dig` |
| **A2** | **Phase 0 Auth-System** (User, Sessions, Approval, Migration alter Tokens) | 8–10 | Login End-to-End, alter Token migriert |
| **A3** | **Phase 5 Export-Lib** (parallel) — `html-to-image` + `useExport` | 2–3 | Karten-Export erzeugt PNG + PDF |
| **B1** | **Phase 1 Hub-Kacheln** + `event.phase`-Toggle + Admin-UI | 3–4 | Phase-Wechsel sichtbar, Hub live |
| **B2** | **Phase 2 Forum-Redesign** | 6–7 | Diskurs-Stil, Migration alter Posts |
| **C** | **Phase 3 Dokumente** | 7–8 | Upload, Versionen, Download, Quota |
| **D1** | **Phase 4 Archiv-Tagesordnung** mit Material-Verknüpfung | 3–4 | Klick auf Programm-Punkt zeigt Material |
| **D2** | **Phase 6 Notification-Center** (Bell, intern) | 2 | Ungelesen-Indikator in Hub-Kacheln |
| ~~E~~ | Phase 7 RAG (später) | 4–6 | semantische Suche |
| ~~E~~ | Phase 8 Optional 2FA für Admin | 2 | TOTP+Recovery |

**Total bis Phase 6:** ~32–40 h Entwicklung über 5–7 Werktage.

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

#### Phase im Plan

Eingegliedert als **Phase 3.5** zwischen Dokumente und Archiv:

| Sprint | Inhalt | h |
|---|---|---:|
| **C2** | **Phase 3.5 Auto-Harvest** (Celery-Beat, HarvestRun-Model, Admin-UI, Δ-Statistik) | 4–5 |

Das verschiebt **Phase 4 Archiv** und **Phase 6 Notifications** nach hinten,
ändert aber nichts am Gesamtaufwand wesentlich (~36–45 h statt 32–40 h).

---

## 17. Änderungs-Historie

- **2026-05-07 v3.1** — Landing-Page mit Public-Tools (Begünstigte + Sanktionen);
  Upload-Schutz nur für Mods; automatischer monatlicher Harvest mit
  Admin-Dashboard
- **2026-05-07 v3** — Final, alle Anwender-Antworten konsolidiert, Migration der bestehenden Nutzer beschrieben
- **2026-05-07 v2** — Login-System detailliert, Phase 0 hinzugefügt
- **2026-05-07 v1** — Erstentwurf nach Anwender-Auftrag „GUI für Post-Event-Modus planen"
