"""
flowworkshop · scripts/seed_kom_annex_1_2_mv.py

Seedet die KOM-Mustercheckliste "Annex 1.2 (RB)MV — Management verifications /
Verwaltungskontrolle (KA4)" als deutsche, in die audit_designer-Struktur
überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Teile/Sektionen (Überschriften) →
Fragen (mit Rechtsgrundlage KA/BK, Antwortset Ja/Nein/Teilweise/Entfällt, Belegen
und "Notes for auditor" als HINT-Kindknoten). Englisches Original bleibt als
source_document hinterlegt.

Idempotent: vorhandener Seed (gleiche source_document_name ODER title) wird zuvor
entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_2_mv.py
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

SOURCE_DOC = "Annex 1.2 (RB)MV (1).docx"
SOURCE_PATH = "checklist_sources/annex_1_2_mv.docx"
TITLE = "KOM — Verwaltungskontrolle (RB/MV)"

INSTRUCTION = (
    "Hinweis: Die Checkliste dient der Beurteilung, ob das Verwaltungs- und "
    "Kontrollsystem (VKS) die Anforderungen an die (risikobasierte) "
    "Verwaltungskontrolle erfüllt. Sie deckt die risikobasierte "
    "Risikobewertung, die Durchführung der Verwaltungskontrollen (VerwK), "
    "die nationalen Verfahren bei verstärkten verhältnismäßigen Regelungen "
    "(EPA) sowie die Verwaltungskontrolle von Vorhaben internationaler "
    "Organisationen ab. Die Fragen leiten sich aus der Verordnung ab und "
    "spiegeln die wesentlichen Prüfpunkte wider."
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
    ("Teil A — Risikobasierte Risikobewertung", [
        ("1", "Art. 74(2) CPR · KA4 BK4.1",
         "Wurde die Risikobewertung vorab (ex ante) und schriftlich durchgeführt?",
         ["Risikobewertung"],
         "Die Verwaltungsbehörde ist verpflichtet, die Risiken für die Verwaltungskontrollen schriftlich zu ermitteln, bevor sie mit den Verwaltungskontrollen beginnt."),
        ("2", "Art. 74(2) CPR · KA4 BK4.1",
         "Hat die Verwaltungsbehörde, falls die Verwaltungskontrollen 100 % der Ausgaben abdecken, eine angemessene Begründung vorgelegt?",
         ["Risikobewertung"],
         "Verwaltungskontrollen zu 100 % bleiben theoretisch bei hohen Risiken möglich; solche Fälle müssen jedoch in der Risikobewertung umfassend begründet werden."),
        ("3", "Art. 74(2) CPR · KA4 BK4.2",
         "Deckt die Risikobewertung sowohl administrative als auch Vor-Ort-Kontrollen ab?",
         ["Risikobewertung"],
         "Sowohl administrative als auch Vor-Ort-Kontrollen müssen von der Risikobewertung abgedeckt sein."),
        ("4", "Reflexionspapier zur risikobasierten Verwaltungskontrolle (RBMV)",
         "War die Prüfbehörde in die Ex-ante-Prüfung der Risikobewertung eingebunden? Falls ja, wurden die von der Prüfbehörde vorgebrachten Anmerkungen berücksichtigt?",
         ["Schriftverkehr", "Protokolle", "Bericht der Prüfbehörde"],
         "Die Ex-ante-Prüfung durch die Prüfbehörde ist nach der Verordnung nicht vorgeschrieben; die KOM fördert jedoch die Zusammenarbeit zwischen Verwaltungsbehörde und Prüfbehörde (da Verwaltungsbehörden in der Regel keine Erfahrung mit Risikobewertungen haben). Hat die Verwaltungsbehörde die Anmerkungen der Prüfbehörde nicht berücksichtigt, sollte eine Begründung vorliegen. Die Information ist mit den Ergebnissen (der Verwaltungskontrollen und der Prüfungen von Vorhaben) abzugleichen. Eine niedrige Gesamtfehlerquote (TER) ist ein starkes Indiz dafür, dass die Risikobewertung korrekt durchgeführt wurde."),
        ("5", "Art. 74(2) CPR · KA4 BK4.1",
         "Wird die Risikobewertung von der Verwaltungsbehörde durchgeführt (oder bei Interreg-Programmen zumindest geprüft)?",
         ["Risikobewertung"],
         "Die Aufgabe, die Risikobewertung zu entwickeln, obliegt der Verwaltungsbehörde (nicht dem Mitgliedstaat oder anderen Stellen). Zwar können beispielsweise zwischengeschaltete Stellen (oder bei Interreg der Mitgliedstaat bzw. die Kontrolleure) zur Entwicklung beitragen — was empfehlenswert sein kann, wenn diese in der vorherigen Förderperiode Verwaltungskontrollen durchgeführt haben —, doch sollte die Verwaltungsbehörde die Verantwortung für die Risikobewertung übernehmen, da sie den besten Überblick über die auf Ebene der Grundgesamtheit ermittelten Risiken hat."),
        ("6", "Art. 74(2) CPR · KA4 BK4.1",
         "Hat die Verwaltungsbehörde die Risikobewertung auf der Grundlage objektiver und zuverlässiger Daten und/oder Informationen durchgeführt?",
         ["Prüfpfad auf Ebene der Verwaltungsbehörde (verwendete Daten)"],
         "Die Verwaltungsbehörde kann entweder die Grundgesamtheit der vorherigen Förderperiode oder den zum Zeitpunkt der Auswahl der Vorhaben gewonnenen Überblick verwenden. Bei einer Aktualisierung der Risikobewertung kann die Verwaltungsbehörde die Ergebnisse ihrer eigenen Verwaltungskontrollen sowie die Ergebnisse der von der Prüfbehörde (und ggf. auch von KOM und EuRH) durchgeführten Prüfarbeiten heranziehen."),
        ("7", "Art. 74(2) CPR · KA4 BK4.1",
         "Wurden die wesentlichen, relevanten Risikofaktoren ermittelt?",
         ["Risikobewertung"],
         "Auch wenn die Verwaltungsbehörde Urheberin der Risikobewertung ist und sich die Bestätigung der Zuverlässigkeit letztlich erst mit Vorliegen der Ergebnisse der Prüfungen von Vorhaben erweist, kann und sollte der Prüfer kontrollieren, ob zumindest die wesentlichen, relevanten Risiken ermittelt wurden. Die wesentlichen zu prüfenden Punkte sind in Frage 2 der zweiten Tabelle aufgeführt."),
        ("8", "Art. 74(2) CPR · KA4 BK4.1",
         "Ermöglicht die Risikobewertung eine Ausweitung der Verwaltungskontrollen?",
         ["Risikobewertung"],
         "Da die Risikobewertung vorab durchgeführt wird, kann sie nicht alle tatsächlichen Folgen abbilden. Die Risikobewertung sollte anpassungsfähig sein (z. B. sieht die Verwaltungsbehörde vor, nur 10 von 100 Positionen zu prüfen, stellt dabei aber in allen Fällen Fehler fest — dann sollte sie die Prüfung ausweiten können; die Risikobewertung sollte solche Anpassungen also zulassen)."),
        ("9", "Art. 74(2) CPR · KA4 BK4.1",
         "Sind regelmäßige Aktualisierungen der Risikobewertung vorgesehen?",
         ["Risikobewertung"],
         "Zwar besteht keine rechtliche Verpflichtung, die Risikobewertung in bestimmten festen Abständen zu aktualisieren, doch sollte die Verwaltungsbehörde regelmäßige Aktualisierungen vorsehen (z. B. sollte zumindest nach Vorliegen der Ergebnisse der Prüfungen von Vorhaben eine Überlegung stattfinden)."),
        ("10", "Art. 74(2) CPR · KA4 BK4.1",
         "Wurde die Risikobewertung bei Bedarf tatsächlich aktualisiert? (falls zutreffend)",
         ["Risikobewertung"],
         "In bestimmten Fällen (z. B. hohe Gesamtfehlerquote TER, bei Verwaltungskontrollen entdeckte systembedingte Fehler, deutlich höhere Fehlerhäufigkeit als ursprünglich geschätzt) sollte die Verwaltungsbehörde eine Aktualisierung der Risikobewertung in Erwägung ziehen."),
        ("11", "Art. 74(2) CPR",
         "Hält der Prüfer eine Aktualisierung der Risikobewertung für erforderlich?",
         ["Ergebnisse aussagebezogener Prüfungen (Substantive Tests)"],
         "Stellt der Prüfer beispielsweise in seiner Stichprobe einen wiederkehrenden Fehler für eine bestimmte Kategorie von Kosten/Begünstigten/Vorhaben fest, kann dies zu dem Schluss führen, dass die Risikobewertung überarbeitet werden sollte (z. B. derselbe Fehler liegt in 7 von 8 Stichprobeneinheiten vor). Handelt es sich jedoch um einen einmaligen Fehler, sollte dies nicht automatisch zu dem Schluss führen, dass die Risikobewertung fehlerhaft ist."),
        ("12", "—",
         "Wesentliche Feststellungen angeben:",
         [],
         ""),
    ]),
    ("Teil B — Durchführung der Verwaltungskontrollen", [
        ("1", "KA1",
         "Verfügt das Programm über Maßnahmen zur Schulung des Personals im Hinblick auf die risikobasierte Verwaltungskontrolle? Ist das erforderliche Personal verfügbar?",
         [],
         "Zu beachten ist, dass eine Funktionstrennung für Kontrolleure sowie für Auswahl und/oder Begleitung nicht erforderlich ist. Die rechtliche Anforderung für 2021-2027 (wie mit dem Juristischen Dienst geklärt) besteht darin, dass Kontrolleure nicht die Rechnungslegungsfunktion ausüben."),
        ("2", "Art. 74(1)(a) CPR · KA1 BK1.2",
         "Verfügt das Programm über Verfahren, die die Verwaltungskontrollen abdecken?",
         ["Verfahren für die Verwaltungskontrolle"],
         "Die Verfahren sollten sowohl administrative als auch Vor-Ort-Kontrollen abdecken. Zu beachten ist, dass die administrativen Kontrollen tatsächlich im Rahmen des Vor-Ort-Besuchs durchgeführt werden können."),
        ("3", "Art. 74(1)(a) CPR",
         "Sind die vorhandenen Verfahren angemessen?",
         ["Verfahren für die Verwaltungskontrolle"],
         "Für die Verwaltungskontrollen werden schriftliche Verfahren und Checklisten verwendet und die Schlussfolgerungen dokumentiert. Solche Checklisten umfassen mindestens die Kontrollen nach Art. 74 CPR: 1) die kofinanzierten Produkte und Dienstleistungen wurden geliefert (Realität des Vorhabens, einschließlich der tatsächlichen Erbringung von Produkt oder Dienstleistung); 2) das Vorhaben entspricht dem geltenden Recht, dem Programm und den Bedingungen für die Unterstützung des Vorhabens, insbesondere hinsichtlich: a. Richtigkeit und Vollständigkeit des Zahlungsantrags der Begünstigten; b. Förderfähigkeitszeitraum; c. Einhaltung des genehmigten Finanzierungssatzes (falls zutreffend); d. Einhaltung der einschlägigen Förderfähigkeitsregeln sowie der EU- und nationalen Vorschriften zu Vergabe, Beihilfen, Publizität, Chancengleichheit und Nichtdiskriminierung, Transparenz und Zugänglichkeit für Menschen mit Behinderungen, Gleichstellung der Geschlechter, Charta der Grundrechte der EU sowie Grundsatz der nachhaltigen Entwicklung und der Umweltpolitik der Union nach Art. 11 und Art. 191(1) AEUV; e. Einhaltung der Bedingungen des Dokuments zur Festlegung der Bedingungen für die Unterstützung; f. der geltend gemachten Ausgaben und Vorhandensein des Prüfpfads; g. Fehlen von Doppelfinanzierung; 3) für von der Verwaltungsbehörde nach Art. 53(1)(a) CPR zu erstattende Kosten: h. die von den Begünstigten geltend gemachten Kosten wurden getätigt und bezahlt; i. ein getrenntes Rechnungslegungssystem oder ein geeigneter Buchungscode für alle ein Vorhaben betreffenden Transaktionen ist eingerichtet. Diese Kontrollen können entweder während der administrativen Kontrollen oder während der Vor-Ort-Kontrollen erfolgen. Die Verfahren sollten auf Einzelfallebene zuverlässig sein und die Ermittlung der relevanten Sachverhalte ermöglichen."),
        ("4", "Art. 74(1)(a) CPR",
         "Sind die vorhandenen Verfahren danach angepasst, ob es sich um Realkosten oder um vereinfachte Kostenoptionen (SCO/FNLC) handelt?",
         ["Verfahren für die Verwaltungskontrolle"],
         "Für von der Verwaltungsbehörde nach Art. 53(1)(b), (c) und (d) CPR erstattete Kosten: j. die Voraussetzungen für die Erstattung von Kosten über vereinfachte Kostenoptionen (Kosten je Einheit, Pauschalbeträge oder Pauschalfinanzierung) wurden erfüllt; für nach Art. 53(1)(f) CPR erstattete Kosten: k. die Erstattungsvoraussetzungen wurden erfüllt; und l. die Ergebnisse wurden erreicht; für von der Kommission nach Art. 94(3) CPR erstattete Ausgaben: m. die Erstattungsvoraussetzungen wurden erfüllt; für von der Kommission nach Art. 95(3) CPR erstattete Ausgaben: n. die Erstattungsvoraussetzungen wurden erfüllt; oder o. die Ergebnisse wurden erreicht."),
        ("5", "Art. 9(4), Art. 74(1)(a) CPR",
         "Verfügt die Verwaltungsbehörde über geeignete Verfahren zur Kontrolle der Erfüllung DNSH-bezogener Bedingungen (sofern solche Bedingungen in den Zuwendungsbescheid aufgenommen wurden)?",
         ["Verfahren für die Verwaltungskontrolle"],
         "Die Verfahren sollten sicherstellen, dass etwaige Anforderungen an das Projekt oder im Auswahlstadium eingegangene Verpflichtungen in Bezug auf DNSH (Vermeidung erheblicher Beeinträchtigungen) anschließend erfüllt wurden (Beispiele: Hat sich das Projekt zu einer umweltorientierten Vergabe verpflichtet, war die Vergabe tatsächlich 'grün'; das Projekt verpflichtete sich zu keinen erheblichen Treibhausgasemissionen, aus den vorliegenden Unterlagen geht jedoch das Gegenteil hervor; das Projekt verpflichtete sich zur Wiederherstellung der Biodiversität und der Ökosysteme, es werden jedoch keine Maßnahmen ergriffen)."),
        ("6", "Art. 69(1), Art. 74(1)(a) CPR",
         "Sehen die Verfahren Fristen für die Durchführung der Verwaltungskontrolle vor?",
         ["Verfahren für die Verwaltungskontrolle", "Zeitplan für Vor-Ort-Kontrollen"],
         "Die Verfahren sollten klare Fristen für die Durchführung sowohl der administrativen als auch der Vor-Ort-Kontrolle enthalten (für Vor-Ort-Kontrollen kann auch ein Zeitplan vorgesehen werden)."),
        ("7", "Art. 69(1), Art. 74(1)(a) CPR",
         "Überwacht das Programm die Einhaltung der jeweiligen Fristen?",
         ["Verfahren für die Verwaltungskontrolle"],
         "Das Programmverfahren sollte die Überwachung der vorgenannten Fristen vorsehen (um eine wirtschaftliche Haushaltsführung des Programms sicherzustellen). Ständige Verzögerungen bei den Verwaltungskontrollen können die Projektumsetzung und folglich die Erreichung der Programmziele beeinträchtigen."),
        ("8", "Art. 69(1), Art. 74(1)(a) CPR",
         "Wurden die vorgenannten Fristen eingehalten?",
         ["Verfahren für die Verwaltungskontrolle", "Zeitplan für Vor-Ort-Kontrollen und zugehörige Prüfaufträge/vergleichbarer Prüfpfad"],
         "Die Einhaltung der Fristen (bzw. des Zeitplans, sofern bei Vor-Ort-Kontrollen anwendbar) für die administrative Kontrolle ist für die wirtschaftliche Haushaltsführung des Programms erforderlich."),
        ("9", "Art. 69(6) CPR · KA4 BK4.5 und BK5.1",
         "Ist der Prüfpfad für die Verwaltungskontrollen verfügbar?",
         ["Verfahren und Systeme"],
         "Die Mitgliedstaaten haben Systeme und Verfahren einzurichten, die sicherstellen, dass alle für den Prüfpfad nach Anhang XIII erforderlichen Unterlagen gemäß den Anforderungen des Art. 82 aufbewahrt werden. Für die Projekte Ihrer Stichprobe sollte der Prüfpfad vollständig verfügbar sein (unabhängig davon, ob sie Gegenstand risikobasierter Verwaltungskontrollen waren oder nicht). Wird die Anforderung nicht eingehalten, werden die betreffenden Ausgaben nicht förderfähig und die Bewertung von KA4 und KA5 ist entsprechend anzupassen."),
        ("10", "Art. 74(1)(a) CPR",
         "Sind die Checklisten für die Verwaltungskontrollen angemessen ausgefüllt?",
         ["Checklisten der Verwaltungsbehörde/zwischengeschalteten Stelle/Kontrolleure (bei einigen Interreg-Programmen)"],
         "Die Checklisten sollten alle erforderlichen Informationen enthalten."),
        ("11", "Art. 74(1)(a), Art. 76(1), (2) VO (EU) 2021/1060 und Art. 46(3) VO (EU) 2021/1059",
         "Liegt eine Doppelung der Verwaltungskontrollen vor?",
         ["Verfahren und Checklisten der Verwaltungsbehörde (oder Kontrolleure), der zwischengeschalteten Stelle sowie der Betrugsbekämpfung"],
         "Verwaltungskontrollen sind Aufgabe der Verwaltungsbehörde (bei einigen Interreg-Programmen der Kontrolleure). Die Aufgabe kann an eine zwischengeschaltete Stelle delegiert werden. In diesem Fall sollte die Verwaltungsbehörde die delegierten Aufgaben beaufsichtigen und überwachen, dies sollte jedoch nicht zu einer Doppelung der Verwaltungskontrolle führen. Zudem hat die Rechnungslegungsfunktion/-stelle nicht mehr die Aufgabe, Kontrollen durchzuführen (oder sicherzustellen, dass die Verwaltungsbehörde die erforderlichen Kontrollen durchgeführt hat). Daher sollten auf Ebene der Rechnungslegungsfunktion/-stelle keine Kontrollen stattfinden. Andernfalls liegt ein Fall von Gold-Plating vor und die in der Verordnung angestrebte Vereinfachung wird nicht erreicht."),
        ("12", "Art. 74(1)(a) CPR",
         "Hat die Verwaltungsbehörde für die in Ihrer Stichprobe ausgewählten Projekte die vorhandenen Verfahren korrekt angewandt?",
         ["Aussagebezogene Checkliste aus den Konformitätsprüfungen verwenden"],
         "Für die Projekte der Stichprobe sollte der Prüfer die aussagebezogene Checkliste aus der Konformitätsprüfung verwenden."),
        ("13", "Art. 74(1)(a) CPR",
         "Wurden die erforderlichen Korrekturmaßnahmen auf der Grundlage der Ergebnisse der Verwaltungskontrollen ergriffen?",
         ["Verschiedene Unterlagen auf Ebene der Verwaltungsbehörde/zwischengeschalteten Stelle"],
         "Der Prüfer hat den Prüfpfad anzufordern und zu prüfen, der belegt, dass die Korrekturmaßnahmen ergriffen wurden (z. B. dass die finanzielle Korrektur vorgenommen wurde, die Maßnahmen zur Instandsetzung einer Straße ergriffen wurden usw.)."),
        ("14", "—",
         "Wesentliche Feststellungen angeben:",
         [],
         ""),
    ]),
    ("Teil C — Nationale Verfahren (verstärkte verhältnismäßige Regelungen — EPA)", [
        ("1", "Art. 83 CPR",
         "Hat der Mitgliedstaat die Kommission notifiziert?",
         ["Notifizierung in SFC 2021"],
         "Der Mitgliedstaat muss im vorangegangenen Geschäftsjahr (N-1) notifizieren, um die EPA im darauffolgenden Geschäftsjahr (N) anwenden zu können."),
        ("2", "Art. 83 CPR",
         "Gibt es Nachweise dafür, dass die nationalen Verfahren nicht eingehalten werden bzw. unzureichend sind?",
         ["Ergebnisse von Prüfungen von Vorhaben", "Betrugsfälle", "Beschwerden, die zur Aufdeckung von Unregelmäßigkeiten führen"],
         "Werden solche Nachweise ausgelöst, sollten gesonderte Kontrollen der Strukturen durchgeführt werden, die die nationalen Kontrollen durchführen."),
        ("3", "Art. 83 CPR",
         "Falls sich die Verwaltungsbehörde auf von externen Stellen durchgeführte Kontrollen stützt: Gibt es einen Prüfpfad, der belegt, dass sie Nachweise über die Kompetenz dieser Stellen eingeholt hat?",
         ["Verfahren zur Beurteilung der Kompetenz"],
         "Die Nachweise sollten vor der Notifizierung eingeholt werden."),
        ("4", "Art. 83 CPR",
         "Sind die Nachweise über die Kompetenz dieser Stellen ausreichend?",
         ["Verfahren zur Beurteilung der Kompetenz"],
         "Die Verwaltungsbehörde sollte überprüft haben, dass die Stellen hinreichend kompetent sind."),
        ("5", "—",
         "Wesentliche Feststellungen angeben:",
         [],
         ""),
    ]),
    ("Teil D — Verwaltungskontrolle von Vorhaben internationaler Organisationen (IO)", [
        ("1", "Art. 22(1) AMIF / 18(1) BMVI / 17(1) ISF",
         "Gibt es Nachweise dafür, dass die internationale Organisation für die Zwecke der indirekten Mittelverwaltung von der KOM positiv 'säulenbewertet' (pillar-assessed) wurde?",
         ["Säulenbewertungsbericht, von der KOM auf Anfrage des Mitgliedstaats übermittelt", "Zentrales Register der säulenbewerteten Stellen (Link)"],
         "Besondere Bestimmungen zu den Verwaltungskontrollen nähern das VKS der geteilten Mittelverwaltung an dasjenige an, das die KOM in der indirekten Mittelverwaltung anwendet, indem sie sich auf Vorschriften, Systeme und Verfahren internationaler Organisationen oder ihrer Agenturen stützen — insbesondere auf Prüfung und interne Kontrolle —, wenn diese für die Zwecke der indirekten Mittelverwaltung von der KOM positiv bewertet ('säulenbewertet') wurden. Ist die internationale Organisation Begünstigte, liegt aber kein Säulenbewertungsbericht vor, führt die Verwaltungsbehörde Verwaltungskontrollen gemäß den Anforderungen der Dachverordnung durch; die Prüfer verwenden den obigen Teil 'Verwaltungskontrolle'."),
        ("2", "Art. 22(6) AMIF / 18(6) BMVI / 17(6) ISF · Art. 155(1)(a) Haushaltsordnung",
         "Hat die internationale Organisation mit jedem Zahlungsantrag einen Bericht über die Verwendung der Unionsmittel vorgelegt?",
         ["Bericht über die Umsetzung"],
         "Ist eine internationale Organisation (IO) Begünstigte der Förderung, ist die Verwaltungsbehörde nicht verpflichtet, die Verwaltungskontrollen durchzuführen, sofern die IO der Verwaltungsbehörde mit jedem Zahlungsantrag den Bericht über die Verwendung der Unionsmittel und die Verwaltungserklärung vorlegt."),
        ("3", "Art. 22(6) AMIF / 18(6) BMVI / 17(6) ISF · Art. 155(1)(a) Haushaltsordnung",
         "Hat die internationale Organisation mit jedem Zahlungsantrag eine Verwaltungserklärung vorgelegt?",
         ["Verwaltungserklärung (Vorlage in Anhang I der Informationsnote kann verwendet werden)"],
         "Wie vorstehend."),
        ("4a", "Art. 22(6) AMIF / 18(6) BMVI / 17(6) ISF · Art. 155(1)(c) Haushaltsordnung",
         "Bestätigte die von der internationalen Organisation vorgelegte Verwaltungserklärung, dass die Informationen ordnungsgemäß dargestellt, vollständig und richtig sind?",
         ["Informationsnote zu den neuen Bestimmungen für die Fonds für innere Angelegenheiten betreffend Verwaltungskontrollen und Prüfungen von durch IO umgesetzten Projekten"],
         ""),
        ("4b", "Art. 22(3) AMIF / 18(3) BMVI / 17(3) ISF",
         "... dass die Unionsmittel für ihren vorgesehenen Zweck verwendet wurden, wie in den Beitragsvereinbarungen, Finanzierungsvereinbarungen oder Garantievereinbarungen bzw. ggf. in den einschlägigen sektorspezifischen Vorschriften festgelegt?",
         [],
         ""),
        ("4c", "Art. 22(4) AMIF / 18(4) BMVI / 17(4) ISF",
         "... dass, sofern der Zahlungsantrag die Erstattung tatsächlich getätigter und bezahlter förderfähiger Kosten betrifft, die Rechnungen und der Nachweis ihrer Bezahlung durch den Begünstigten geprüft wurden?",
         [],
         ""),
        ("4d", "Art. 22(4) AMIF / 18(4) BMVI / 17(4) ISF",
         "... dass, sofern der Zahlungsantrag die Erstattung tatsächlich getätigter und bezahlter förderfähiger Kosten betrifft, die vom Begünstigten geführten Rechnungslegungsunterlagen oder Buchungscodes für die mit den der Verwaltungsbehörde gemeldeten Ausgaben verbundenen Transaktionen geprüft wurden?",
         [],
         ""),
        ("4e", "Art. 22(5) AMIF / 18(5) BMVI / 17(5) ISF",
         "... dass, sofern der Zahlungsantrag Kosten je Einheit, Pauschalbeträge oder Pauschalfinanzierung betrifft, die Voraussetzungen für die Erstattung der Ausgaben erfüllt wurden?",
         [],
         ""),
        ("4f", "Art. 22(4) AMIF / 18(4) BMVI / 17(4) ISF",
         "... dass die eingerichteten Kontrollsysteme die erforderlichen Gewähr hinsichtlich der Recht- und Ordnungsmäßigkeit der zugrunde liegenden Transaktionen bieten?",
         [],
         ""),
        ("5", "Art. 22(7) AMIF / 18(7) BMVI / 17(7) ISF",
         "Hat die internationale Organisation der Verwaltungsbehörde die Rechnungslegung zu allen kofinanzierten Projekten bis zum 15. Oktober vorgelegt?",
         ["Prüfpfad auf Ebene der Verwaltungsbehörde (Bericht über die Umsetzung, Verwaltungserklärung, von der IO der Verwaltungsbehörde vorgelegte Jahresrechnung, Bestätigungsvermerke)"],
         "Die internationale Organisation legt der Verwaltungsbehörde jedes Jahr bis zum 15. Oktober die Rechnungslegung zu allen vom Programm des betreffenden Mitgliedstaats kofinanzierten Projekten vor."),
        ("6", "Art. 22(7) AMIF / 18(7) BMVI / 17(7) ISF",
         "Hat die internationale Organisation die Rechnungslegung zusammen mit dem/den Bestätigungsvermerk(en) vorgelegt?",
         [],
         "Der Rechnungslegung ist ein Bestätigungsvermerk eines externen Prüfers (Option 1) oder des Prüfers der internationalen Organisation (Option 2) beizufügen. Der Bestätigungsvermerk muss: feststellen, ob die eingerichteten Kontrollsysteme ordnungsgemäß funktionieren und wirtschaftlich sind, und ob die zugrunde liegenden Transaktionen recht- und ordnungsmäßig sind; angeben, ob die Prüfarbeiten die in den von der IO vorgelegten Verwaltungserklärungen gemachten Angaben in Zweifel ziehen, einschließlich Informationen über Betrugsverdachtsfälle; Gewähr dafür bieten, dass die in den von der IO der Verwaltungsbehörde vorgelegten Zahlungsanträgen enthaltenen Ausgaben recht- und ordnungsmäßig sind."),
        ("7", "Art. 22(7) AMIF / 18(7) BMVI / 17(7) ISF",
         "Erfüllten die vom externen Prüfer bereitgestellten Bestätigungsvermerke / der vom Prüfer der internationalen Organisation bereitgestellte Bestätigungsvermerk den Gewährbedarf der Verwaltungsbehörde?",
         [],
         "Unabhängig davon, welche Option für die Bereitstellung des Bestätigungsvermerks gewählt wird, decken die im Bestätigungsvermerk enthaltenen Elemente möglicherweise nicht den Gewährbedarf der Verwaltungsbehörde; in diesem Fall kann die Verwaltungsbehörde eine Kontrolle durchführen. Die gewählte Option ist in das Verwaltungs- und Kontrollsystem des Mitgliedstaats und in die zwischen Verwaltungsbehörde und IO geschlossenen Vereinbarungen aufzunehmen."),
        ("8", "Art. 22(7) AMIF / 18(7) BMVI / 17(7) ISF",
         "Wurden die von der internationalen Organisation zur Stützung des Bestätigungsvermerks vorgelegten Prüfnachweise von der Verwaltungsbehörde als ausreichend erachtet?",
         [],
         "Dem vom Prüfer der Organisation bereitgestellten Bestätigungsvermerk muss ein Vermerk beigefügt sein, der hinreichend detailliert beschreibt: die durchgeführten Prüfarbeiten; die Anzahl der von den Prüfarbeiten erfassten Transaktionen; eine Erläuterung, wie die verschiedenen Prüfelemente hinreichende Gewähr hinsichtlich der Recht- und Ordnungsmäßigkeit der zugrunde liegenden Transaktionen bieten; alle aus den Prüfungen abgeleiteten Elemente, die in prüfungstechnischer Hinsicht hervorzuheben sind; alle Vorbehalte des Kontrolleurs der Organisation hinsichtlich der durch die Jahresrechnung gebotenen Gewähr."),
        ("9", "Art. 22(7) AMIF / 18(7) BMVI / 17(7) ISF",
         "Wurden die hinsichtlich der in einem bestimmten Jahr betroffenen Beträge durchgeführten Prüfarbeiten von der Verwaltungsbehörde als ausreichend erachtet?",
         [],
         "Wie vorstehend."),
        ("10", "Art. 22(10) AMIF / 18(10) BMVI / 17(10) ISF",
         "Hat die Verwaltungsbehörde ein Risiko der Unregelmäßigkeit oder ein Anzeichen für Betrug in Bezug auf ein von der internationalen Organisation initiiertes oder umgesetztes Projekt festgestellt?",
         ["Risikobewertung, Informationen aus verschiedenen relevanten Quellen (Arachne, EuRH-Prüfungen, OLAF-Untersuchungen usw.)"],
         "Die Verwaltungsbehörde ist verpflichtet, eigene Verwaltungskontrollen durchzuführen, wenn: sie ein spezifisches Risiko der Unregelmäßigkeit oder ein Anzeichen für Betrug in Bezug auf ein von der IO initiiertes oder umgesetztes Projekt feststellt; die internationale Organisation eines der in den Abschnitten 3.1 und 3.2 dieser Note genannten Dokumente nicht vorlegt; die von der IO vorgelegten Dokumente unvollständig sind."),
        ("11", "Art. 22(10) AMIF / 18(10) BMVI / 17(10) ISF",
         "Waren die von der internationalen Organisation vorgelegten Dokumente vollständig?",
         ["Prüfpfad auf Ebene der Verwaltungsbehörde (Bericht über die Umsetzung, Verwaltungserklärung)"],
         "Wie vorstehend."),
        ("12", "Art. 22(10) AMIF / 18(10) BMVI / 17(10) ISF · Titel VI Kapitel 2 CPR",
         "Wurden von der Verwaltungsbehörde zusätzliche Kontrollen durchgeführt?",
         ["Verfahren zur Verwaltungskontrolle bei der Umsetzung von Projekten durch IO", "Partnerschaftsvereinbarung ähnlich FAFA, sofern von Verwaltungsbehörde und IO unterzeichnet"],
         "Die Bestimmungen der Rechtsgrundlagen beschränken die Verantwortlichkeiten der Verwaltungsbehörde nicht. Im Falle der Kontrolle gemeldeter Ausgaben können IO und Verwaltungsbehörde Verfahren vereinbaren, die denjenigen ähneln, die die KOM in ihren Finanzrahmen-Partnerschaftsvereinbarungen (FFPA) mit IO verwendet."),
        ("13", "—",
         "Falls ja: War dies mit den Antworten auf die vorstehenden Fragen vereinbar?",
         [],
         ""),
        ("14", "—",
         "Falls nein: War dies auf der Grundlage der vorstehenden Fragen gerechtfertigt?",
         [],
         ""),
        ("15", "—",
         "Wesentliche Feststellungen angeben:",
         [],
         ""),
    ]),
]

# Zusätzlicher Erläuterungstext zu Teil D (aus dem Kopfblock des IO-Abschnitts)
PART_D_NOTE = (
    "Hinweis: Ist eine internationale Organisation (IO) Begünstigte der "
    "Förderung, ist die Verwaltungsbehörde nicht verpflichtet, die "
    "Verwaltungskontrollen durchzuführen, sofern die IO der "
    "Verwaltungsbehörde mit jedem Zahlungsantrag den Bericht über die "
    "Verwendung der Unionsmittel und die Verwaltungserklärung vorlegt. Die IO "
    "legt der Verwaltungsbehörde jedes Jahr bis zum 15. Oktober die "
    "Rechnungslegung zu allen vom Programm des betreffenden Mitgliedstaats "
    "kofinanzierten Projekten vor. Der Rechnungslegung ist ein "
    "Bestätigungsvermerk einer unabhängigen Prüfstelle nach international "
    "anerkannten Prüfungsstandards beizufügen. Decken die im "
    "Bestätigungsvermerk enthaltenen Elemente den Gewährbedarf der "
    "Verwaltungsbehörde nicht, kann diese eine Kontrolle durchführen."
)

CONCLUSION = (
    "Schlussfolgerung: Entspricht die (risikobasierte) Verwaltungskontrolle den "
    "regulatorischen Anforderungen? Die Prüfer schließen, ob die Risikobewertung "
    "und die durchgeführten Verwaltungskontrollen regelkonform organisiert sind "
    "und ob die zugrunde liegenden Ausgaben rechtmäßig und ordnungsgemäß "
    "kontrolliert wurden."
)


def _uid():
    return str(uuid.uuid4())


def run():
    db = SessionLocal()
    try:
        # Idempotenz: vorhandenen Seed entfernen (source_document_name ODER title)
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
                "Musterprüfcheckliste der Europäischen Kommission zur "
                "(risikobasierten) Verwaltungskontrolle (Kernanforderung 4, KA4), "
                "Förderperiode 2021-2027 — ins Deutsche übertragen und in die "
                "Designer-Struktur überführt. Englisches Original siehe "
                "Quelldokument."
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
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.2 (RB)MV (KA4)",
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

        # Hinweise für Prüfer
        h_intro = add_node(node_type="HEADING", title="Hinweise für Prüfer")
        add_node(node_type="HINT", parent_id=h_intro.id, title=INSTRUCTION)

        # Teile + Fragen
        for part_title, questions in PARTS:
            h_part = add_node(node_type="HEADING", title=part_title)
            # Zusatzhinweis zu Teil D direkt unter die Überschrift hängen
            if part_title.startswith("Teil D"):
                add_node(node_type="HINT", parent_id=h_part.id, title=PART_D_NOTE)
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
