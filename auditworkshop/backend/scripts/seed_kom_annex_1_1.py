"""
flowworkshop · scripts/seed_kom_annex_1_1.py

Seedet die KOM-Mustercheckliste "Annex 1.1 — Selection of operations (KA2)"
als deutsche, in die audit_designer-Struktur überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Teil A/B/C (Überschriften) →
Fragen (mit Rechtsgrundlage, Antwortset Ja/Nein/Teilweise/Entfällt, Belegen
und "Notes for auditor" als HINT-Kindknoten). Englisches Original bleibt als
source_document hinterlegt.

Idempotent: vorhandener Seed (gleiche source_document_name) wird zuvor entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_1.py
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

SOURCE_DOC = "Annex 1.1 Selection of operations (KR2).docx"
SOURCE_PATH = "checklist_sources/annex_1_1_selection_of_operations.docx"
TITLE = "KOM — Auswahl der Vorhaben (KA2)"

INSTRUCTION = (
    "Hinweis: Die Checkliste dient der Beurteilung, ob das "
    "Verwaltungs- und Kontrollsystem (VKS) und die Vorhaben den Anforderungen "
    "an die Auswahl der Vorhaben entsprechen. Idealerweise wird sie für "
    "aussagekräftige Prüfungen sowohl ausgewählter als auch — in mindestens "
    "einem Fall — abgelehnter Vorhaben verwendet. Die Fragen leiten sich aus "
    "der Verordnung ab und spiegeln die wesentlichen Prüfpunkte wider."
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

# Kopfblock-Felder (Allgemeine Angaben)
HEADER_FIELDS = [
    ("Audit-Code", "TEXT"),
    ("CCI / Programm(e)", "TEXT"),
    ("Codes und Titel der ausgewählten Projekte (falls zutreffend)", "TEXT"),
    ("Checkliste erstellt — Name", "TEXT"),
    ("Checkliste erstellt — Datum", "DATE"),
    ("Checkliste geprüft — Name", "TEXT"),
    ("Checkliste geprüft — Datum", "DATE"),
]

# Teile mit Fragen: (key, legal_reference, frage_de, belege_de[list], note_de)
PARTS = [
    ("Teil A — Festgelegte Auswahlmethodik, Kriterien und Förderfähigkeitsregeln (BK 2.1 und 2.2)", [
        ("1", "KA2 BK2.1 · Art. 40(2) und 73(1) CPR · Art. 22 Interreg-VO",
         "Hat die Verwaltungsbehörde eine geeignete Auswahlmethodik und -kriterien aufgestellt, die anschließend vom Begleitausschuss genehmigt wurden?",
         ["Auswahlmethodik oder vergleichbares Dokument", "Beschluss des Begleitausschusses"],
         "Die Verwaltungsbehörde ist verpflichtet, Kriterien und Verfahren für die Auswahl der Vorhaben festzulegen. Bei Interreg-Programmen liegt die Verantwortung beim Begleitausschuss (in der Praxis schlägt die VB/das gemeinsame Sekretariat die Kriterien vor, der Begleitausschuss genehmigt sie). Methodik und Kriterien einschließlich aller Änderungen müssen vom Begleitausschuss genehmigt werden."),
        ("2", "KA2 BK2.1 · Art. 73(1) CPR · Art. 22 Interreg-VO",
         "Stellen die Auswahlverfahren und -kriterien sicher, dass die auszuwählenden Vorhaben mit Blick auf einen maximalen Beitrag der Unionsförderung zur Erreichung der Programmziele priorisiert werden?",
         ["Auswahlmethodik oder vergleichbares Dokument", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Prüfen, ob sowohl Kriterien als auch Methodik genehmigt wurden. Prüfen, ob die genehmigten Kriterien hinreichend detailliert sind (Unterkriterien sind gute Praxis, aber nicht zwingend)."),
        ("3", "KA2 BK2.1 · Art. 73(1) CPR · Art. 22 Interreg-VO",
         "Sind die Auswahlverfahren und -kriterien nichtdiskriminierend und transparent?",
         ["Auswahlmethodik oder vergleichbares Dokument", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Auf die Genehmigung von Kriterien und Methodik achten; Klarheit und Nachvollziehbarkeit der Kriterien prüfen."),
        ("4", "KA2 BK2.1 · Art. 73(1) CPR · Art. 22 Interreg-VO",
         "Gewährleisten die Auswahlverfahren und -kriterien die Zugänglichkeit für Menschen mit Behinderungen, die Gleichstellung der Geschlechter und die Berücksichtigung der Charta der Grundrechte der EU sowie des Grundsatzes der nachhaltigen Entwicklung und der Umweltpolitik der Union (Art. 11 und Art. 191(1) AEUV)?",
         ["Auswahlmethodik oder vergleichbares Dokument", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Querschnittsziele und Grundrechte müssen in den Auswahlkriterien berücksichtigt sein."),
        ("5", "KA2 BK2.1 · Art. 73(1) CPR · Art. 22 Interreg-VO",
         "Stellen die Auswahlkriterien sicher, dass die ausgewählten Vorhaben mit der Vermeidung erheblicher Beeinträchtigungen (DNSH) vereinbar sind?",
         ["Auswahlmethodik oder vergleichbares Dokument", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Programme sollten nur Tätigkeiten fördern, die keine erhebliche Beeinträchtigung der Umweltziele im Sinne von Art. 17 der VO (EU) 2020/852 verursachen."),
        ("6", "KA2 BK2.2 · Art. 63, 64, 67 und 68 CPR · Art. 37-44 und 56 Interreg-VO",
         "Sind die Förderfähigkeitsregeln für Ausgaben auf nationaler/regionaler Ebene festgelegt?",
         ["Bestehende nationale/regionale Rechtsvorschriften/Leitfäden", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Prüfen und angeben, wo die Förderfähigkeitsregeln geregelt sind (Programm, nationale Regeln, nationales Recht). Für Interreg gelten gesonderte Regeln (Art. 37-44 VO (EU) 2021/1059)."),
        ("7", "KA2 BK2.2 · Art. 63, 64, 67 und 68 CPR · Art. 37-44 und 56 Interreg-VO",
         "Sind klar definierte und eindeutige Förderfähigkeitsregeln für das Programm/die Aufforderung zur Einreichung von Vorschlägen festgelegt?",
         ["Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Klare Regeln sind mindestens festzulegen zu: Arten von Begünstigten; Arten von Vorhaben; geografischem Gebiet; Beginn/Ende der Förderfähigkeit; Formen der Unterstützung (Realkosten; vereinfachte Kostenoptionen); anwendbaren Sonderregeln (CLLD, Beihilfen, Finanzinstrumente)."),
        ("8", "KA3 BK3.2 · Art. 63, 64, 67, 68 und 73(1) CPR · Art. 22, 37-44, 56 Interreg-VO",
         "Entsprechen die in den veröffentlichten Aufforderungen zur Einreichung von Vorschlägen enthaltenen Kriterien (einschließlich Unterkriterien) und die Methodik den vom Begleitausschuss genehmigten?",
         ["Beschluss des Begleitausschusses", "Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen"],
         "Die veröffentlichten Aufforderungen zur Einreichung von Vorschlägen müssen der vom Begleitausschuss genehmigten Methodik und den Kriterien folgen. Besonders auf Aufforderungen achten, in denen Unterkriterien nicht in den genehmigten Dokumenten enthalten waren."),
        ("9", "KA2 BK2.2 · Art. 53 CPR",
         "Falls die Aufforderung zur Einreichung von Vorschlägen eine spezifische SCO-/FNLC-Methodik im Verhältnis VB-Begünstigte verwendet ('lower level' SCO): Entspricht diese einer von der EK genehmigten ('upper level' SCO)? Falls nicht, entspricht die Methodik den Anforderungen der Dachverordnung?",
         ["SCO-Methodik(en)"],
         "Bei 'lower level'-SCO (Verhältnis VB-Begünstigte), die nicht von der EK im Rahmen des Programms genehmigt wurden, muss die VB sicherstellen, dass die Methodik Art. 53 entspricht (Checkliste zur SCO-Beurteilung verwenden)."),
        ("10", "KA3 BK3.3 · Art. 49(1)-(2) CPR · Art. 36(1)-(2) Interreg-VO",
         "Werden die Förderfähigkeitsregeln den Begünstigten kommuniziert?",
         ["Veröffentlichte Aufforderungen zur Einreichung von Vorschlägen", "Website der VB/zwischengeschalteten Stelle oder dedizierte nationale Website"],
         "Prüfen, ob die Informationen zu den Aufforderungen zur Einreichung von Vorschlägen veröffentlicht und allen potenziellen Begünstigten zugänglich sind. Die Aufforderung muss mindestens enthalten: klare Beschreibung des Auswahlverfahrens, vollständige Förderfähigkeitsregeln, Rechte und Pflichten der Begünstigten. Nicht anwendbar bei Direktzuweisung sowie bei Förderung nach Art. 29(1) und (3) CPR."),
    ]),
    ("Teil B — Auswahlprozess", [
        ("11", "KA2 BK2.3 · Art. 69(8), 73 und Anhang XVI §4 CPR · Art. 22 Interreg-VO",
         "Werden alle fristgerecht eingegangenen Projektanträge im elektronischen Datenaustauschsystem registriert?",
         ["Verfahrenshandbücher der VB/zwischengeschalteten Stelle", "Arbeitsunterlagen", "IT-System"],
         "Zur Gewährleistung der Gleichbehandlung potenzieller Begünstigter und eines angemessenen Prüfpfads."),
        ("12", "KA2 BK2.3 · Art. 69(8), 73 und Anhang XVI §4 CPR",
         "Haben alle Antragsteller eine Eingangsbestätigung der zuständigen Stelle erhalten?",
         ["Verfahrenshandbücher", "Arbeitsunterlagen", "IT-System"],
         "Prüfen anhand von: Titel und Datum der Aufforderung zur Einreichung von Vorschlägen; Einreichungsfrist; Datum und Form des Eingangs; bestätigende Stelle."),
        ("13", "KA2 BK2.3 · Art. 69(8), 73 und Anhang XVI §4 CPR",
         "Sind bei Anträgen, die zur Korrektur oder wegen fehlender Unterlagen zurückgegeben wurden, die Gründe gerechtfertigt und dokumentiert?",
         ["Verfahrenshandbücher", "Arbeitsunterlagen", "IT-System"],
         "Abgleich mit den Vorgaben der Aufforderung zur Einreichung von Vorschlägen (z. B. Kapitel zur Rückgabe wegen Schreibfehlern oder fehlender Unterlagen)."),
        ("14", "KA2 BK2.4 · Art. 73 CPR · Art. 22 Interreg-VO",
         "Erfolgt die Bewertung auf Basis der zuvor vom Begleitausschuss genehmigten und in der Aufforderung zur Einreichung von Vorschlägen veröffentlichten Auswahlkriterien — ohne andere Kriterien oder abweichende Gewichtungen/Bewertungen?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Prüfen, ob das Auswahlverfahren auf den in der Aufforderung zur Einreichung von Vorschlägen veröffentlichten Bestimmungen beruht."),
        ("15", "KA2 BK2.4 · Art. 73 CPR · Art. 22 Interreg-VO",
         "Wird die Bewertung konsistent und nichtdiskriminierend angewandt? Wird jeder eingereichte Antrag derselben Beurteilung unterzogen?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Prüfen, ob das Bewertungsverfahren für alle Anträge einer Aufforderung zur Einreichung von Vorschlägen einheitlich angewandt wird (Gleichbehandlung)."),
        ("16", "KA2 BK2.4 · Art. 73(2)a CPR · Art. 22(4)a Interreg-VO",
         "Stellt die VB/der Begleitausschuss bei der Bewertung sicher, dass die ausgewählten Vorhaben den Programmzielen entsprechen (Konsistenz mit den zugrunde liegenden Strategien) und einen wirksamen Beitrag zu den spezifischen Programmzielen leisten?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Bei Interreg: sicherstellen, dass die Vorhaben dem Interreg-Programm entsprechen und wirksam zu dessen spezifischen Zielen beitragen."),
        ("17", "KA2 BK2.4 · Art. 73(2)b CPR · Art. 22(4)b Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass Vorhaben im Anwendungsbereich einer grundlegenden Voraussetzung mit den entsprechenden Strategien und Planungsdokumenten im Einklang stehen?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Bei Interreg: sicherstellen, dass die Vorhaben nicht im Widerspruch zu den nach Art. 10(1) Interreg-VO festgelegten Strategien stehen."),
        ("18", "KA2 BK2.4 · Art. 73(2)c CPR · Art. 22(4)c Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass die ausgewählten Vorhaben das beste Verhältnis zwischen Förderbetrag, durchgeführten Tätigkeiten und Zielerreichung aufweisen?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Auf Wirtschaftlichkeit (best value for money) prüfen."),
        ("19", "KA2 BK2.4 · Art. 73(2)d CPR · Art. 22(4)d Interreg-VO",
         "Stellt die VB/der Begleitausschuss bei Vorhaben mit Infrastruktur- oder produktiven Investitionen sicher, dass der Begünstigte über die nötigen finanziellen Mittel und Mechanismen zur Deckung der Betriebs- und Instandhaltungskosten verfügt (finanzielle Tragfähigkeit)?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Geschäftsplan/Verfügbarkeit anderer Mittel prüfen."),
        ("20", "KA2 BK2.4 · Art. 73(2)e CPR · Art. 22(4)e Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass Vorhaben im Anwendungsbereich der Richtlinie 2011/92/EU einer Umweltverträglichkeitsprüfung oder einem Screening unterzogen wurden und die Prüfung von Alternativen angemessen berücksichtigt wurde?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         ""),
        ("21", "KA2 BK2.4 · Art. 73(2)f CPR · Art. 22(4)f Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass bei Vorhaben, die vor Einreichung des Förderantrags begonnen wurden, das anwendbare Recht eingehalten wurde?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         ""),
        ("22", "KA2 BK2.4 · Art. 73(2)g CPR · Art. 22(4)g Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass die ausgewählten Vorhaben in den Anwendungsbereich des betreffenden Fonds fallen und einer Interventionsart zugeordnet sind?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         ""),
        ("23", "KA2 BK2.4 · Art. 73(2)h CPR · Art. 22(4)h Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass die Vorhaben keine Tätigkeiten umfassen, die Teil eines verlagerten Vorhabens nach Art. 66 waren oder eine Verlagerung einer Produktionstätigkeit nach Art. 65(1)a darstellen?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         ""),
        ("24", "KA2 BK2.4 · Art. 73(2)i CPR · Art. 22(4)i Interreg-VO",
         "Stellt die VB/der Begleitausschuss sicher, dass die ausgewählten Vorhaben nicht unmittelbar von einer mit Gründen versehenen Stellungnahme der Kommission zu einem Vertragsverletzungsverfahren nach Art. 258 AEUV betroffen sind?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         ""),
        ("25", "KA2 BK2.4 · Art. 73(2)j CPR · Art. 22(4)j Interreg-VO",
         "Stellt die VB/der Begleitausschuss die Sicherung der Klimaverträglichkeit von Infrastrukturinvestitionen mit einer erwarteten Lebensdauer von mindestens 5 Jahren sicher?",
         ["Bewertungsbögen", "Projektanträge", "Ausdrucke aus dem IT-System"],
         "Bei Interreg ist eine Bewertung der erwarteten Auswirkungen des Klimawandels durchzuführen."),
        ("26", "KA2 BK2.4 · Art. 64, 66 und 73(2) CPR · Art. 22(4) Interreg-VO",
         "Ist/sind das/die ausgewählte(n) Vorhaben förderfähig?",
         ["Bewertungsbögen", "Projektanträge"],
         "Sicherstellen, dass das Vorhaben: dem Programm entspricht (förderfähiger Begünstigter, vorgesehene und nach CPR förderfähige Tätigkeiten); keinen Ausschlussklauseln unterliegt; die Methodik und Kriterien von den Bewertern eingehalten wurden."),
        ("27", "KA2 BK2.5 · Art. 29(3)-(4), 33(3), 69(7) und 73(3) CPR · Art. 22, 28 und 36 Interreg-VO",
         "Werden Annahme-/Ablehnungsentscheidungen von ordnungsgemäß befugten Personen getroffen, die Ergebnisse schriftlich mitgeteilt und begründet, und wird die Liste der ausgewählten Vorhaben gemäß CPR veröffentlicht?",
         ["Bewertungsergebnisse", "Mitteilungen an Antragsteller", "auf der Website der VB veröffentlichte Dokumente"],
         "Sicherstellen, dass die Bewerter über die erforderliche Fachkenntnis und Unabhängigkeit verfügen. Bei externen Sachverständigen sollte die VB die Qualität der Arbeit prüfen."),
        ("28", "KA2 BK2.5 · Art. 69(7) CPR",
         "Ist ein ordnungsgemäßes Beschwerde-/Einspruchsverfahren eingerichtet und werden alle potenziellen Begünstigten informiert?",
         ["Aufforderungen zur Einreichung von Vorschlägen", "Website der VB"],
         "Die Begünstigten und potenziellen Begünstigten werden über ihr Beschwerderecht informiert (Art. 69(7) CPR)."),
        ("29", "KA2 BK2.5 · Art. 69(7) CPR",
         "Wurden eingelegte Beschwerden ordnungsgemäß von den Programmbehörden bearbeitet?",
         ["Eingereichte Beschwerden", "Arbeitsunterlagen der VB", "Kommunikation mit dem Antragsteller"],
         ""),
        ("30", "KA2 BK2.5 · Art. 73(3) CPR · Art. 22(6) Interreg-VO",
         "Gibt es für die ausgewählten Projekte ein offizielles Dokument zwischen Programmbehörden und Begünstigten, das die Bedingungen für die Unterstützung enthält?",
         ["Fördervereinbarungen / Zuwendungsbescheide"],
         "Rechte und Pflichten der Begünstigten werden wirksam kommuniziert — insbesondere: anwendbare Förderfähigkeitsregeln, Beihilferegeln, spezifische Förder- und Zahlungsbedingungen je Vorhaben, zu liefernde Produkte/Leistungen, Finanzierungsplan, ggf. Kostenermittlungsmethode, Durchführungsfrist sowie Anforderungen an ein getrenntes Rechnungslegungssystem/geeignete Buchungscodes."),
        ("31", "KA2 BK2.5 · Art. 73(1) CPR · Art. 22 Interreg-VO",
         "Wurden DNSH-bezogene Verpflichtungen, sofern das Programm solche enthält, in die Fördervereinbarung aufgenommen?",
         ["Fördervereinbarungen / Zuwendungsbescheide"],
         "Programme sollten nur Tätigkeiten fördern, die keine erhebliche Beeinträchtigung der Umweltziele im Sinne von Art. 17 der VO (EU) 2020/852 verursachen."),
        ("32", "Art. 73(5) CPR",
         "Wurde die EK bei Vorhaben von strategischer Bedeutung über deren Auswahl informiert?",
         ["Kopie der Mitteilung"],
         "Wählt die VB ein Vorhaben von strategischer Bedeutung aus, informiert sie die Kommission innerhalb von 1 Monat und stellt alle relevanten Informationen bereit."),
        ("33", "KA2 BK2.5 · Art. 118 und 118a CPR",
         "Erfüllt das Vorhaben bei in Phasen durchgeführten Vorhaben die Auswahlbedingungen?",
         ["Bewertungsbögen", "Projektanträge"],
         "In Phasen durchgeführte Vorhaben müssen die in Art. 118 und 118a CPR genannten besonderen Anforderungen erfüllen, um förderfähig zu sein."),
    ]),
    ("Teil C — Querschnittsaspekte: Arbeitsabläufe, angemessener Prüfpfad, Doppelfinanzierung und Vermeidung von Interessenkonflikten", [
        ("34", "KA2 BK2.1-2.5 · Art. 69(11), 70, 71 und 72(1) CPR",
         "Verfügt die VB im Rahmen der Beschreibung des Verwaltungs- und Kontrollsystems über eine klare Arbeitsmethodik/Verfahren für alle vorgenannten Prozesse?",
         ["Beschreibung des VKS", "Verfahrenshandbuch/-bücher"],
         "Die Programmbehörden haben klare Verfahren, um die Anforderungen an den Auswahlprozess zu erfüllen."),
        ("35", "KA2 BK2.6 · Art. 69(6), Anhang XIII CPR",
         "Liegt eine angemessene Dokumentation zum gesamten Auswahlverfahren und zur Genehmigung der Vorhaben vor (Prüfpfad)?",
         ["Im IT-System verfügbare Dokumente"],
         "Die Dokumentation ermöglicht die Überprüfung der Anwendung der Auswahlkriterien/-methodik während des gesamten Prozesses."),
        ("36", "KA7 BK7.4 · Art. 61 Haushaltsordnung · Art. 38 CPR · Art. 28 Interreg-VO",
         "Stellt die VB sicher, dass die Bewerter über die erforderliche Fachkenntnis und Unabhängigkeit verfügen (einschließlich Erklärung zum Nichtvorliegen von Interessenkonflikten)? Prüft die VB stichprobenartig das Nichtvorliegen von Interessenkonflikten?",
         ["Regeln zu Interessenkonflikten, Präventionsstrategie", "Erklärungen zum Nichtvorliegen von Interessenkonflikten", "Regeln des Bewertungsausschusses"],
         "Das mit der Bewertung befasste Personal muss frei von Interessenkonflikten sein; eine stichprobenartige Prüfung ist vorzusehen."),
        ("37", "KA2 BK2.4",
         "Stellt der Bewertungsprozess sicher, dass die ausgewählten Vorhaben keine Förderung aus anderen Quellen erhalten haben (Vermeidung von Doppelfinanzierung)?",
         ["Arbeitsverfahren", "verfügbare Arbeitsunterlagen", "bestehende Datenbanken/Werkzeuge"],
         "Angesichts der vielfältigen Finanzierungsquellen ist zu prüfen, ob die VB ein Verfahren zur Vermeidung von Doppelfinanzierung benötigt und anwendet."),
        ("38", "—",
         "Haben die Prüfer übermäßige Verwaltungsverfahren (Gold-Plating) festgestellt?",
         ["Arbeitsverfahren", "verfügbare Arbeitsunterlagen"],
         "Besonders auf das Auftreten übermäßiger Verwaltungsanforderungen achten, die über die regulatorischen Vorgaben hinausgehen."),
    ]),
]

CONCLUSION = (
    "Schlussfolgerung: Entspricht das Auswahlverfahren / die Auswahl des Vorhabens "
    "den regulatorischen Anforderungen? Die Prüfer schließen, ob das Auswahlverfahren "
    "regelkonform organisiert ist und ob die ausgewählten Vorhaben rechtmäßig und "
    "ordnungsgemäß ausgewählt wurden."
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
            | (ChecklistTemplate.title == "KOM — Auswahl der Vorhaben (KR2)")
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
                "Musterprüfcheckliste der Europäischen Kommission zur Auswahl der "
                "Vorhaben (Kernanforderung 2, KA2), Förderperiode 2021-2027 — ins Deutsche "
                "übertragen und in die Designer-Struktur überführt. Englisches "
                "Original siehe Quelldokument."
            ),
            source_language="en",
            target_language="de",
            source_document_name=SOURCE_DOC,
            source_document_path=SOURCE_PATH,
            status="published",
            properties_json={
                "audit_code": "",
                "cci_programme": "",
                "selected_projects": "",
                "prepared_by": "", "prepared_date": "",
                "reviewed_by": "", "reviewed_date": "",
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.1 (KA2)",
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

        # Teile + Fragen
        for part_title, questions in PARTS:
            h_part = add_node(node_type="HEADING", title=part_title)
            for key, legal, frage, belege, note in questions:
                q = add_node(
                    node_type="QUESTION", parent_id=h_part.id,
                    title=f"{key}. {frage}",
                    answer_type="CUSTOM_ENUM", eingabetyp=0,
                    answer_set_id=aset.id,
                    legal_reference=legal if legal != "—" else None,
                    relevant_documents_json=belege or None,
                )
                if note:
                    add_node(node_type="HINT", parent_id=q.id,
                             title=f"Hinweis: {note}")

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
