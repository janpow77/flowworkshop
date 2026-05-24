"""
flowworkshop · scripts/seed_kom_sco.py

Seedet die KOM-Mustercheckliste "Checklist SCO 2021-2027" (Vereinfachte
Kostenoptionen, VKO/SCO) als deutsche, in die audit_designer-Struktur
überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Abschnitt 1/2 mit Teilen
(Überschriften) → Fragen (mit Rechtsgrundlage KA/BK, Antwortset
Ja/Nein/Teilweise/Entfällt, Belegen und "Notes for auditor" als HINT-
Kindknoten). Englisches Original bleibt als source_document hinterlegt.

Abschnitt 1 prüft die VKO-Methodik (faire/gerechte/nachprüfbare Methode,
Entwurfsbudget, Unions-/mitgliedstaatliche Methoden, delegierter Rechtsakt,
Stundensätze nach Art. 55 CPR). Abschnitt 2 prüft die Anwendung der Methodik
auf Pauschalsätze, Kosten je Einheit und Pauschalbeträge.

Idempotent: vorhandener Seed (gleiche source_document_name oder Titel) wird
zuvor entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_sco.py
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

SOURCE_DOC = "Checklist SCO 2021-2027(1).docx"
SOURCE_PATH = "checklist_sources/sco.docx"
TITLE = "KOM — Vereinfachte Kostenoptionen (VKO)"

INSTRUCTION = (
    "Hinweis: Die Prüfung der auf Grundlage vereinfachter Kostenoptionen "
    "(VKO/SCO) geltend gemachten Ausgaben umfasst sowohl die VKO-Methodik als "
    "auch deren Anwendung (Abschnitt 1 und Abschnitt 2 dieser Checkliste). "
    "Wurde die Methodik von der Kommission nach Art. 94 CPR genehmigt, "
    "beschränkt sich die Prüfung auf die Anwendung der VKO-Methodik "
    "(Abschnitt 2). Abschnitt 1 dient der Beurteilung der VKO-Methodik — bei "
    "der Ex-ante-Bewertung oder bei Prüfungen während der Durchführung von "
    "VKO, die die Verwaltungsbehörde zur Erstattung an Begünstigte nutzt "
    "('lower level' VKO nach Art. 53 CPR), sowie bei der Ex-ante-Bewertung "
    "einer VKO-Methodik, die zur Erstattung der Kommission an die "
    "Verwaltungsbehörde eingereicht wird ('upper level' VKO nach Art. 94 CPR). "
    "Die Fragen 1-11 sind für alle VKO-Methodiken auszufüllen; die "
    "anschließenden Teile (12-17) sind je nach der zur Festlegung der "
    "VKO-Methodik verwendeten Methode auszufüllen. Bei Interreg-Programmen "
    "liegt die Verantwortung gemäß Interreg-Verordnung (VO (EU) 2021/1059) "
    "bei den Verwaltungsbehörden bzw. Begleitausschüssen."
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
    ("Verwaltungsbehörde / zwischengeschaltete Stelle", "TEXT"),
    ("Begünstigte und Empfänger (falls zutreffend)", "TEXT"),
    ("Geprüfter Gesamtbetrag (einschließlich Unions- und nationaler Förderung)", "TEXT"),
    ("Checkliste erstellt — Name", "TEXT"),
    ("Checkliste erstellt — Datum", "DATE"),
    ("Checkliste geprüft — Name", "TEXT"),
    ("Checkliste geprüft — Datum", "DATE"),
]

# Teile mit Fragen: (key, legal_reference, frage_de, belege_de[list], note_de)
PARTS = [
    ("Abschnitt 1 — Bewertung der VKO-Methodik (Fragen 1-11 für alle Methodiken)", [
        ("1", "KA13 BK13.1 und BK13.3 · Art. 77 CPR · Art. 48 Interreg-VO",
         "Hat die Prüfbehörde die VKO-Methodik geprüft und validiert?",
         ["Prüfbericht", "Checklisten der Prüfbehörde"],
         "Werden auf Grundlage von VKO geltend gemachte Ausgaben geprüft, muss die Prüfbehörde die VKO-Methodik und deren Anwendung prüfen. Hat die Prüfbehörde die VKO-Methodik (ex ante oder während der Durchführung) nicht geprüft, obwohl die auf VKO gestützten Ausgaben geprüft wurden, ist eine Empfehlung an die Prüfbehörde zu formulieren, diesen Aspekt künftig abzudecken."),
        ("2", "KA13 BK13.1 und BK13.3 · Art. 77 CPR · Art. 48 Interreg-VO",
         "Falls ja: Hatte die Prüfbehörde für die VKO-Methodik relevante Feststellungen? War der Prüfungsumfang angemessen?",
         ["Prüfbericht", "Checklisten der Prüfbehörde"],
         "Sind die Feststellungen der Prüfbehörde zur Methodik oder der Prüfungsumfang nicht sachgerecht, ist eine Empfehlung an die Prüfbehörde zu formulieren, ihren Prüfansatz für künftige Prüfungen anzupassen."),
        ("3", "KA13 BK13.5 · Art. 74 CPR",
         "Falls die Antwort auf Frage 2 'Ja' lautet: Hat die Verwaltungsbehörde die Empfehlungen umgesetzt?",
         [],
         "Sind die Feststellungen der Prüfbehörde relevant und hat die Verwaltungsbehörde sie nicht umgesetzt, ist eine Empfehlung an die Verwaltungsbehörde zu formulieren, die von der Prüfbehörde ausgesprochenen Empfehlungen nachzuverfolgen."),
        ("4", "KA4 BK4.3 / KA9 BK9.1 / KA13 BK13.3 · Art. 63 CPR · VKO-Leitfaden",
         "Sind die von der VKO abgedeckten Kostenkategorien klar definiert und förderfähig, auch bei vorgefertigten ('off the shelf') VKO?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')", "Bei vorgefertigten VKO: nationale Regeln, operationelles Programm, Aufforderungen zur Einreichung von Vorschlägen"],
         "Da die VKO eine Erstattungsform ist, müssen die von der VKO abgedeckten und damit erstatteten Kostenkategorien in der VKO-Methodik bzw. — bei vorgefertigten Pauschalsätzen — in den nationalen Regeln, im Programm oder in den veröffentlichten Aufforderungen zur Einreichung von Vorschlägen klar definiert sein. Die vorgefertigten Pauschalsätze sind in der Dachverordnung bzw. der fondsspezifischen Verordnung definiert und am Ende dieser Checkliste aufgeführt. Die VKO darf nur förderfähige Kostenkategorien abdecken. Deckt die VKO eine nicht förderfähige Kostenkategorie ab, ist die Methodik zu ändern; der Prüfer prüft die in der Berechnungsmethodik berücksichtigten Kosten."),
        ("5", "KA4 BK4.3 / KA9 BK9.1 / KA13 BK13.3 · Art. 63 CPR · Beihilfevorschriften · VKO-Leitfaden",
         "Falls die Verwaltungsbehörde plant, die VKO in Vorhaben einzusetzen, die dem Beihilferecht unterliegen: Sind die von der VKO abgedeckten Kostenkategorien auch nach den auf die Vorhaben anwendbaren Beihilfevorschriften förderfähig?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "In einigen Fällen kann die Verwaltungsbehörde angeben, dass die VKO in Vorhaben verwendet wird, die dem Beihilferecht unterliegen (z. B. Kosten je Einheit für Personalkosten in Entwicklungs- und Innovationsprojekten von Unternehmen nach AGVO-Regelungen). Der Prüfer prüft dann, ob die in der VKO-Methodik genannten Kostenkategorien nach den spezifischen Beihilfevorschriften förderfähig sind. Beihilfevorschriften gelten nur für VKO zur Erstattung an Begünstigte ('lower level'). Sind die Kostenkategorien nach Beihilferecht nicht förderfähig, so darf die VKO entweder nicht in beihilferechtlich relevanten Vorhaben verwendet werden oder die Methodik ist beihilferechtskonform anzupassen."),
        ("6", "KA4 BK4.3 / KA9 BK9.1 / KA13 BK13.3 · Art. 53 / Art. 94 CPR · VKO-Leitfaden",
         "Ist der die Erstattung auslösende Indikator und seine Maßeinheit klar beschrieben und für die festgelegte VKO relevant?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Die VKO-Methodik muss den die Erstattung auslösenden Indikator angeben: bei Kosten je Einheit die Einheit, für die ein Wert festgelegt wurde, bei Pauschalbeträgen die Ergebnisse und bei Pauschalsätzen die Basiskosten. Indikator und Maßeinheit müssen für die Art der VKO sachgerecht sein (z. B. bei Kosten je Einheit für erfolgreiche Schulungsteilnehmer die Zahl der erfolgreich abgeschlossenen Teilnehmer). Bei vorgefertigten Pauschalsätzen löst die Geltendmachung der Basiskosten die Zahlung aus; eine weitere Definition ist nicht erforderlich."),
        ("7", "KA4 BK4.3 / KA9 BK9.1 / KA13 BK13.3 · Art. 63 CPR",
         "Sind die von der VKO abgedeckten Kostenkategorien klar angegeben und nicht in den als Realkosten geltend zu machenden Kosten doppelt enthalten?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Die von der VKO abgedeckten Kostenkategorien dürfen nicht über andere Erstattungsformen geltend gemacht werden, um eine Doppelerfassung derselben Kostenkategorien zu vermeiden. Sind die von der VKO abgedeckten Kostenkategorien nicht klar von den als Realkosten geltend zu machenden Kategorien abgegrenzt, fordert der Prüfer die Verwaltungsbehörde auf, die Methodik so anzupassen, dass die Kategorien getrennt und das Risiko der Doppelfinanzierung gemindert wird."),
        ("8", "KA4 BK4.3 / KA9 BK9.1 / KA13 BK13.3 · Art. 53 / Art. 94 CPR",
         "Ist in der VKO-Methodik eine Anpassungsmethode vorgesehen? Falls ja: Ist die Anpassungsmethode beschrieben und angemessen?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Bei VKO in über lange Zeiträume durchgeführten Vorhaben wird der Verwaltungsbehörde empfohlen, eine Anpassungsmethode in die Methodik aufzunehmen; verpflichtend ist dies nicht. Ist eine Anpassungsmethode vorgesehen, muss sie hinreichende Angaben zu Bedingungen und Zeitpunkt ihrer Anwendung sowie den Verweis auf den verwendeten Indikator (ggf. mit Link zur Veröffentlichung) enthalten. Der Prüfer prüft, ob die Bedingungen klar und messbar sind und die Methode angemessen ist."),
        ("9", "KA4 BK4.3 / KA9 BK9.1 · Art. 53 / Art. 94 CPR",
         "Sind in der VKO-Methodik Überprüfungen zur Erreichung der gelieferten Einheiten/erzielten Ergebnisse vorgesehen, die für die Maßeinheit relevant und für die festgelegte VKO sachgerecht sind?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Die Verwaltungsbehörde sollte beschreiben, welche Dokumentation/welches System zur Überprüfung der Erreichung der gelieferten Einheiten/erzielten Ergebnisse verwendet wird. Beispiel: Für Kosten je Einheit für energetische Sanierungsarbeiten an einem Haus sieht die Methodik vor, dass die Einheit erreicht ist, wenn ein Mindestgewinn von 100 kWh/m²/Jahr Primärenergie vorliegt; die vorgesehenen Überprüfungen müssen je Einheit den Nachweis dieser Mindestbedingung umfassen."),
        ("10", "KA5 BK5.1 / KA6 BK6.1 · Art. 53 / Art. 94 CPR",
         "Sind die Vorkehrungen zur Erhebung und Speicherung von Daten zum die Erstattung auslösenden Indikator beschrieben und angemessen?",
         ["Dokument zur Festlegung der VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Diese Prüfung dient der Feststellung, dass die Verwaltungsbehörde die Erhebung und Speicherung VKO-spezifischer Daten (Erreichung der Ergebnisse / Lieferung der Kosten je Einheit) und das zu verwendende System vorsieht. Der Prüfer beurteilt, ob das vorgeschlagene System angemessen ist und eine ordnungsgemäße Erhebung und jederzeitige Verfügbarkeit der Daten bei Prüfungen ermöglicht. Ist die Erhebung und Speicherung der spezifischen Daten unmöglich, kann die Methodik nicht genehmigt werden; der Prüfer empfiehlt der Verwaltungsbehörde, geeignete Vorkehrungen zu treffen."),
        ("11", "KA4 BK4.3 / KA9 BK9.1 · Art. 53 / Art. 94 CPR",
         "Wird die VKO-Methodik aus früheren Förderperioden verwendet? Falls ja: Wurde die Methodik nach dem geltenden Rechtsrahmen festgelegt und bewertet?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR"],
         "VKO aus früheren Förderperioden zählen nicht zu den von der Dachverordnung vorgesehenen Methoden und dürfen in der Förderperiode 2021-2027 nicht ohne weitere Überprüfung verwendet werden. Verwendet die Verwaltungsbehörde eine in früheren Perioden festgelegte Methodik, muss sie diese an den geltenden Rechtsrahmen anpassen; sie ist wie jede neue Methodik durch die Prüfer zu bewerten. Die Fragen des jeweils einschlägigen Teils unten sind je nach ursprünglich verwendeter Methode auszufüllen."),
    ]),
    ("Abschnitt 1 · Teil 12 — Faire, gerechte und nachprüfbare Methode (Art. 53(3)a / 94(2)a CPR)", [
        ("12.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR · VKO-Leitfaden",
         "Sind die für die Berechnung verwendeten Daten zuverlässig, genau und vollständig?",
         ["Datenbank"],
         "Der Umfang der Beurteilung der Zuverlässigkeit/Korrektheit der verwendeten Daten hängt von der Datenquelle ab. Hält der Prüfer die Quelle für zuverlässig (z. B. Daten der nationalen Statistikämter), konzentriert sich die Prüfung darauf, dass die tatsächlich in die Berechnung eingegebenen Daten den Quelldaten entsprechen. Bei manchen Quellen sind detailliertere Prüfungen erforderlich (z. B. stichprobenartige Prüfung der Belege). Sind die Daten nicht zuverlässig und genau, besteht das Risiko, dass die VKO keine Annäherung an die Realkosten widerspiegelt; in diesem Fall empfiehlt der Prüfer der Verwaltungsbehörde, die Berechnungsmethodik zu überarbeiten."),
        ("12.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 53 / Art. 63 / Art. 94 CPR · VKO-Leitfaden",
         "Ist die Berechnungsmethodik dokumentiert, nachvollziehbar und korrekt?",
         ["Arbeitsunterlagen"],
         "Die Verwaltungsbehörde muss in der Methodik die Berechnungsmethodik und alle Datenbearbeitungen erläutern. Die Prüfer müssen die Berechnungsmethodik jederzeit während einer Prüfung nachvollziehen können; daher müssen die Daten, ihre Quellen sowie alle angewandten mathematischen Berechnungen zum Zeitpunkt der Methodik-Beurteilung verfügbar sein. Berechnungsfehler sind zu korrigieren."),
        ("12.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR · VKO-Leitfaden",
         "Sind die in den für die Berechnung der VKO verwendeten Daten enthaltenen Kosten förderfähig?",
         ["Für die Berechnung verwendete Datenbank"],
         "Die zur Festlegung der VKO berücksichtigten Kosten müssen mit den einschlägigen nationalen und EU-Förderfähigkeitsregeln im Einklang stehen. Nach nationalem und EU-Recht nicht förderfähige Kosten dürfen den Berechnungsdaten nicht hinzugefügt werden. Wurden nicht förderfähige Kosten hinzugefügt, berechnet der Prüfer die VKO unter Ausschluss dieser Kosten neu und ermittelt den korrekten Wert der VKO (Kosten je Einheit, Pauschalbetrag oder Pauschalsatz)."),
        ("12.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR · VKO-Leitfaden",
         "Sind die in den für die Berechnung verwendeten Daten enthaltenen Kosten für die von der VKO abgedeckten Kostenkategorien angemessen?",
         ["Datenbank und VKO-Methodik"],
         "Die Berechnungsmethodik sollte nur die von der VKO abgedeckten Kosten berücksichtigen. Beispiel: Für die Bestimmung von Kosten je Einheit für Energieeffizienzarbeiten dürfen nicht alle Renovierungskosten früherer Vorhaben berücksichtigt werden, sondern nur die für die Steigerung der Energieeffizienz erforderlichen Arbeiten."),
        ("12.5", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR · VKO-Leitfaden",
         "Wurden Ausreißer aus den für die Berechnung verwendeten Daten ausgeschlossen? Falls ja: Ist der Ausschluss erläutert und angemessen?",
         ["Datenbank", "Arbeitsunterlagen"],
         "Die Verordnung enthält keine Definition von Ausreißern. Der Prüfer wendet sein berufliches Urteilsvermögen an und holt Informationen zu den Gründen ein, aus denen die Verwaltungsbehörde Daten aus der Berechnung ausgeschlossen hat oder nicht."),
        ("12.6", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(a)(i) / 94(2)(a)(i) CPR · VKO-Leitfaden",
         "Im Falle eines Sachverständigengutachtens: Ist der Sachverständige für das jeweilige Fachgebiet qualifiziert? Falls ja: Sind die vom Sachverständigen getroffenen Annahmen für die VKO-Methodik relevant?",
         ["Arbeitsunterlagen", "Belege"],
         "Sachverständigengutachten sollten auf einem spezifischen Kriterienkatalog und/oder in einem bestimmten Wissens-, Anwendungs- oder Produktbereich, einer Disziplin oder Branche erworbener Fachkenntnis beruhen, dokumentiert und auf den Einzelfall bezogen sein. Die Dachverordnung definiert das Sachverständigengutachten nicht; die Verwaltungsbehörde legt die Anforderungen fest und stellt sicher, dass kein Interessenkonflikt besteht. Für jeden Sachverständigen sind dessen Fachkenntnis und Unabhängigkeit nachzuweisen. Die Annahmen des Sachverständigen sind zu dokumentieren, damit die Prüfer sie bei der Beurteilung der VKO-Methodik nachvollziehen können."),
        ("12.7", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)a / 94(2)a CPR",
         "Kann auf Grundlage der vorstehenden Antworten geschlossen werden, dass die Methodik im Sinne der Dachverordnung fair, gerecht und nachprüfbar war?",
         ["Dokument zur Festlegung der Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Nach Art. 53(3)a ('lower level') und 94(2)a ('upper level') CPR kann eine faire, gerechte und nachprüfbare Berechnungsmethodik beruhen auf: statistischen Daten, anderen objektiven Informationen oder einem Sachverständigengutachten; überprüften historischen Daten (bei 'lower level' VKO sind dies Daten einzelner Begünstigter); Anwendung der üblichen Kostenrechnungspraxis (bei 'lower level' VKO Daten einzelner Begünstigter). Der Prüfer schließt, ob die VKO mit einer dieser Methoden berechnet wurde. Wurde keine dieser Methoden verwendet, ist die VKO nicht auf einer fairen, gerechten und nachprüfbaren Methode festgelegt; der Prüfer ermittelt die verwendete Methodik oder fordert weitere Informationen von der Verwaltungsbehörde an."),
    ]),
    ("Abschnitt 1 · Teil 13 — Entwurfsbudget (Art. 53(3)b CPR)", [
        ("13.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(b) / 73(3) CPR · Art. 22 Interreg-VO",
         "Wurde das Entwurfsbudget ex ante von der das Vorhaben auswählenden Stelle analysiert und genehmigt? Falls ja: Ist die Beurteilung des Entwurfsbudgets korrekt?",
         ["Dokument zur Genehmigung des Entwurfsbudgets"],
         "Das Entwurfsbudget wird von Förderantragstellern mit Belegen zur Rechtfertigung aller Budgetkosten eingereicht. Die Verwaltungsbehörde muss beurteilen, dass das Entwurfsbudget angemessen ist (Marktpreise, Marktstudien, Preise anderer Projekte) und eine VKO festlegen. Der Prüfer prüft die Beurteilung der Verwaltungsbehörde. Wurde das Entwurfsbudget vor Ausstellung des Dokuments mit den Bedingungen für die Unterstützung nicht beurteilt und genehmigt, ist die Methode nicht eingehalten und die VKO-Methodik nicht mit Art. 53(3)b vereinbar; der Prüfer kann die Verwaltungsbehörde zur Ex-post-Beurteilung auffordern und die VKO bei Angemessenheit akzeptieren, verbunden mit einer Empfehlung, künftig Art. 53(3)b einzuhalten."),
        ("13.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Enthält das Entwurfsbudget nur nach EU- und nationalen Regeln förderfähige Kosten?",
         ["Entwurfsbudget"],
         "Der Prüfer überprüft die Belege zu den im Entwurfsbudget festgelegten Beträgen und prüft, ob die zur VKO-Berechnung beitragenden Kosten förderfähig sind. Sind Kosten nicht förderfähig, berechnet der Prüfer die VKO unter Ausschluss dieser Kosten aus dem Entwurfsbudget neu."),
        ("13.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(b) CPR",
         "Bei einer 'lower level' VKO: Wurde die Entwurfsbudget-Methode nur für Vorhaben verwendet, deren Gesamtkosten unter 200 000 EUR liegen?",
         ["Förderantrag"],
         "Nach Art. 53(3)b darf die Entwurfsbudget-Methode nur für Vorhaben verwendet werden, deren Gesamtkosten unter 200 000 EUR liegen. Maßgeblich sind die bei der Auswahl geplanten Gesamtkosten; die tatsächlich entstandenen Kosten der Durchführung sind nicht relevant."),
        ("13.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 25 Interreg-VO",
         "Wurde bei Kleinprojekten, die über Kleinprojektfonds in Interreg-Programmen finanziert werden, das Entwurfsbudget ex ante vom den Kleinprojektfonds verwaltenden Begünstigten genehmigt?",
         ["Dokument zur Genehmigung des Entwurfsbudgets"],
         "Bei Kleinprojekten nach Art. 25 Interreg-VO wählt der den Kleinprojektfonds verwaltende Begünstigte die Kleinprojekte aus und muss das Entwurfsbudget ex ante auf Angemessenheit beurteilen (Marktpreise, Marktstudien, Preise anderer Projekte). Der Prüfer überprüft die Beurteilung des Begünstigten."),
        ("13.5", "KA4 BK4.3 / KA9 BK9.1 · Art. 25 Interreg-VO",
         "Bei Kleinprojekten über Kleinprojektfonds in Interreg-Programmen: Wurde die Entwurfsbudget-Methode nur für Projekte verwendet, deren öffentlicher Beitrag unter 100 000 EUR liegt?",
         ["Förderantrag"],
         "Nach Art. 25(6) Interreg-VO darf die Entwurfsbudget-Methode nur für Kleinprojekte verwendet werden, deren öffentlicher Beitrag unter 100 000 EUR liegt. Die tatsächlich entstandenen Kosten der Durchführung des Kleinprojekts sind nicht relevant."),
        ("13.6", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(b) / 73(3) CPR · Art. 22 Interreg-VO",
         "Ist die auf dem Entwurfsbudget beruhende VKO korrekt berechnet?",
         ["Entwurfsbudget", "VKO-Methodik"],
         "Der Prüfer prüft, ob das Entwurfsbudget korrekt in eine VKO überführt wurde. Falls nicht, wird die Verwaltungsbehörde zur Neuberechnung der korrekten VKO aufgefordert und der Prüfer beurteilt die Auswirkungen."),
    ]),
    ("Abschnitt 1 · Teil 14 — VKO aus Unionspolitiken für ähnliche Vorhaben (Art. 53(3)c / 94(2)c CPR)", [
        ("14.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(c) / 94(2)(c) CPR",
         "Wurde die VKO auf Grundlage der für entsprechende Kosten je Einheit, Pauschalbeträge und Pauschalsätze geltenden Regeln aus Unionspolitiken für ähnliche Vorhaben festgelegt?",
         ["VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Die VKO-Methodik muss die Regeln aus Unionspolitiken darlegen, auf deren Grundlage die VKO festgelegt wurde. Die Verwaltungsbehörde muss nachweisen, dass die VKO für ähnliche Vorhaben verwendet wird; die Dachverordnung definiert ähnliche Vorhaben nicht — es obliegt der Verwaltungsbehörde, die Ähnlichkeit zu erläutern. Der Prüfer beurteilt die vorgelegte Begründung. Aus delegierten Rechtsakten der Förderperiode 2014-2020 übernommene VKO sind unter diesem Punkt zu behandeln."),
        ("14.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(c) / 94(2)(c) CPR",
         "Waren die Regeln der entsprechenden Unionspolitik zum Zeitpunkt der Aufforderung zur Einreichung von Vorschlägen ('lower level') bzw. zum Zeitpunkt der Einreichung der Programmänderung bei der Kommission ('upper level') noch anwendbar?",
         ["Anwendbare Unionspolitik"],
         "War die Unionspolitik, auf deren Grundlage die VKO festgelegt wurde, zum Zeitpunkt der Aufforderung zur Einreichung von Vorschlägen ('lower level') bzw. der Einreichung der Programmänderung ('upper level') nicht in Kraft, darf die VKO dieser Politik nicht zur Festlegung einer VKO nach der Dachverordnung verwendet werden."),
        ("14.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(c) / 94(2)(c) CPR",
         "Wurde die Methodik der VKO vollständig — einschließlich aller Bedingungen — übernommen?",
         ["Anwendbare Unionspolitik", "VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Alle auf Ebene einer anderen Unionspolitik festgelegten Bedingungen sind in die VKO-Methodik zu übernehmen, um die korrekte Verwendung der VKO sicherzustellen. Besteht die VKO in Unionspolitiken aus mehreren klar getrennten Kosten je Einheit/Pauschalbeträgen/Pauschalsätzen, kann die Verwaltungsbehörde nur eines davon zur Festlegung einer VKO nach der Dachverordnung übernehmen (Beispiel: Marie-Skłodowska-Curie-Maßnahmen unter Horizont 2020 mit getrenntem Satz für Kosten je Einheit für Lebenshaltungs- und Mobilitätszulagen)."),
    ]),
    ("Abschnitt 1 · Teil 15 — VKO aus mitgliedstaatlichen Politiken für ähnliche Vorhaben (Art. 53(3)d / 94(2)d CPR)", [
        ("15.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(d) / 94(2)(d) CPR",
         "Wurde die VKO auf Grundlage der für entsprechende Kosten je Einheit, Pauschalbeträge und Pauschalsätze geltenden Regeln aus mitgliedstaatlichen Politiken für ähnliche Vorhaben festgelegt?",
         ["VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Die VKO-Methodik muss die Regeln aus mitgliedstaatlichen Politiken darlegen, auf deren Grundlage die VKO festgelegt wurde. Die Verwaltungsbehörde muss nachweisen, dass die VKO für ähnliche Vorhaben verwendet wird. Der Betrag der VKO aus mitgliedstaatlichen Politiken muss nicht gerechtfertigt werden. In nationalen Gesetzen festgelegte Obergrenzen dürfen nicht als Grundlage zur Bestimmung einer VKO nach der Dachverordnung herangezogen werden."),
        ("15.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(d) / 94(2)(d) CPR",
         "Waren die Regeln der entsprechenden mitgliedstaatlichen VKO zum Zeitpunkt der Aufforderung zur Einreichung von Vorschlägen ('lower level') bzw. zum Zeitpunkt der Einreichung der Programmänderung bei der Kommission ('upper level') noch anwendbar?",
         ["Anwendbare mitgliedstaatliche Politik"],
         "War die mitgliedstaatliche Politik, auf deren Grundlage die VKO festgelegt wurde, zum maßgeblichen Zeitpunkt nicht in Kraft, darf die VKO dieser Politik nicht zur Festlegung einer VKO nach der Dachverordnung verwendet werden."),
        ("15.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(d) / 94(2)(d) CPR",
         "Wurde die Methodik vollständig — einschließlich aller Bedingungen — übernommen?",
         ["Anwendbare mitgliedstaatliche Politik", "VKO-Methodik ('lower level')", "Anlage 1 zu Anhang V CPR ('upper level')"],
         "Alle auf Ebene einer anderen Politik festgelegten Bedingungen sind in die VKO-Methodik zu übernehmen. Besteht die VKO in mitgliedstaatlichen Politiken aus mehreren klar abgegrenzten Kosten je Einheit/Pauschalbeträgen/Pauschalsätzen, kann die Verwaltungsbehörde nur eines davon zur Festlegung einer VKO nach der Dachverordnung übernehmen."),
        ("15.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 53(3)(d) / 94(2)(d) CPR",
         "Wird die VKO-Methodik der nationalen Politik im Rahmen von ausschließlich vom Mitgliedstaat finanzierten Förderregelungen angewandt?",
         ["Belege"],
         "Die VKO aus mitgliedstaatlichen Politiken kann nur dann in eine VKO nach der Dachverordnung überführt werden, wenn sie in ausschließlich vom Mitgliedstaat finanzierten Zuschüssen verwendet wird. Ist diese Bedingung nicht erfüllt, kann die VKO nicht auf Grundlage mitgliedstaatlicher Politiken festgelegt werden."),
    ]),
    ("Abschnitt 1 · Teil 16 — VKO aus delegiertem Rechtsakt (Delegierte VO (EU) 2023/1676 vom 7. Juli 2023)", [
        ("16.1", "KA4 BK4.3 / KA9 BK9.1 · Delegierter Rechtsakt",
         "Werden die Bestimmungen des delegierten Rechtsakts eingehalten?",
         [],
         "Jede im delegierten Rechtsakt genannte Bedingung ist einzuhalten. Bestimmt der delegierte Rechtsakt etwa, dass die festgelegte VKO nur verwendet werden darf, wenn sie für alle ähnlichen Vorhaben eines Programms verwendet wird, darf die Verwaltungsbehörde keine andere VKO zur Erstattung von Ausgaben in ähnlichen Vorhaben nutzen."),
        ("16.2", "KA4 BK4.3 / KA9 BK9.1 · Delegierter Rechtsakt",
         "Hat der Mitgliedstaat den entsprechenden Prüfpfad für die Förderfähigkeit der Zielgruppe und die Erfüllung der Bedingungen festgelegt?",
         [],
         "Der delegierte Rechtsakt gibt dem Mitgliedstaat die Möglichkeit, den Prüfpfad zum Nachweis der Förderfähigkeit der Zielgruppe festzulegen. Vor Verwendung der VKO sollte die Verwaltungsbehörde daher die entsprechenden Belege zur Prüfung der Förderfähigkeit der Zielgruppe und der Erfüllung der Bedingungen festlegen."),
    ]),
    ("Abschnitt 1 · Teil 17 — Stundensatz für Personalkosten (Art. 55 CPR)", [
        ("17.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 55(2)(a) CPR",
         "Wird der Stundensatz auf Grundlage der letzten jährlichen Bruttobeschäftigungskosten geteilt durch 1 720 festgelegt? Falls ja: Sind die jährlichen Bruttobeschäftigungskosten dokumentiert?",
         [],
         "Die Verordnung verweist auf die Berechnung des Stundensatzes anhand der 'letzten' dokumentierten jährlichen Bruttobeschäftigungskosten; die verwendeten Daten müssen die aktuellsten verfügbaren sein. Eine Berechnungsmethodik auf Basis historischer Daten des Begünstigten ist daher in der Regel nicht relevant. 1 720 Stunden entsprechen einem Vollzeitäquivalent und die Methode ist in allen Mitgliedstaaten anwendbar, unabhängig von der nach nationalem Recht zulässigen wöchentlichen Höchstarbeitszeit. Die Bruttobeschäftigungskosten müssen einen vollen Zeitraum von 12 Monaten abdecken, unabhängig vom Kalender- oder Geschäftsjahr."),
        ("17.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 55(2)(a) CPR",
         "Ist bei Teilzeitbeschäftigten der Nenner ein entsprechender anteiliger Wert von 1 720 Stunden?",
         [],
         "Nach Art. 55(2)a CPR können die 1 720 Stunden bei Teilzeitbeschäftigten durch Anwendung eines entsprechenden anteiligen Werts verwendet werden."),
        ("17.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 55(2)(a) CPR",
         "Sind die letzten jährlichen Bruttobeschäftigungskosten verfügbar? Falls nicht: Werden sie aus verfügbaren, auf einen 12-Monats-Zeitraum angepassten Unterlagen berechnet?",
         [],
         "Sind die jährlichen Bruttobeschäftigungskosten nicht verfügbar, können sie aus den verfügbaren dokumentierten Bruttobeschäftigungskosten abgeleitet werden (z. B. kann die Verwaltungsbehörde Daten eines Beschäftigten über 4 Monate auf die jährlichen Bruttobeschäftigungskosten hochrechnen, ggf. unter Berücksichtigung von gesetzlichem Urlaubsgeld oder sogenannten 13. Monatsgehältern)."),
        ("17.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 55(2)(b) CPR",
         "Wird der Stundensatz durch Division der letzten dokumentierten monatlichen Bruttobeschäftigungskosten durch die durchschnittliche monatliche Arbeitszeit festgelegt? Falls ja: Wird die durchschnittliche monatliche Arbeitszeit nach den im Arbeitsvertrag näher geregelten nationalen Vorschriften festgelegt?",
         [],
         "Die in Art. 55(2)(b) CPR eingeführte Option kann auch dann verwendet werden, wenn die Daten zu den jährlichen Bruttobeschäftigungskosten verfügbar sind."),
    ]),
    ("Abschnitt 2 · Teil 1 — Anwendung: Pauschalsätze (Art. 73(3) CPR / Art. 22(6) Interreg-VO)", [
        ("2.1.2", "KA2 BK2.1 / KA3 BK3.3 · Art. 73(3) CPR · Art. 22(6) Interreg-VO",
         "Ist die Verwendung des Pauschalsatzes in der Aufforderung zur Einreichung von Vorschlägen und im Dokument mit den Bedingungen für die Unterstützung vorgesehen?",
         ["Aufforderung zur Einreichung von Vorschlägen (oder gleichwertig)", "Dokument mit den Bedingungen für die Unterstützung"],
         "Die Grundsätze der Transparenz und Gleichbehandlung sind sicherzustellen; alle potenziellen Begünstigten müssen Zugang zu den Informationen über die verwendete Erstattungsform haben. Daher ist die Verwendung des Pauschalsatzes in der Aufforderung zur Einreichung von Vorschlägen (oder einem gleichwertigen Dokument, falls keine Aufforderung zur Einreichung von Vorschlägen veröffentlicht wurde) anzugeben und zusätzlich im Dokument mit den Bedingungen für die Unterstützung zu nennen. Wurden die Grundsätze nicht eingehalten, beurteilt der Prüfer die Auswirkungen und empfiehlt der Verwaltungsbehörde, sie bei künftigen Aufforderungen zur Einreichung von Vorschlägen/Vorhaben einzuhalten."),
        ("2.1.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Sind die als Berechnungsgrundlage verwendeten Kosten (sogenannte 'Basiskosten') förderfähig, rechtmäßig und ordnungsgemäß?",
         ["Belege für die Basiskosten"],
         "Der Prüfer prüft die Kosten, auf die der Pauschalsatz angewandt wird (Basiskosten), entsprechend ihrer Erstattungsform (werden sie z. B. über VKO erstattet, gilt der Prüfpfad für VKO)."),
        ("2.1.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Schließen die Basiskosten die vom Pauschalsatz abgedeckten Kostenkategorien aus?",
         ["Dokument zur Definition der vom Pauschalsatz abgedeckten Kostenkategorien", "Belege für die Basiskosten"],
         "Die 'Basis' der Berechnung oder andere Realkosten dürfen keinen vom Pauschalsatz abgedeckten Kostenposten enthalten, um Doppelfinanzierung zu vermeiden. Werden z. B. Verwaltungskosten von einem Pauschalsatz für indirekte Kosten abgedeckt, dürfen sie nicht zusätzlich auf Basis tatsächlich entstandener Kosten geltend gemacht werden. Werden vom Pauschalsatz abgedeckte Kostenkategorien als entstandene Kosten geltend gemacht, kann der Prüfer schließen, dass dieselben Kategorien doppelt geltend gemacht wurden, und die als Realkosten geltend gemachten Kosten als nicht förderfähig betrachten."),
        ("2.1.5", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Ist der geltend gemachte Betrag durch Anwendung des Pauschalsatzes auf die 'Basiskosten' korrekt berechnet?",
         ["Geltend gemachte Ausgaben"],
         "Der Prüfer prüft die Berechnung des auf die Basiskosten angewandten Pauschalsatzes."),
        ("2.1.6", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR · Art. 22 ESF+-VO",
         "Spiegeln sich Anpassungen der Basiskosten im Pauschalsatz wider?",
         ["Belege für die Basiskosten"],
         "Jede nach Überprüfungen akzeptierte Verringerung des förderfähigen Betrags der 'Basiskosten' (z. B. infolge einer finanziellen Berichtigung) wirkt sich anteilig auf den für die pauschal berechneten Kostenkategorien akzeptierten Betrag aus. Ist dies nicht der Fall, empfiehlt der Prüfer der Verwaltungsbehörde/Prüfbehörde, die erforderlichen Berichtigungen vorzunehmen. Bei Pauschalsätzen nach Art. 22 ESF+-VO führt eine Verringerung der Basiskosten nicht zu einer Verringerung der vom Pauschalsatz abgedeckten förderfähigen Kosten."),
        ("2.1.7", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR",
         "Hat die Verwaltungsbehörde bei der Auswahl beurteilt, dass die vom Pauschalsatz abgedeckten Kostenkategorien für die Durchführung des Vorhabens erforderlich sind und daher vom Begünstigten geltend gemacht werden können?",
         ["Arbeitsunterlagen"],
         "In der Auswahlphase muss die Verwaltungsbehörde anhand der Angaben im Förderantrag und im Dokument mit den Bedingungen für die Unterstützung prüfen, ob die vom Pauschalsatz abgedeckten Kostenkategorien erforderlich sind. Geschah dies nicht bei der Auswahl, kann die Verwaltungsbehörde die erforderlichen Erläuterungen ex post nachreichen. Sind die abgedeckten Kostenkategorien für die Durchführung nicht erforderlich, kann der Prüfer schließen, dass der Pauschalsatz für das Vorhaben nicht verwendet werden kann."),
        ("2.1.8", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR · anwendbare Beihilfevorschriften",
         "Sind Beihilfevorschriften anwendbar?",
         ["Arbeitsunterlagen (Beihilfeanalyse)", "erstattete Ausgaben"],
         "Falls ja, ist die beihilferechtsspezifische Checkliste auszufüllen. Der auf Grundlage von VKO erstattete Betrag ist der für die Berechnung der Beihilfeintensität/-höhe bzw. der Ausgleichsleistung bei DAWI zu berücksichtigende Betrag."),
        ("2.1.9", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) / 94(3) CPR",
         "Falls zutreffend: Werden die in der Methodik festgelegten Bedingungen eingehalten?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR"],
         "Die Methodik kann spezifische Bedingungen für die Verwendung der Pauschalsätze vorsehen. Zusätzliche Bedingungen in der VKO-Methodik sind unüblich, müssen aber, falls genannt, erfüllt sein, um die Erstattung auszulösen (z. B. bei einem Pauschalsatz für Personalkosten von Promovierenden die in der Methodik festgelegte Bedingung zum Bildungsniveau)."),
    ]),
    ("Abschnitt 2 · Teil 2 — Anwendung: Kosten je Einheit (standardisierte Kosten je Einheit)", [
        ("2.2.1", "KA2 BK2.1 / KA3 BK3.3 · Art. 73(3) CPR · Art. 22(6) Interreg-VO",
         "Ist die Verwendung der Kosten je Einheit in der Aufforderung zur Einreichung von Vorschlägen und im Dokument mit den Bedingungen für die Unterstützung vorgesehen?",
         ["Aufforderung zur Einreichung von Vorschlägen (oder gleichwertig)", "Dokument mit den Bedingungen für die Unterstützung"],
         "Die Grundsätze der Transparenz und Gleichbehandlung sind sicherzustellen; alle potenziellen Begünstigten müssen Zugang zu den Informationen über die verwendete Erstattungsform haben. Daher ist die Verwendung der Kosten je Einheit in der Aufforderung zur Einreichung von Vorschlägen (oder einem gleichwertigen Dokument) anzugeben und zusätzlich im Dokument mit den Bedingungen für die Unterstützung zu nennen. Wurden die Grundsätze nicht eingehalten, beurteilt der Prüfer die Auswirkungen und empfiehlt der Verwaltungsbehörde, sie künftig einzuhalten."),
        ("2.2.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR",
         "Wird die Anzahl der geltend gemachten Einheiten durch Belege in Übereinstimmung mit der Methodik gerechtfertigt?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR", "geltend gemachte Ausgaben"],
         "Die vom Vorhaben gelieferten Einheiten im Sinne quantifizierter Inputs, Outputs oder Ergebnisse, die von den Kosten je Einheit abgedeckt sind, müssen dokumentiert, nachprüfbar und real sein. Kosten je Einheit für nicht erreichte Outputs/Ergebnisse dürfen nicht geltend gemacht werden. Der Prüfer prüft die Belege zum Nachweis der geltend gemachten Einheiten und empfiehlt der Verwaltungsbehörde/Prüfbehörde, bei nicht erreichten oder nicht belegten Einheiten die erforderlichen finanziellen Berichtigungen vorzunehmen."),
        ("2.2.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 53 / Art. 94 CPR",
         "Wurden die Kosten je Einheit mit der in der Methodik vorgesehenen Anpassungsmethode angepasst?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR"],
         "Im Falle einer Anpassung prüft der Prüfer, ob die in der VKO-Methodik vorgesehene Anpassungsmethode eingehalten wurde, und empfiehlt bei Unregelmäßigkeiten finanzielle Berichtigungen. War keine Anpassungsmethode vorgesehen, dürfen die Kosten je Einheit nicht geändert werden."),
        ("2.2.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR",
         "Entspricht der geltend gemachte Betrag den Kosten je Einheit multipliziert mit den tatsächlich gelieferten Einheiten?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR", "geltend gemachte Ausgaben"],
         "Der Prüfer prüft die Berechnung der geltend gemachten Ausgaben und empfiehlt der Verwaltungsbehörde/Prüfbehörde bei Unregelmäßigkeiten die erforderlichen finanziellen Berichtigungen."),
        ("2.2.5", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR · anwendbare Beihilfevorschriften",
         "Sind Beihilfevorschriften anwendbar?",
         ["Arbeitsunterlagen (Beihilfeanalyse)", "erstattete Ausgaben"],
         "Falls ja, ist die beihilferechtsspezifische Checkliste auszufüllen. Der auf Grundlage von VKO erstattete Betrag ist der für die Beihilfeintensität/-höhe bzw. die Ausgleichsleistung bei DAWI zu berücksichtigende Betrag."),
        ("2.2.6", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) / 94(3) CPR",
         "Falls zutreffend: Werden die in der Methodik festgelegten Bedingungen eingehalten?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR"],
         "Die Methodik kann spezifische Bedingungen für die Verwendung der Kosten je Einheit vorsehen. Zusätzliche Bedingungen sind unüblich, müssen aber, falls genannt, erfüllt sein (z. B. bei Kosten je Einheit für ein Haus mit verbesserter Energieeffizienz von mindestens 100 kWh/m²/Jahr Primärenergie die einzuhaltende Mindestbedingung). Der Prüfer prüft die Erfüllung und empfiehlt andernfalls die erforderlichen Berichtigungen."),
    ]),
    ("Abschnitt 2 · Teil 3 — Anwendung: Pauschalbeträge", [
        ("2.3.1", "KA2 BK2.1 / KA3 BK3.3 · Art. 73(3) CPR · Art. 22(6) Interreg-VO",
         "Ist die Verwendung des Pauschalbetrags in der Aufforderung zur Einreichung von Vorschlägen und im Dokument mit den Bedingungen für die Unterstützung vorgesehen?",
         ["Aufforderung zur Einreichung von Vorschlägen (oder gleichwertig)", "Dokument mit den Bedingungen für die Unterstützung"],
         "Die Grundsätze der Transparenz und Gleichbehandlung sind sicherzustellen; alle potenziellen Begünstigten müssen Zugang zu den Informationen über die verwendete Erstattungsform haben. Daher ist die Verwendung des Pauschalbetrags in der Aufforderung zur Einreichung von Vorschlägen (oder einem gleichwertigen Dokument) anzugeben und zusätzlich im Dokument mit den Bedingungen für die Unterstützung zu nennen. Wurden die Grundsätze nicht eingehalten, beurteilt der Prüfer die Auswirkungen und empfiehlt der Verwaltungsbehörde, sie künftig einzuhalten."),
        ("2.3.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) / 94(3) CPR",
         "Wurden die Leistungen (deliverables) in Übereinstimmung mit der VKO-Methodik erbracht?",
         ["erstattete Ausgaben", "Belege für erbrachte Leistungen"],
         "Die vereinbarten Leistungen (ggf. Meilensteine) des Projekts müssen vollständig erbracht und die Outputs/Ergebnisse in Übereinstimmung mit den in der VKO-Methodik festgelegten Bedingungen geliefert worden sein. Die erbrachten Leistungen müssen dokumentiert sein. Der Prüfer prüft die Belege zum Nachweis; sind die Leistungen nicht erbracht oder nicht belegt, empfiehlt er der Verwaltungsbehörde/Prüfbehörde die erforderlichen Berichtigungen."),
        ("2.3.3", "KA4 BK4.3 / KA9 BK9.1 · Art. 53 / Art. 94 CPR",
         "Wurde der Pauschalbetrag mit der in der Methodik vorgesehenen Anpassungsmethode angepasst?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR"],
         "Im Falle einer Anpassung prüft der Prüfer, ob die in der VKO-Methodik vorgesehene Anpassungsmethode eingehalten wurde, und empfiehlt bei Unregelmäßigkeiten finanzielle Berichtigungen. War keine Anpassungsmethode vorgesehen, darf der Pauschalbetrag nicht geändert werden."),
        ("2.3.4", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) CPR · anwendbare Beihilfevorschriften",
         "Sind Beihilfevorschriften anwendbar?",
         ["erstattete Ausgaben"],
         "Falls ja, ist die beihilferechtsspezifische Checkliste auszufüllen. Der auf Grundlage von VKO erstattete Betrag ist der für die Beihilfeintensität/-höhe bzw. die Ausgleichsleistung bei DAWI zu berücksichtigende Betrag."),
        ("2.3.5", "KA4 BK4.3 / KA9 BK9.1 · Art. 74(1)(a)(ii) / 94(3) CPR",
         "Falls zutreffend: Werden die in der Methodik festgelegten Bedingungen eingehalten?",
         ["VKO-Methodik", "Anlage 1 zu Anhang V CPR", "Belege zum Nachweis der Erfüllung der Bedingungen"],
         "Über die Basiskosten hinaus kann die Methodik spezifische Bedingungen für die Verwendung der Pauschalbeträge vorsehen. Zusätzliche Bedingungen sind unüblich, müssen aber, falls genannt, erfüllt sein (z. B. bei einem Pauschalbetrag für eine Schulung mit mindestens 10 Teilnehmern die Bedingung zur Teilnehmerzahl). Der Prüfer prüft die Erfüllung und empfiehlt andernfalls die erforderlichen Berichtigungen."),
    ]),
    ("Abschnitt 2 · Teil 4 — Doppelfinanzierung (Art. 63 CPR)", [
        ("2.4.1", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Liegt bei mehreren Erstattungsformen innerhalb desselben Vorhabens eine doppelte Geltendmachung derselben Kostenkategorien vor?",
         ["VKO-Methodik, Dokument zur Definition der von VKO abgedeckten Kostenkategorien", "Belege für andere Kostenkategorien"],
         "Bei Bedarf ist die Checkliste zur Doppelfinanzierung unter den thematischen Prüfungen heranzuziehen. Stellt der Prüfer eine doppelte Geltendmachung derselben Kostenkategorien fest, empfiehlt er der Verwaltungsbehörde/Prüfbehörde die erforderlichen Berichtigungen."),
        ("2.4.2", "KA4 BK4.3 / KA9 BK9.1 · Art. 63 CPR",
         "Ist das Risiko der Doppelfinanzierung aus anderen Unionsinstrumenten oder Fonds gemindert?",
         ["Protokolle oder Schriftverkehr zwischen Verwaltungsbehörden", "Prüfungen in IT-Systemen und/oder offenen Plattformen", "Verfahren, Checklisten, Selbsterklärungen der Begünstigten"],
         "Die Verwaltungsbehörden eines Mitgliedstaats können (vor der Auswahl) prüfen, ob die für Programm X vorgeschlagenen Vorhaben nicht bereits in Programm Y zur Finanzierung genehmigt wurden; die Erörterungen sollten inhaltlich (nicht nur formal) sein. Die Verwaltungsbehörde kann Prüfungen in IT-Systemen (z. B. Arachne, veröffentlichte Listen ausgewählter Vorhaben) oder offenen Datenplattformen (z. B. Kohesio) durchführen. Bei Verwaltungskontrollen sollten die Kontrolleure die Publizitätsmaßnahmen der Begünstigten prüfen, um Finanzierung aus anderen Quellen zu erkennen. Begünstigte können zudem (Selbsterklärungen) erklären, dass keine Doppelfinanzierung vorliegt; die Verwaltungsbehörde sollte dies mit anderen Quellen abgleichen."),
    ]),
    ("Abschnitt 2 · Teil 5 — Verpflichtende Verwendung von VKO", [
        ("2.5", "—",
         "Wurde die verpflichtende Verwendung von VKO eingehalten?",
         [],
         "Prüfen, ob in den Fällen, in denen die Verordnung die Verwendung vereinfachter Kostenoptionen verbindlich vorschreibt, diese auch tatsächlich angewandt wurden."),
    ]),
]

CONCLUSION = (
    "Schlussfolgerung: Entsprechen die VKO-Methodik und ihre Anwendung den "
    "regulatorischen Anforderungen? Die Prüfer schließen, ob die vereinfachten "
    "Kostenoptionen (Pauschalsätze, Pauschalbeträge, Kosten je Einheit) nach einer "
    "fairen, gerechten und nachprüfbaren Methode (Art. 53 CPR) festgelegt und "
    "rechtmäßig und ordnungsgemäß angewandt wurden (Hauptfeststellungen bitte "
    "angeben)."
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
                "Musterprüfcheckliste der Europäischen Kommission zu den "
                "vereinfachten Kostenoptionen (VKO/SCO), Förderperiode 2021-2027 — "
                "ins Deutsche übertragen und in die Designer-Struktur überführt. "
                "Abschnitt 1 bewertet die VKO-Methodik (faire, gerechte und "
                "nachprüfbare Methode, Entwurfsbudget, Unions-/mitgliedstaatliche "
                "Methoden, delegierter Rechtsakt, Stundensätze), Abschnitt 2 die "
                "Anwendung auf Pauschalsätze, Kosten je Einheit und Pauschalbeträge. "
                "Englisches Original siehe Quelldokument."
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
                "managing_authority": "",
                "beneficiaries": "",
                "total_amount_audited": "",
                "prepared_by": "", "prepared_date": "",
                "reviewed_by": "", "reviewed_date": "",
                "kom_reference": "EC audit checklists 2021-2027 — Checklist SCO",
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
