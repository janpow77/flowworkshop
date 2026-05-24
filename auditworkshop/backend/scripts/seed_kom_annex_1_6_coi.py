"""
flowworkshop · scripts/seed_kom_annex_1_6_coi.py

Seedet die KOM-Mustercheckliste "Annex 1.6 — Conflict of interest (KA7)"
als deutsche, in die audit_designer-Struktur überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → vier Zielsetzungen (Überschriften)
mit Unterabschnitten → Fragen (mit Rechtsgrundlage KA/BK, Antwortset
Ja/Nein/Teilweise/Entfällt, Belegen und Aufzählungen/Hinweisen als HINT-
Kindknoten). Englisches Original (XLSX) bleibt als source_document hinterlegt.

Quelle: backend/data/checklist_sources/annex_1_6_coi.xlsx (KOM-XLSX, 6 Sheets:
Metadata, Cover, Objective 1-4). Erkannte Spaltenzuordnung der Objective-Tabs:
  A   = No.            (Nummer; mehrstufig 2.1 / 2.1.1 → Abschnitt vs. Frage)
  B   = TEST           (Fragetext; Folgezeilen ohne No. = Aufzählungen/Hinweise)
  H/J/L = Answer        (je Begünstigtem X/Y/Z; "Free text or Y/N or N/A")
  I/K/M = Ref/ WP       (Belegverweis je Begünstigtem)
  N   = Other Comments
Die Begünstigten-Spaltenmatrix (X/Y/Z) wird auf ein einziges Antwortset
(Ja / Nein / Teilweise / Entfällt) abgebildet; die mehrfachen Antwort-/Ref-
Spalten dienen im Original nur der Mehrfacherhebung je Begünstigtem.

Idempotent: vorhandener Seed (gleiche source_document_name / Titel) wird zuvor
entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_6_coi.py
"""
import sys
import uuid

sys.path.insert(0, "/app")

from database import SessionLocal  # noqa: E402
from models.checklist_template import (  # noqa: E402
    ChecklistTemplate, ChecklistTemplateNode, ChecklistAnswerSet,
    ChecklistAnswerOption, ChecklistMember,
)
from models.registration import Registration  # noqa: E402

SOURCE_DOC = "Annex 1.6 Conflict of interest.xlsx"
SOURCE_PATH = "checklist_sources/annex_1_6_coi.xlsx"
TITLE = "KOM — Interessenkonflikte (KA7)"

INSTRUCTION = (
    "Hinweis: Die Checkliste dient der Beurteilung, ob die Vorgaben des "
    "Art. 61 der Haushaltsordnung und die hierzu vom Zentralen Finanzdienst "
    "ergangenen Leitlinien eingehalten werden. Sie umfasst Prüfungen zu vier "
    "Zielsetzungen: (1) Beurteilung des gesamten Kontrollumfelds rund um "
    "Interessenkonflikte und der Erfassung von Hochrisiko-Funktionen und "
    "-Verhaltensweisen, (2) Nachweis, dass finanzielle und nichtfinanzielle "
    "Akteure — einschließlich nationaler Behörden jeder Ebene — keine Handlung "
    "vornehmen, die ihre eigenen Interessen in Konflikt mit denen der Union "
    "bringt (die meisten Tests betreffen die Verwaltungsbehörden / "
    "zwischengeschalteten Stellen, sind aber — soweit zutreffend — auf die "
    "Ebene der Begünstigten auszudehnen), (3) Nachweis geeigneter Mechanismen "
    "zur Prävention und Aufdeckung von Interessenkonflikten und (4) Nachweis "
    "ausreichender und ordnungsgemäß genutzter Werkzeuge zur Aufdeckung von "
    "Interessenkonflikten. In Grün gekennzeichnete Tests des Originals dienen "
    "lediglich der Information."
)

# Antwortset (QChess-Stil): Ja / Nein / Teilweise / Entfällt
ANSWER_SET = {
    "name": "Ja / Nein / Teilweise / Entfällt",
    "description": "Standard-Antwortset der KOM-Prüfchecklisten (Y/N/Partial).",
    "options": [
        {"name": "Ja", "is_standard": True},
        {"name": "Nein"},
        {"name": "Teilweise"},
        {"name": "Entfällt", "is_entfaellt": True},
    ],
}

# Kopfblock-Felder (Allgemeine Angaben) — aus Cover/Metadata des Originals
HEADER_FIELDS = [
    ("Audit-Code", "TEXT"),
    ("Mitgliedstaat", "TEXT"),
    ("Operationelle Programme (CCI)", "TEXT"),
    ("Checkliste erstellt — Name", "TEXT"),
    ("Checkliste erstellt — Datum", "DATE"),
    ("Checkliste geprüft — Name", "TEXT"),
    ("Checkliste geprüft — Datum", "DATE"),
]

# Gemeinsame Rechtsgrundlage der Interessenkonflikt-Prüfung (KA7).
KA7 = "KA7 BK7.x · Art. 61 Haushaltsordnung"

# Belegspalten des Originals (Ref/WP je Begünstigtem) — generisch abgebildet.
BELEGE = [
    "Bezug / Arbeitspapier (Ref/WP)",
    "ggf. je Begünstigtem (X / Y / Z)",
]

# Teile (Zielsetzungen) mit Unterabschnitten und Fragen.
# Struktur je Teil: (teil_titel, einleitungs_hint, [abschnitte])
# Abschnitt: (abschnitts_titel_or_None, [fragen])
# Frage: (key, legal_reference, frage_de, [hinweise_de])
PARTS = [
    (
        "Zielsetzung 1 — Beurteilung des Kontrollumfelds für Interessenkonflikte",
        "Ziel: Beurteilung des gesamten Kontrollumfelds rund um Interessenkonflikte "
        "und Nachweis, dass Hochrisiko-Funktionen und -Verhaltensweisen erfasst "
        "werden (Art. 61 Haushaltsordnung).",
        [
            (None, [
                ("1.1", KA7,
                 "Werden Hochrisiko-Funktionen ordnungsgemäß und rechtzeitig identifiziert?",
                 [
                     "Dies können sein:",
                     "Hochrisiko-Verwaltungsprozesse im Zusammenhang mit dem Verwaltungs- und Kontrollsystem;",
                     "öffentliche Auftragsvergabe;",
                     "Ernennung und Einstellung von Amtsträgern und Entscheidungsträgern sowie Mitgliedern von Begleitausschüssen (in Verbindung mit Erklärungen zum Nichtvorliegen von Interessenkonflikten);",
                     "staatseigene Unternehmen (SOE) und öffentlich-private Partnerschaften (PPP), die in der Regel nicht denselben Regeln wie andere öffentliche Aufträge unterliegen.",
                 ]),
                ("1.2", KA7,
                 "Werden Hochrisiko-Personen ordnungsgemäß und rechtzeitig identifiziert?",
                 [
                     "Dies können sein:",
                     "verbundene natürliche Personen;",
                     "Analyse der Einrichtungen, in denen verbundene Personen erheblichen Einfluss ausüben.",
                 ]),
            ]),
        ],
    ),
    (
        "Zielsetzung 2 — Akteure dürfen keine Handlungen vornehmen, die Interessenkonflikte begründen",
        "Ziel: Nachweis, dass finanzielle und nichtfinanzielle Akteure — "
        "einschließlich nationaler Behörden jeder Ebene — keine Handlung "
        "vornehmen, die ihre eigenen Interessen in Konflikt mit denen der Union "
        "bringt. Die meisten Tests betreffen die Verwaltungsbehörden / "
        "zwischengeschalteten Stellen, sind aber — soweit zutreffend — auf die "
        "Ebene der Begünstigten auszudehnen.",
        [
            ("2.1 — Risiken bei Verträgen / Zuwendungen und Interessenkonflikte", [
                ("2.1.1", KA7,
                 "Bestehen diese Erklärungen für alle Akteure, die am Verfahren zur Erlangung von EU-Mitteln beteiligt und/oder mit EU-Mitteln verbunden sind?",
                 ["Überprüfen Sie den gesamten Prozess der Erklärungen."]),
                ("2.1.2", KA7,
                 "Werden das Vorliegen der Erklärungen und deren vollständige Ausfüllung intern geprüft und kontrolliert?",
                 []),
                ("2.1.3", KA7,
                 "Falls die vorstehende Frage mit „Ja“ beantwortet wird: Ist das Verfahren der Überprüfung und Kontrolle angemessen?",
                 []),
                ("2.1.4", KA7,
                 "Stellt die Organisation (Verwaltungsbehörde / zwischengeschaltete Stelle) sicher, dass jede Person, die an Vorbereitung, Verhandlung, Verwaltung oder Durchsetzung eines die Organisation betreffenden Vertrags beteiligt ist oder sein kann, der Organisation jedes für den Vertrag relevante private Interesse angezeigt hat?",
                 []),
                ("2.1.5", KA7,
                 "Untersagt die Organisation Mitarbeitenden u. a. die Beteiligung an Vorbereitung, Verhandlung, Verwaltung oder Durchsetzung eines Vertrags, wenn ein relevantes Interesse besteht, oder verlangt sie, dass das relevante Interesse vor einer solchen Tätigkeit aufgegeben oder anderweitig geregelt wird?",
                 []),
                ("2.1.6", KA7,
                 "Hebt die Einrichtung einen Vertrag auf oder ändert ihn, wenn nachgewiesen ist, dass das Vergabeverfahren durch einen Interessenkonflikt oder korruptes Verhalten erheblich beeinträchtigt ist?",
                 []),
                ("2.1.7", KA7,
                 "Bewertet die Organisation, wenn ein Vertrag durch eine beteiligte Person möglicherweise beeinträchtigt wurde, rückwirkend weitere wesentliche Entscheidungen dieser Person in amtlicher Eigenschaft, um sicherzustellen, dass auch diese nicht in ähnlicher Weise beeinträchtigt waren?",
                 ["Falls ja: Verfolgt die Einrichtung dies nach? Und wie?"]),
            ]),
            ("2.2 — Öffentliche Auftragsvergabe und Interessenkonflikte", [
                ("2.2.1", KA7,
                 "Prüft die Einrichtung die Teilnahme an einem Bewertungsausschuss für ein Vergabe- oder Zuwendungsverfahren daraufhin, ob die Person mittelbar oder unmittelbar finanziell vom Ergebnis dieser Verfahren profitieren kann?",
                 []),
                ("2.2.2", KA7,
                 "Prüft die Einrichtung (und wie) Fälle, in denen ein Teilnehmer versucht, den Entscheidungsprozess der Vergabestelle während eines Vergabeverfahrens unzulässig zu beeinflussen?",
                 []),
                ("2.2.3", KA7,
                 "Prüft die Einrichtung (und wie) alle Stufen eines Vergabeverfahrens (Vorbereitung der Ausschreibung, Auswahl der Bieter/Bewerber und Zuschlagserteilung sowie die Phase nach der Ausschreibung)?",
                 ["Falls die vorstehende Frage mit „Ja“ beantwortet wird: Ist das Verfahren der Überprüfung und Kontrolle angemessen?"]),
                ("2.2.4", KA7,
                 "Wurde — soweit zutreffend und falls das Verfahren einer vorherigen Ex-ante-Prüfung unterlag — diese ordnungsgemäß durch die Verwaltungsbehörde getestet und kontrolliert?",
                 []),
            ]),
            ("2.3 — Insiderinformationen", [
                ("2.3.1", KA7,
                 "Hat die Organisation eine Politik und ein Verwaltungsverfahren festgelegt, um sicherzustellen, dass Insiderinformationen — insbesondere privilegierte Informationen — durch das Personal sicher gehalten und nicht missbraucht (intern oder nach außen weitergegeben) werden? Insbesondere: geschäftlich sensible Informationen; Steuer- und Regulierungsinformationen; personenbezogene sensible Informationen; Informationen aus Strafverfolgung und Strafverfahren; Informationen zur Wirtschaftspolitik der Regierung und zum Finanzmanagement.",
                 []),
                ("2.3.2", KA7,
                 "Hat die Organisation eine Politik und ein Verwaltungsverfahren festgelegt, um sicherzustellen, dass im Fall eines Hinweisgebers dessen Rechte geschützt und gewahrt werden? Wurde dies ordnungsgemäß kontrolliert?",
                 []),
                ("2.3.3", KA7,
                 "Gibt es ein Verfahren zum Schutz von Hinweisgebern?",
                 []),
                ("2.3.4", KA7,
                 "Falls die vorstehende Frage mit „Ja“ beantwortet wird: Ist das Verfahren angemessen ausgestaltet und wirksam?",
                 ["Ist es für jeden potenziellen Hinweisgeber offen und sichtbar?"]),
                ("2.3.5", KA7,
                 "Findet nach dem Hinweis eines Hinweisgebers eine angemessene Nachverfolgung statt?",
                 []),
                ("2.3.6", KA7,
                 "Ist das gesamte Personal über das Bestehen der Politik und des Verfahrens informiert?",
                 []),
                ("2.3.7", KA7,
                 "Sind alle Führungskräfte über ihre jeweilige Verantwortung zur Durchsetzung der Politik informiert?",
                 []),
            ]),
            ("2.4 — Ernennung / Einstellung von Amtsträgern und Interessenkonflikte", [
                ("2.4.1", KA7,
                 "Gibt es ein verlässliches, schriftlich festgelegtes Verfahren zur Ernennung / Einstellung von Amtsträgern? Sind Ausnahmen dokumentiert?",
                 []),
                ("2.4.2", KA7,
                 "Ist sichergestellt, dass kein Nepotismus stattfindet? Und falls ja, ist dieser Sicherstellungsprozess angemessen? Bitte prüfen, wie die Einrichtung dies sicherstellt.",
                 ["Nepotismus liegt vor, wenn Eingestellte Verwandte der einstellenden Amtsperson sind oder anschließend von einem anderen Verwandten beaufsichtigt werden."]),
                ("2.4.3", KA7,
                 "Ist sichergestellt, dass keine Begünstigung (Favoritismus) stattfindet? Und falls ja, ist dieser Sicherstellungsprozess angemessen? Bitte prüfen, wie die Einrichtung dies sicherstellt.",
                 ["Gemeint ist die Begünstigung von Familie und Freunden."]),
            ]),
            ("2.5 — Drehtüreffekte (Revolving Doors) und Interessenkonflikte", [
                ("2.5.1", KA7,
                 "Prüft die Einrichtung, dass keine Drehtüreffekte auftreten?",
                 ["Drehtüreffekte bezeichnen den Wechsel von Personen in und aus dem öffentlichen Dienst, statt diesen als lebenslange Laufbahn auszuüben. Solche Wechsel schaffen Situationen mit erhöhtem Risiko für Interessenkonflikte — z. B. wenn eine Person beim Eintritt in den öffentlichen Dienst fortbestehende finanzielle oder starke persönliche Bindungen zu früheren Arbeitsumfeldern mitbringt."]),
            ]),
            ("2.6 — Amtliche Entscheidungsfindung und Interessenkonflikte", [
                ("2.6.1", KA7,
                 "Stellt die Organisation sicher, dass jede beschäftigte Person, die bedeutende amtliche Entscheidungen trifft oder daran mitwirkt, der Organisation jedes für eine Entscheidung relevante private Interesse angezeigt hat, das einen Interessenkonflikt der entscheidenden Person begründen könnte?",
                 []),
                ("2.6.2", KA7,
                 "Stellt die Organisation sicher, dass jede beschäftigte Person, die bedeutende amtliche Entscheidungen trifft oder daran mitwirkt, jedes relevante private Interesse angezeigt hat, das einen Interessenkonflikt begründen könnte?",
                 ["Dies kann Ressourcen, Strategien, Personal, Funktionen sowie administrative oder gesetzliche Zuständigkeiten der Einrichtung betreffen. Zu prüfen sind beispielsweise Entscheidungen über Ausgaben, Beschaffung, Mittelzuweisung, Umsetzung eines Gesetzes oder einer Politik, Ernennung auf eine Stelle, Einstellung, Beförderung, Disziplinarmaßnahmen, Leistungsbeurteilung usw."]),
                ("2.6.3", KA7,
                 "Untersagt die Organisation Mitarbeitenden u. a. die Beteiligung an Vorbereitung, Verhandlung, Verwaltung oder Durchsetzung einer amtlichen Entscheidung, wenn ein relevantes Interesse besteht, oder verlangt sie, dass das relevante Interesse vor einer solchen Entscheidung aufgegeben oder anderweitig geregelt wird?",
                 []),
                ("2.6.4", KA7,
                 "Hat die Organisation die Befugnis — durch Gesetz oder auf andere Weise —, eine amtliche Entscheidung zu überprüfen und zu ändern oder aufzuheben, wenn nachgewiesen ist, dass der Entscheidungsprozess durch einen Interessenkonflikt oder korruptes Verhalten eines Mitarbeitenden erheblich beeinträchtigt war?",
                 []),
            ]),
            ("2.7 — Politikberatung und Interessenkonflikte", [
                ("2.7.1", KA7,
                 "Stellt die Organisation sicher, dass jede Person, die die Regierung oder andere Amtsträger berät, der Organisation jedes für diese Beratung relevante private Interesse angezeigt hat, das einen Interessenkonflikt der beratenden Person begründen könnte?",
                 ["Dies kann jede amtliche Angelegenheit betreffen, z. B. eine politische Maßnahme, Strategie, ein Gesetz, Ausgaben, Beschaffung, die Umsetzung einer Politik oder eines Gesetzes, einen Vertrag, eine Haushaltsmaßnahme, die Ernennung auf eine Stelle oder eine Verwaltungsstrategie."]),
                ("2.7.2", KA7,
                 "Untersagt die Organisation Mitarbeitenden u. a. die Beteiligung an Vorbereitung, Verhandlung oder Befürwortung einer amtlichen Politikberatung, wenn ein relevantes Interesse besteht, oder verlangt sie, dass das relevante Interesse vor dem Erstellen oder Erteilen einer solchen Beratung aufgegeben oder anderweitig geregelt wird?",
                 []),
                ("2.7.3", KA7,
                 "Verfügt die Organisation über die Fähigkeit und die Verfahren, eine amtliche Politikberatung zu überprüfen und zurückzuziehen, wenn nachgewiesen ist, dass der Beratungsprozess durch einen Interessenkonflikt oder korruptes Verhalten eines Mitarbeitenden bzw. eines Amtsträgers erheblich beeinträchtigt war?",
                 []),
            ]),
            ("2.8 — Geschenke / Vorteile und Interessenkonflikte", [
                ("2.8.1", KA7,
                 "Behandelt die geltende Politik der Organisation Interessenkonflikte, die sich aus herkömmlichen wie aus sämtlichen sonstigen Formen von Geschenken oder Vorteilen ergeben?",
                 []),
                ("2.8.2", KA7,
                 "Verfügt die Organisation über ein festgelegtes Verwaltungsverfahren zur Kontrolle von Geschenken — etwa durch Festlegung zulässiger und unzulässiger Geschenke, durch die Annahme bestimmter Geschenkarten im Namen der Organisation, durch Entsorgung oder Rückgabe unzulässiger Geschenke, durch Hinweise an Empfänger zur Ablehnung von Geschenken und durch die Meldung erheblicher angebotener Geschenke?",
                 []),
            ]),
            ("2.9 — Sonstige Tätigkeiten, die einen Interessenkonflikt auslösen können", [
                ("2.9.1", KA7,
                 "Erkennt die Organisation das Potenzial für Interessenkonflikte an, das sich aus Erwartungen ergibt, die einzelnen Amtsträgern durch ihre unmittelbare Familie oder ihre Gemeinschaft — einschließlich religiöser oder ethnischer Gemeinschaften — gestellt werden, insbesondere in einem multikulturellen Kontext?",
                 []),
                ("2.9.2", KA7,
                 "Erkennt die Organisation das Potenzial für Interessenkonflikte an, das sich aus der Beschäftigung oder geschäftlichen Tätigkeit anderer Mitglieder der unmittelbaren Familie eines beschäftigten Amtsträgers ergibt?",
                 []),
                ("2.9.3", KA7,
                 "Legt die Organisation die Umstände fest, unter denen ein Amtsträger eine gleichzeitige Bestellung übernehmen oder gleichzeitig im Vorstand oder Kontrollorgan einer externen Organisation tätig sein darf — insbesondere wenn diese Stelle in einem vertraglichen, regulatorischen, partnerschaftlichen oder Sponsoring-Verhältnis zur beschäftigenden Organisation steht oder stehen könnte?",
                 ["Zum Beispiel: eine Gemeinschaftsgruppe oder NRO; eine berufliche oder politische Organisation; eine andere staatliche Organisation oder Stelle; ein staatseigenes Unternehmen oder eine kommerzielle öffentliche Organisation."]),
                ("2.9.4", KA7,
                 "Werden Beteiligungen an privaten Unternehmen, die aus Personen in Leitungspositionen der staatlichen Verwaltung bestehen, ordnungsgemäß gemeldet und geregelt?",
                 ["Sonderfälle."]),
                ("2.9.5", KA7,
                 "Besteht eine ordnungsgemäße Funktionstrennung, um sicherzustellen, dass Minister und Parlamentsmitglieder nicht Teil von Aufsichts- oder Leitungsorganen privater Unternehmen und ihrer Subunternehmer sind?",
                 ["Dieser Test wird ausschließlich mit Bezug auf den EU-Haushalt durchgeführt."]),
                ("2.9.6", KA7,
                 "Wird der Einfluss von Beratungsgruppen ordnungsgemäß gemeldet und geregelt?",
                 ["Beispiel: Wenn Unternehmensvertreter oder Interessenvertreter Regierungen als Mitglieder einer Beratungsgruppe beraten, wirken sie mit direktem Einfluss auf Entscheidungsträger am Entscheidungsprozess mit, während sie zugleich eigene private Interessen verfolgen."]),
            ]),
        ],
    ),
    (
        "Zielsetzung 3 — Mechanismen zur Prävention und Aufdeckung von Interessenkonflikten",
        "Ziel: Nachweis geeigneter Mechanismen zur Prävention und Aufdeckung von "
        "Interessenkonflikten. Die nachstehenden Tests beziehen sich ausschließlich "
        "auf den EU-Haushalt; jede Überprüfung der hier betrachteten Prozesse und "
        "Verfahren bezieht sich auf deren mögliche Auswirkungen auf den EU-Haushalt.",
        [
            ("3.1 — Präventivmaßnahmen", [
                ("3.1.1", KA7,
                 "Besteht ein Prozess, der die folgenden Präventivmaßnahmen vorsieht?",
                 [
                     "Beschränkungen der Nebentätigkeit;",
                     "Erklärung der persönlichen Einkünfte;",
                     "Erklärung der Familieneinkünfte;",
                     "Erklärung des persönlichen Vermögens;",
                     "Erklärung des Familienvermögens;",
                     "Erklärung von Geschenken;",
                     "Sicherheit und Kontrolle des Zugangs zu internen Informationen (beteiligte Akteure wahren vertrauliche Informationen);",
                     "Erklärung privater Interessen, die für die Verwaltung von Verträgen relevant sind;",
                     "Erklärung privater Interessen, die für die Entscheidungsfindung relevant sind;",
                     "Erklärung privater Interessen, die für die Mitwirkung an der Vorbereitung oder Erteilung von Politikberatung relevant sind;",
                     "öffentliche Bekanntgabe der Einkommens- und Vermögenserklärungen;",
                     "Beschränkungen und Kontrolle geschäftlicher oder NRO-Tätigkeiten vor und nach der Beschäftigung.",
                     "Erinnerung an besondere Aspekte von Bindungen, z. B. emotionale Beziehungen, politische und/oder nationale Verbundenheit (je nach Prüfungsgegenstand und -umfang im Verlauf der Prüfung zu betrachten).",
                 ]),
                ("3.1.2", KA7,
                 "Besteht ein geeigneter Prozess, um Folgendes sicherzustellen?",
                 [
                     "Beschränkungen und Kontrolle von Geschenken und sonstigen Formen von Vorteilen sind vorhanden;",
                     "Beschränkungen und Kontrolle externer gleichzeitiger Bestellungen (z. B. bei einer NRO, politischen Organisation oder einem staatseigenen Unternehmen);",
                     "Befangenheitsausschluss und routinemäßiger Rückzug von Amtsträgern aus der Amtsausübung, wenn die Teilnahme an einer Sitzung oder eine bestimmte Entscheidung sie in einen Interessenkonflikt brächte;",
                     "Veräußerung — durch Verkauf von Geschäftsanteilen oder Investitionen oder durch Einrichtung eines Treuhand- bzw. Blind-Management-Vertrags — vor Eintritt in einen möglichen Interessenkonflikt.",
                 ]),
                ("3.1.3", KA7,
                 "Verfügen die Führungskräfte über ein angemessenes Maß an Sensibilisierung?",
                 [
                     "Ist die Grundhaltung der Führungsebene (Tone at the Top) angemessen?",
                     "Die Prüfer sollten hier — soweit zutreffend — Folgendes berücksichtigen: 1. Politiken und Verfahren; 2. das Sensibilisierungsniveau innerhalb der Organisation testen; 3. die Häufigkeit der Sensibilisierungsmaßnahmen testen (mindestens jährliche Aktualisierung, im Einzelfall zu beurteilen); 4. die Einbeziehung der Sensibilisierung in die Kontrollstrategie testen; 5. testen, ob dies neuen Mitarbeitenden als Willkommenspaket bereitgestellt wird; 6. Umsetzung eines Verhaltenskodex; 7. Interessenerklärungen, Vermögensoffenlegung und ausschließliche Funktionen; 8. Abgleich von Informationen aus Handelsregister-Datenbanken, Datenbanken nationaler Stellen zur Prüfung von Arbeitsverträgen zwischen natürlichen und juristischen Personen, öffentlichen Registern, Personalakten und sonstigen relevanten Informationen.",
                 ]),
            ]),
        ],
    ),
    (
        "Zielsetzung 4 — Werkzeuge zur Aufdeckung von Interessenkonflikten",
        "Ziel: Nachweis ausreichender und ordnungsgemäß genutzter Werkzeuge zur "
        "Aufdeckung von Interessenkonflikten.",
        [
            ("4.1 — Risikoindikatoren eines möglichen Interessenkonflikts", [
                ("4.1.1", KA7,
                 "Prüfen Sie, ob spezifische und geeignete Risikoindikatoren vorhanden sind. Dazu können unter anderem gehören:",
                 [
                     "Fehlen einer Erklärung zum Interessenkonflikt, wo diese verpflichtend oder gefordert ist;",
                     "Fehlen einer Erklärung zum Interessenkonflikt, obwohl diese ihrer Art nach erforderlich wäre, eine entsprechende Pflicht aber nicht besteht;",
                     "Risiko unvollständiger oder zweckungeeigneter Erklärungen;",
                     "fehlende Kontrollen und Prüfungen zu Vorliegen und Vollständigkeit der Erklärungen;",
                     "ein Mitarbeitender der Vergabestelle hat unmittelbar vor seinem Eintritt für ein Unternehmen gearbeitet, das sich an einer von ihm vorzubereitenden Ausschreibung beteiligen könnte;",
                     "ein Mitarbeitender der Vergabestelle hat ein unmittelbares Familienmitglied (oder eine emotional verbundene Person), das für ein Unternehmen arbeitet, das sich an einer Ausschreibung beteiligen könnte;",
                     "Änderung der Vertragsbedingungen zwischen Begünstigtem und Auftragnehmer;",
                     "Beziehungen/Bekanntschaft zwischen dem letztlich Begünstigten und Auftragnehmern;",
                     "Begünstigter und beauftragter Subunternehmer teilen sich Büroräume/Geschäftsräume/Adresse, oder Ähnlichkeiten in Firmennamen deuten auf wirtschaftliche Verflechtung hin;",
                     "Mitglieder des Bewertungsausschusses verfügen nicht über die nötige fachliche Expertise zur Bewertung der eingereichten Angebote und werden von einer einzelnen Person gesteuert, die mit einem Bieter oder einem seiner Subunternehmer verbunden ist;",
                     "Spezifikationen ähneln sehr stark dem Produkt oder den Leistungen des erfolgreichen Bieters, insbesondere wenn sie sehr spezifische Anforderungen enthalten, die nur wenige Bieter erfüllen könnten;",
                     "Beschränkungen und Kontrolle geschäftlicher oder NRO-Tätigkeiten vor und nach der Beschäftigung;",
                     "Begünstigter wurde unmittelbar vor der Antragstellung auf die Zuwendung gegründet;",
                     "wenige Antragsteller oder weniger Antragsteller als erwartet bei einem Aufruf zur Einreichung von Vorschlägen/Angeboten;",
                     "Fälle mit nur einem einzigen Bieter;",
                     "dasselbe Unternehmen gewinnt wiederholt aufeinanderfolgende Aufträge;",
                     "mangelhafte Vertragserfüllung führt nicht zur Anwendung von Vertragsstrafen oder zum Ausschluss des Auftragnehmers/Dienstleisters von weiteren Aufträgen;",
                     "Änderungen von Verträgen nach Abschluss des Vergabeverfahrens.",
                 ]),
                ("4.1.2", KA7,
                 "Werden IT-Werkzeuge wie ARACHNE oder andere alternative Risiko-Scoring- und Data-Mining-Werkzeuge angemessen eingesetzt — zum Abgleich zwischen natürlichen und juristischen Personen, öffentlichen Registern, Personalakten und sonstigen relevanten Informationen?",
                 []),
            ]),
        ],
    ),
]

CONCLUSION = (
    "Gesamtschlussfolgerung: Werden die Anforderungen des Art. 61 der "
    "Haushaltsordnung zur Vermeidung von Interessenkonflikten eingehalten? Die "
    "Prüfer schließen, ob Prävention, Aufdeckung und Behebung von "
    "Interessenkonflikten im Verwaltungs- und Kontrollsystem angemessen "
    "ausgestaltet und wirksam sind."
)


def _uid():
    return str(uuid.uuid4())


def run():
    db = SessionLocal()
    try:
        # Idempotenz: vorhandenen Seed entfernen
        existing = db.query(ChecklistTemplate).filter(
            (ChecklistTemplate.source_document_name == SOURCE_DOC)
            | (ChecklistTemplate.title == TITLE)
        ).all()
        for tpl in existing:
            db.delete(tpl)
        db.commit()

        owner = (
            db.query(Registration)
            .filter(Registration.status == "active")
            .order_by((Registration.role == "admin").desc())
            .first()
        )
        owner_id = owner.id if owner else None

        tpl = ChecklistTemplate(
            id=_uid(),
            owner_id=owner_id,
            title=TITLE,
            description=(
                "Musterprüfcheckliste der Europäischen Kommission zu "
                "Interessenkonflikten (Kernanforderung 7, KA7), Förderperiode "
                "2021-2027 — ins Deutsche übertragen und in die Designer-Struktur "
                "überführt. Sie umfasst vier Zielsetzungen (Kontrollumfeld, "
                "Handlungen der Akteure, Präventions-/Aufdeckungsmechanismen, "
                "Aufdeckungswerkzeuge) auf Grundlage von Art. 61 der "
                "Haushaltsordnung. Englisches Original (XLSX) siehe Quelldokument."
            ),
            source_language="en",
            target_language="de",
            source_document_name=SOURCE_DOC,
            source_document_path=SOURCE_PATH,
            status="published",
            properties_json={
                "audit_code": "",
                "member_state": "",
                "cci_programme": "",
                "prepared_by": "", "prepared_date": "",
                "reviewed_by": "", "reviewed_date": "",
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.6 (KA7)",
            },
        )
        db.add(tpl)

        # Antwortset
        aset = ChecklistAnswerSet(
            id=_uid(), template_id=tpl.id, name=ANSWER_SET["name"],
            description=ANSWER_SET["description"], sort_order=0,
        )
        db.add(aset)
        for i, opt in enumerate(ANSWER_SET["options"]):
            db.add(ChecklistAnswerOption(
                id=_uid(), answer_set_id=aset.id, name=opt["name"], sort_order=i,
                is_standard=opt.get("is_standard", False),
                is_entfaellt=opt.get("is_entfaellt", False),
            ))

        order = 0

        def add_node(**kw):
            nonlocal order
            kw.setdefault("id", _uid())
            kw.setdefault("template_id", tpl.id)
            kw.setdefault("sort_order", order)
            order += 1
            n = ChecklistTemplateNode(**kw)
            db.add(n)
            return n

        # Allgemeine Angaben (Kopfblock als Felder)
        h_meta = add_node(node_type="HEADING", title="Allgemeine Angaben")
        for label, atype in HEADER_FIELDS:
            add_node(node_type="QUESTION", parent_id=h_meta.id, title=label,
                     answer_type=atype, eingabetyp=(4 if atype == "DATE" else 1),
                     is_header_field=True)

        # Hinweis für Prüfer
        h_intro = add_node(node_type="HEADING", title="Hinweise für Prüfer")
        add_node(node_type="HINT", parent_id=h_intro.id, title=INSTRUCTION)

        # Zielsetzungen → Unterabschnitte → Fragen
        for part_title, part_intro, sections in PARTS:
            h_part = add_node(node_type="HEADING", title=part_title)
            if part_intro:
                add_node(node_type="HINT", parent_id=h_part.id,
                         title=f"Hinweis: {part_intro}")
            for section_title, questions in sections:
                # Unterabschnitt als eigene Überschrift, falls vorhanden;
                # andernfalls hängen die Fragen direkt an der Zielsetzung.
                section_parent = h_part
                if section_title:
                    section_parent = add_node(
                        node_type="HEADING", parent_id=h_part.id,
                        title=section_title,
                    )
                for key, legal, frage, hinweise in questions:
                    q = add_node(
                        node_type="QUESTION", parent_id=section_parent.id,
                        title=f"{key} {frage}",
                        answer_type="CUSTOM_ENUM", eingabetyp=0,
                        answer_set_id=aset.id,
                        legal_reference=legal,
                        relevant_documents_json=BELEGE,
                    )
                    for hinweis in hinweise:
                        add_node(node_type="HINT", parent_id=q.id,
                                 title=f"Hinweis: {hinweis}")

        # Schlussfolgerung
        h_concl = add_node(node_type="HEADING", title="Schlussfolgerung")
        add_node(node_type="QUESTION", parent_id=h_concl.id, title=CONCLUSION,
                 answer_type="CUSTOM_ENUM", eingabetyp=0, answer_set_id=aset.id)

        # Owner als Mitglied
        if owner_id:
            db.add(ChecklistMember(
                id=_uid(), template_id=tpl.id, user_id=owner_id, role="owner",
            ))

        # Statistik
        node_count = order
        tpl.statistics_json = {"node_count": node_count}
        db.commit()
        print(f"Seed OK: Template {tpl.id} '{TITLE}' mit {node_count} Knoten, "
              f"Owner={owner_id}, Antwortset '{aset.name}'.")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Seed FEHLGESCHLAGEN: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
