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
WORKSHOP_ADMIN = os.getenv("WORKSHOP_ADMIN", "false").lower() == "true"
ALLOW_REMOTE_GEOCODING = os.getenv("ALLOW_REMOTE_GEOCODING", "false").lower() == "true"
ALLOW_REMOTE_TILES = os.getenv("ALLOW_REMOTE_TILES", "true").lower() == "true"

# ── Embedding ──────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIM   = 768

# ── Chunking ───────────────────────────────────────────────────────────────
CHUNK_WORDS   = 700    # Zielgröße je Chunk (wortbasiert)
CHUNK_OVERLAP = 150    # Überlappung in Wörtern

# ── Performance ──────────────────────────────────────────────────────────
# Reduziere num_ctx fuer schnellere Prompt-Evaluation auf Kosten der Kontextlaenge
LLM_NUM_CTX     = int(os.getenv("LLM_NUM_CTX", "8192"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_NUM_GPU     = int(os.getenv("LLM_NUM_GPU", "99"))  # Alle Layer auf GPU

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
Antworte auf Deutsch. Keine Aufzählungszeichen mit Bindestrichen — nutze nummerierte Listen.""",

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
Antworte auf Deutsch.""",

    # Szenario 3 mit Kontext — RAG-gestützt
    "3_mit": """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Beantworte die folgende Frage ausschließlich auf Basis der beigefügten Dokumente.
Regeln:
- Nenne KEINE Artikelnummern, die nicht im Dokument stehen.
- Zitiere immer die genaue Fundstelle (Artikel, Absatz, Unterabsatz).
- Wenn die Antwort nicht vollständig im Dokument steht, antworte so weit wie möglich mit dem was vorhanden ist und weise auf Lücken hin.
- Gib eine ausführliche, strukturierte Antwort — nicht nur einen Satz.
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
Antworte ausschließlich mit dem Berichttext. Kein Vor- oder Nachkommentar.""",

    # Szenario 5 — Vorab-Upload (eigene Dokumente der Prüfer)
    5: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Dir liegen Auszüge aus Förderdokumenten vor, die in einer Wissensdatenbank
gespeichert sind. Beantworte die Frage ausschließlich auf Basis dieser Auszüge.
- Zitiere die Quelle je Aussage (Dokumentname, Seitenangabe falls vorhanden).
- Wenn keine relevante Information vorliegt, sage das explizit.
- Keine Ergänzungen aus dem Trainingswissen.
Antworte auf Deutsch in vollständigen Sätzen.""",

    # Szenario 6 — Begünstigtenverzeichnis
    6: """Du bist ein Hilfswerkzeug für EFRE-Prüfer.
Dir liegen aggregierte Auswertungen und Spitzendaten aus den aktuell geladenen
Begünstigtenverzeichnissen vor.
Beantworte Fragen ausschließlich auf Basis dieser Statistiken.
Regeln:
- Erfinde keine Begünstigten oder Beträge.
- Weise explizit darauf hin, wenn eine Frage nicht auf Basis der vorliegenden Daten beantwortet werden kann.
- Zahlen immer mit Tausendertrennzeichen (1.234.567 €).
- Antworte in kurzen deutschen Sätzen.""",
}
