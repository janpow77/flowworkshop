"""
flowworkshop · config.py
Zentrale Konfiguration — System-Prompts, Umgebungsvariablen, Konstanten.
"""
import os

# ── Verbindungen ───────────────────────────────────────────────────────────
DATABASE_URL  = os.getenv("DATABASE_URL",  "postgresql://workshop:workshop@localhost:5433/workshop")
OLLAMA_URL    = os.getenv("OLLAMA_URL",    "http://localhost:11434")
LLM_BACKEND   = os.getenv("LLM_BACKEND",   "ollama").lower()
EGPU_GATEWAY_URL = os.getenv("EGPU_GATEWAY_URL", "http://localhost:7842")
EGPU_GATEWAY_APP_ID = os.getenv("EGPU_GATEWAY_APP_ID", "auditworkshop")
EGPU_WORKLOAD_TYPE = os.getenv("EGPU_WORKLOAD_TYPE", "llm")
MODEL_NAME    = os.getenv("MODEL_NAME",    "qwen3:14b")
# Europaeische Alternative: MODEL_NAME = "mistral:7b" (Mistral AI, Paris)
# Installieren: ollama pull mistral:7b

# Szenario-spezifischer Modell-Override (kommagetrennt, je "scenario:model")
# Default: keine Override — alle Szenarien nutzen MODEL_NAME (qwen3:14b).
# qwen3.5:35b auf der Evo-X2 ist ein Reasoning-Modell mit endlosen <think>-
# Bloecken (60-80s pro Antwort, oft Token-Limit erreicht ohne Content) und
# damit fuer Live-Demos unbrauchbar. qwen3:14b auf der eGPU liefert in
# 20-30s mit /no_think am User-Turn-Ende.
# Per ENV ueberschreibbar, z. B. SCENARIO_MODELS=6:qwen3.5:35b
_SCENARIO_MODEL_RAW = os.getenv("SCENARIO_MODELS", "")
SCENARIO_MODELS: dict[int, str] = {}
for _entry in _SCENARIO_MODEL_RAW.split(","):
    _entry = _entry.strip()
    if not _entry or ":" not in _entry:
        continue
    _scn, _model = _entry.split(":", 1)
    try:
        SCENARIO_MODELS[int(_scn.strip())] = _model.strip()
    except ValueError:
        continue
WORKSHOP_ADMIN = os.getenv("WORKSHOP_ADMIN", "false").lower() == "true"
ALLOW_REMOTE_GEOCODING = os.getenv("ALLOW_REMOTE_GEOCODING", "false").lower() == "true"
ALLOW_REMOTE_TILES = os.getenv("ALLOW_REMOTE_TILES", "true").lower() == "true"
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET", "workshop-dev-auth-secret-change-me")
WORKER_API_TOKEN = os.getenv("WORKER_API_TOKEN", AUTH_TOKEN_SECRET)

# ── Embedding ──────────────────────────────────────────────────────────────
EMBEDDING_BACKEND = os.getenv(
    "EMBEDDING_BACKEND",
    "gateway" if LLM_BACKEND in {"egpu-manager", "egpu_manager", "gateway"} else "local",
).lower()
EMBEDDING_GATEWAY_URL = os.getenv("EMBEDDING_GATEWAY_URL", EGPU_GATEWAY_URL)
EMBEDDING_GATEWAY_APP_ID = os.getenv("EMBEDDING_GATEWAY_APP_ID", EGPU_GATEWAY_APP_ID)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "bge-m3" if EMBEDDING_BACKEND == "gateway" else "paraphrase-multilingual-mpnet-base-v2",
)
EMBEDDING_DIM   = int(os.getenv("EMBEDDING_DIM", "1024" if EMBEDDING_BACKEND == "gateway" else "768"))

# ── Chunking ───────────────────────────────────────────────────────────────
CHUNK_WORDS   = 700    # Zielgröße je Chunk (wortbasiert)
CHUNK_OVERLAP = 150    # Überlappung in Wörtern

# ── Performance ──────────────────────────────────────────────────────────
# Reduziere num_ctx fuer schnellere Prompt-Evaluation auf Kosten der Kontextlaenge
LLM_NUM_CTX     = int(os.getenv("LLM_NUM_CTX", "8192"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_NUM_GPU     = int(os.getenv("LLM_NUM_GPU", "99"))  # Alle Layer auf GPU
LLM_MAX_TOKENS_DEFAULT = int(os.getenv("LLM_MAX_TOKENS_DEFAULT", "384"))

# ── Wissens-Recherche (KB-Search) ──────────────────────────────────────────
# Modell fuer die KB-Textgenerierung im Recherche-Modul. Geht ueber das Gateway
# (LLM_BACKEND=egpu-manager) an den ai-router.
#
# Stand 2026-05-25: Umstellung von "qwen3.5:35b-fast" (evo-x2) auf "qwen3:14b".
# Begruendung (real gemessen, siehe Mess-Tabelle in der Analyse):
#   - 35b-fast lieferte fuer die Generierung KEINEN Content: lange Reasoning-Phase,
#     dann Read-Timeout (>200 s, 0 Text-Tokens). Der Schalter reasoning_effort
#     wirkte dort nicht.
#   - 14b liefert mit reasoning_effort="none" das erste Text-Token in ~0,1 s und
#     eine vollstaendige, belegbasierte Antwort in ~20-25 s. Qualitaet fuer den
#     belegbasierten Recherche-Modus voellig ausreichend.
# Zurueckdrehen: ENV KB_RESEARCH_MODEL=qwen3.5:35b-fast setzen (nicht empfohlen,
# solange der evo-x2-Spoke so langsam antwortet).
KB_RESEARCH_MODEL = os.getenv("KB_RESEARCH_MODEL", "qwen3:14b")
# Reasoning-Steuerung fuer die KB-Generierung. "none" schaltet die Denk-Phase
# vollstaendig ab (sofortiger Content). WICHTIG: das fruehere "/no_think" im
# User-Prompt wirkte am ai-router NICHT — nur der OpenAI-Parameter
# reasoning_effort greift. Werte: none | low | medium | high.
KB_RESEARCH_REASONING_EFFORT = os.getenv("KB_RESEARCH_REASONING_EFFORT", "none")
# Wie viele Chunks als RAG-Kontext in die Generierung gehen.
# 4 statt 6: weniger Prefill-Tokens → schnelleres erstes Token (Latenz P0).
KB_RESEARCH_TOP_K = int(os.getenv("KB_RESEARCH_TOP_K", "4"))

# Reranking der Generierungs-Treffer ueber den ai-router (BGE-Reranker-v2-m3).
# Cross-Encoder bewertet die Kandidaten nach echter Relevanz zur Frage und loest
# so z. B. die „Artikel 74"-Kollision zwischen VO 2021/1060 und dem EU AI Act —
# domaenenneutral (eine AI-Act-Frage rankt AI-Act-Stellen oben). Ablauf:
# grob KB_RERANK_POOL Treffer per Vektorsuche → reranken → beste KB_RESEARCH_TOP_K.
KB_RERANK_ENABLED = os.getenv("KB_RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
KB_RERANK_POOL = int(os.getenv("KB_RERANK_POOL", "8"))
KB_RERANK_THRESHOLD = float(os.getenv("KB_RERANK_THRESHOLD", "0.05"))
KB_RERANK_MODEL = os.getenv("KB_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# Quellen-Gruppen fuer die Recherche: ein auswaehlbarer Eintrag bündelt mehrere
# Einzelquellen. Wird in Suche + Generierung als Quellen-Filter expandiert.
KB_SOURCE_GROUPS: dict[str, list[str]] = {
    "Grundlagen Strukturfonds": [
        "VO_2018_1046_DE",       # EU-Haushaltsordnung
        "VO_2021_1060_DE",       # Dachverordnung (CPR)
        "VO_2021_1058_DE",       # EFRE + Kohäsionsfonds
        "VO_2021_1057_DE",       # ESF+
        "VO_2021_1056_DE",       # JTF
        "VO_2021_1059_DE",       # Interreg
        "DVO_2023_1676_DE",      # DelVO: SCO-Definitionen (Kosten je Einheit, Pauschalen)
        "DVO_2023_0067_DE",      # DelVO: standardisierte Stichprobenmethoden
        "DVO_2022_2175_DE",      # DelVO: ALMA — Kosten je Einheit
        "DVO_2025_2190_DE",      # DelVO: Interventionskategorien (Anhang I)
    ],
    "Beihilferecht": [
        "AEUV_KONSOLIDIERT_DE",            # AEUV (Art. 107-109)
        "AGVO_651_2014_DE",               # Allgemeine Gruppenfreistellungsverordnung
        "DEMINIMIS_2023_2831_DE",         # De-minimis
        "DEMINIMIS_DAWI_2023_2832_DE",    # De-minimis DAWI
        "DAWI_BESCHLUSS_2012_21_DE",      # DAWI-Freistellungsbeschluss
        "VERFAHRENS_VO_2015_1589_DE",     # Beihilfeverfahren / Notifizierung
        "KOM_LEITLINIEN_INTERESSENKONFLIKTE_DE",  # KOM-Leitlinien Interessenkonflikte
    ],
}
# Standard-Quellenauswahl der Recherche (Gruppenname oder "" für alle Quellen).
KB_DEFAULT_SOURCE = os.getenv("KB_DEFAULT_SOURCE", "Grundlagen Strukturfonds")
# Wortmarke fuer die Abstention-Erkennung im Frontend (muss zum Prompt passen).
KB_RESEARCH_ABSTENTION = "Die Wissensbasis enthält keine Belege zu dieser Frage."
# System-Prompt fuer die KB-Textgenerierung. Strikt belegbasiert mit Abstention —
# das Modell darf nur aus dem mitgelieferten Kontext schöpfen.
KB_RESEARCH_SYSTEM_PROMPT = """Du bist ein Rechercheassistent für EFRE-Prüfer.
Beantworte die Frage AUSSCHLIESSLICH auf Basis der bereitgestellten Fundstellen aus
der Wissensbasis. Erfinde keine Inhalte, Artikel oder Zahlen.
Wenn die Fundstellen die Frage nicht abdecken, antworte exakt mit:
"Die Wissensbasis enthält keine Belege zu dieser Frage."
Zitiere relevante Rechtsgrundlagen (z. B. Artikelnummern) nur, wenn sie im Kontext stehen.
Formuliere keine prüfungsrechtlichen Urteile — das Urteil obliegt dem Prüfer.
Antworte auf Deutsch in klarer Behördensprache."""

# ── Begünstigtenverzeichnis ────────────────────────────────────────────────
BENEFICIARY_URL = (
    "https://wirtschaft.hessen.de/sites/wirtschaft.hessen.de/files/"
    "2025-12/transparenzlistenverzeichnis_hessen_2021-2027.xlsx"
)
BENEFICIARY_CACHE = "/app/data/beneficiary_cache.json"
GEOCODE_CACHE     = "/app/data/geocode_cache.json"

# ── Hinweistext (erscheint unter jeder LLM-Antwort im UI) ─────────────────
DISCLAIMER = (
    "Diese Auswertung ist ein Arbeitsmittel. "
    "Das prüfungsrechtliche Urteil obliegt ausschließlich dem Prüfer "
    "(Art. 77 VO (EU) 2021/1060)."
)

# ── System-Prompts ─────────────────────────────────────────────────────────
SYSTEM_PROMPTS: dict[str | int, str] = {

    # Szenario 1 — Dokumentenanalyse
    1: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Analysiere das vorgelegte Förderdokument und extrahiere alle bindenden Auflagen
und Nachweispflichten strukturiert.
Format je Auflage:
- Nummer (falls vorhanden)
- Wortlaut der Auflage (kurz, sinngemäß)
- Art des geforderten Nachweises
- Frist (falls genannt)
Weise explizit auf Unsicherheiten hin.
Formuliere keine prüfrechtlichen Urteile — das Urteil obliegt dem Prüfer.
Antworte auf Deutsch. Keine Aufzählungszeichen mit Bindestrichen — nutze nummerierte Listen.
Maximal 8 Punkte.""",

    # Szenario 2 — Checklisten-Unterstützung
    2: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Beurteile jeden Prüfpunkt der folgenden Checkliste ausschließlich auf Basis
der vorgelegten Unterlagen.
Gib das Ergebnis als JSON-Array zurück — kein weiterer Text davor oder danach:
[
  {
    "id": "VKO-01",
    "status": "erfüllt",
    "begruendung": "Vergabevermerk liegt vor, Datum passt zum Zuwendungsbescheid.",
    "fundstelle": "Vergabeakte, S. 3"
  },
  {
    "id": "VKO-02",
    "status": "nicht_beurteilbar",
    "begruendung": "Nachweis nicht in den vorgelegten Unterlagen enthalten.",
    "fundstelle": null
  }
]
Erlaubte Statuswerte: erfüllt | nicht_erfüllt | nicht_beurteilbar
Erfinde keine Informationen. Weise explizit auf fehlende Nachweise hin.""",

    # Szenario 3 ohne Kontext — zeigt Halluzinationsrisiko
    "3_ohne": """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Beantworte die folgende Frage zu EU-Strukturfondsrecht so präzise wie möglich.
Antworte auf Deutsch.
Antworte kurz und direkt in höchstens 5 Sätzen.""",

    # Szenario 3 mit Kontext — RAG-gestützt
    "3_mit": """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Beantworte die folgende Frage ausschließlich auf Basis der beigefügten Dokumente.
Regeln:
- Nenne KEINE Artikelnummern, die nicht im Dokument stehen.
- Zitiere immer die genaue Fundstelle (Artikel, Absatz, Unterabsatz).
- Wenn die Antwort nicht vollständig im Dokument steht, antworte so weit wie möglich mit dem was vorhanden ist und weise auf Lücken hin.
- Gib eine kurze, strukturierte Antwort in 3 bis 6 Punkten.
- Keine Ergänzungen aus dem Trainingswissen.
Antworte auf Deutsch.""",

    # Szenario 4 — Berichtsentwurf
    4: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Formuliere auf Basis der folgenden Prüffeststellungen eine Berichtpassage
für einen EFRE-Vorhabenprüfungsbericht nach Art. 77 VO (EU) 2021/1060 (Dachverordnung).
Stilregeln:
- Sachlich, verwaltungsrechtlich präzise, Indikativ.
- Je Feststellung ein Absatz mit drei Teilen: (1) Sachverhalt, (2) Bewertung, (3) Empfehlung.
- Keine Aufzählungszeichen. Keine Einleitungsfloskeln.
- Perfekt statt Präteritum — außer bei "war", "hatte", Modalverben.
- Keine wertenden Adjektive ohne Tatsachenbezug.
- Rechtsgrundlagen: Verweise auf VO (EU) 2021/1060 (Dachverordnung), NICHT auf VO (EU, Euratom) 2018/1046 oder andere Verordnungen, es sei denn sie werden im Eingabetext genannt.
- Bei Vergabemängeln: Auf das einschlägige nationale Vergaberecht verweisen (UVgO, VgV, VOB/A).
- Bei Publizitätsmängeln: Art. 50 VO (EU) 2021/1060 zitieren.
Antworte ausschließlich mit dem Berichttext. Kein Vor- oder Nachkommentar.
Maximal drei Absätze.""",

    # Szenario 5 — Vorab-Upload (eigene Dokumente der Prüfer)
    5: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Dir liegen Auszüge aus Förderdokumenten vor, die in einer Wissensdatenbank
gespeichert sind. Beantworte die Frage ausschließlich auf Basis dieser Auszüge.
- Zitiere die Quelle je Aussage (Dokumentname, Seitenangabe falls vorhanden).
- Wenn keine relevante Information vorliegt, sage das explizit.
- Keine Ergänzungen aus dem Trainingswissen.
Antworte auf Deutsch in vollständigen Sätzen.
Antworte knapp und präzise in höchstens 6 Sätzen.""",

    # Szenario 6 — Begünstigtenverzeichnis
    6: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Dir liegen aggregierte Auswertungen und Spitzendaten aus den aktuell geladenen
Begünstigtenverzeichnissen vor.
Beantworte Fragen ausschließlich auf Basis dieser Statistiken.
Regeln:
- Erfinde keine Begünstigten oder Beträge.
- Weise explizit darauf hin, wenn eine Frage nicht auf Basis der vorliegenden Daten beantwortet werden kann.
- Zahlen immer mit Tausendertrennzeichen (1.234.567 €).
- Antworte in kurzen deutschen Sätzen.
- Nutze maximal 8 Aufzählungspunkte.

Sonderfall — Block "Wahrscheinliche Kandidaten":
Erscheint im Kontext eine Liste mit "Wahrscheinliche Kandidaten" (kein
direkter Substring-Treffer für die Nutzerfrage), darfst du dein
Allgemeinwissen einsetzen, um historische oder veränderte Namen
aufzulösen — z. B. "FH Gießen" entspricht heute der "Technischen
Hochschule Mittelhessen (THM)", "TH Karlsruhe" entspricht dem heutigen
"KIT", "Goethe-Universität" steht für die "Universität Frankfurt am
Main". Wähle aus der Kandidatenliste den passenden Eintrag, nenne den
dort angegebenen Betrag und die Vorhabenzahl und erkläre die
Namensauflösung in einem Halbsatz. Findest du keinen passenden
Kandidaten, sage das ehrlich.""",
}

# ── E-Mail-Versand ─────────────────────────────────────────────────────────
# SMTP-Konfiguration für Anmeldebestätigungen und Admin-Benachrichtigungen.
# Default: IONOS-SMTP (Mailbox jan.riener@vwvg.de). Versand ist nur aktiv,
# wenn EMAIL_ENABLED=true UND SMTP_HOST + SMTP_USER + SMTP_PASSWORD gesetzt.
EMAIL_ENABLED      = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST          = os.getenv("SMTP_HOST", "smtp.ionos.de")
SMTP_PORT          = int(os.getenv("SMTP_PORT", "587"))
SMTP_STARTTLS      = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
SMTP_USER          = os.getenv("SMTP_USER", "")
SMTP_PASSWORD      = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM          = os.getenv("SMTP_FROM", "jan.riener@vwvg.de")
SMTP_FROM_NAME     = os.getenv("SMTP_FROM_NAME", "Prüferworkshop EFRE Hessen")
ADMIN_NOTIFY_EMAIL = os.getenv("ADMIN_NOTIFY_EMAIL", "jan.riener@vwvg.de")
EMAIL_TIMEOUT_S    = int(os.getenv("EMAIL_TIMEOUT_S", "20"))
# Public-URL für Links in Mails (Login, Tagesordnung)
EMAIL_PUBLIC_URL   = os.getenv("EMAIL_PUBLIC_URL", "https://workshop.flowaudit.de")
# LLM darf einen kurzen personalisierten Absatz erzeugen, sofern der
# Teilnehmer dem zugestimmt hat (ai_confirmation_consent).
EMAIL_AI_PERSONALIZE = os.getenv("EMAIL_AI_PERSONALIZE", "true").lower() == "true"
EMAIL_AI_MAX_TOKENS  = int(os.getenv("EMAIL_AI_MAX_TOKENS", "180"))
EMAIL_AI_TIMEOUT_S   = int(os.getenv("EMAIL_AI_TIMEOUT_S", "25"))

