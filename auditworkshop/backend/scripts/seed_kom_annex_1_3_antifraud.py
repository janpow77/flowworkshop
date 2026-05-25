"""
flowworkshop · scripts/seed_kom_annex_1_3_antifraud.py

Seedet die KOM-Mustercheckliste "Annex 1.3 — Anti-fraud (KR 7)"
(Betrugsbekämpfung, Kernanforderung 7) als deutsche, in die
audit_designer-Struktur überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Sektionen (Überschriften) →
Fragen (mit Rechtsgrundlage, Antwortset Ja/Nein/Teilweise/Entfällt, Belegen
und "Notes for auditor" als HINT-Kindknoten). Englisches Original bleibt als
source_document hinterlegt.

Idempotent: vorhandener Seed (gleiche source_document_name) wird zuvor entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_3_antifraud.py
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

SOURCE_DOC = "Annex 1.3 Anti-fraud (KR 7).docx"
SOURCE_PATH = "checklist_sources/annex_1_3_antifraud.docx"
TITLE = "KOM — Betrugsbekämpfung (KA7)"

INSTRUCTION = (
    "Hinweis: Die Checkliste dient der Beurteilung, ob die Verwaltungsbehörde "
    "über wirksame und verhältnismäßige Maßnahmen zur Betrugsbekämpfung verfügt "
    "(Kernanforderung 7, KA7). Geprüft werden insbesondere die Betrugsrisiko"
    "bewertung, die Maßnahmen zur Prävention, Aufdeckung und Korrektur von "
    "Unregelmäßigkeiten sowie die Verfahren für die Meldung und Überwachung von "
    "Verdachtsfällen einschließlich Interessenkonflikten. Die Fragen leiten sich "
    "aus der Verordnung ab und spiegeln die wesentlichen Prüfpunkte wider."
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

# Sektionen mit Fragen: (key, legal_reference, frage_de, belege_de[list], note_de)
PARTS = [
    ("Abschnitt 1 — Betrugsrisikobewertung (BRB) — KA7 BK7.1", [
        ("1.1", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Erstellt und führt die Verwaltungsbehörde/zwischengeschaltete Stelle rechtzeitig eine Betrugsrisikobewertung (BRB) durch? Falls die Antwort 'Nein' lautet, bitte zu Abschnitt 2 wechseln.",
         ["Risikobewertung", "Leitfaden zur Betrugsrisikobewertung 2014-2020 (sinngemäß anzuwenden)"],
         "Die Verwaltungsbehörden führen rechtzeitig eine Betrugsrisikobewertung der Auswirkungen und der Eintrittswahrscheinlichkeit der für die Schlüsselprozesse der Programmdurchführung relevanten Betrugsrisiken durch."),
        ("1.2", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Wurde die Betrugsrisikobewertung vor Beginn der Programmdurchführung durchgeführt?",
         ["Risikobewertung"],
         "Dies ist keine rechtliche Anforderung, sollte jedoch als bewährte Praxis betrachtet werden. Der Beginn der Programmdurchführung ist hier als die erste Auswahl von Vorhaben zu verstehen."),
        ("1.3", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Umfasst diese Bewertung auch Risiken im Zusammenhang mit Interessenkonflikten (Auswirkungen und Eintrittswahrscheinlichkeit der für die Programmdurchführung relevanten Risiken)?",
         [],
         ""),
        ("1.4", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Berücksichtigt die Bewertung die Auswirkungen und die Eintrittswahrscheinlichkeit der für die Schlüsselprozesse der Programmdurchführung relevanten Betrugsrisiken?",
         ["Risikobewertung"],
         "Zur Beurteilung der Relevanz der Betrugsrisiken für die Schlüsselprozesse ist zu beachten, dass die Schlüsselprozesse ab Programmbeginn folgende sind: die Auswahl der Antragsteller; die Durchführung und Überprüfung der Vorhaben; die Zahlungen. Siehe Anhang: Analyse der BRB-Methodik."),
        ("1.5", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Aktualisiert die Verwaltungsbehörde/zwischengeschaltete Stelle die Betrugsrisikobewertung regelmäßig?",
         ["Risikobewertung", "Verfahren", "Sitzungsprotokolle und aktualisierte Risikobewertung"],
         "Die Betrugsrisikobewertung sollte idealerweise jährlich oder — je nach Risikoniveau — alle zwei Jahre durchgeführt werden. Die Ergebnisse der Betrugsrisikobewertung sollten von der oberen Leitungsebene der Verwaltungsbehörde gebilligt werden. Beurteilen, ob ein Verfahren besteht, das die Wiederholung/Aktualisierung der BRB sicherstellt. (Hinweis: Ist das festgestellte Risikoniveau sehr gering und wurden im Vorjahr keine Betrugsfälle gemeldet, kann die Verwaltungsbehörde beschließen, ihre Selbstbewertung nur jedes zweite Jahr zu überprüfen.)"),
        ("1.6", "KA7 BK7.1 · Art. 74(1)(c) CPR",
         "Werden die Ergebnisse der Betrugsrisikobewertung von der Leitung der Verwaltungsbehörde/zwischengeschalteten Stelle gebilligt?",
         ["Risikobewertung"],
         "Dies ist keine regulatorische Anforderung, wird jedoch im Einklang mit den internen Kontrollstandards empfohlen."),
    ]),
    ("Abschnitt 2 — Angemessene Maßnahmen zur Prävention, Aufdeckung und Korrektur von Unregelmäßigkeiten — KA7 BK7.2", [
        ("2.1", "KA7 BK7.2 · Art. 69(2), (12), Art. 74(1)(c)-(d) und Anhang XII CPR",
         "Umfassen die Maßnahmen der Verwaltungsbehörde/zwischengeschalteten Stelle die Analyse digitaler Informationen, etwa durch den Einsatz eines Data-Mining- oder Risiko-Scoring-Werkzeugs?",
         ["IT-Systeme"],
         "Prüfen, ob die Verwaltungsbehörde/zwischengeschaltete Stelle ARACHNE oder ein gleichwertiges nationales Werkzeug verwendet."),
        ("2.2", "KA7 BK7.2 · Art. 69(2), (12), Art. 74(1)(c)-(d) und Anhang XII CPR",
         "Hat die Verwaltungsbehörde ein System eingerichtet, um betrügerisches Verhalten rechtzeitig aufzudecken, indem sie eine Reihe spezifischer Maßnahmen zur Betrugsaufdeckung oder Warnsignale ('red flags') konzipiert und umgesetzt hat, wie etwa:",
         ["Verfahrenshandbücher und Checklisten für die Auswahl der Vorhaben und die Verwaltungsüberprüfungen"],
         ""),
        ("2.2.1", "—",
         "Entwicklung einer angemessenen Grundhaltung?",
         [],
         "Die Verwaltungsbehörde könnte Betrugsrisiken mit spezialisierten und gezielten Aufdeckungstechniken begegnen, wobei benannte Personen für deren Durchführung verantwortlich sind. Darüber hinaus haben alle an der Durchführung eines Strukturförderzyklus Beteiligten eine Rolle dabei, potenziell betrügerische Tätigkeiten zu erkennen und entsprechend zu handeln. Dies erfordert die Förderung einer angemessenen Grundhaltung/Sensibilisierung (z. B. regelmäßige Schulungen zum Thema Betrug, bereitgestellte Ressourcen). Ein gesundes Maß an Skepsis sollte gefördert werden, zusammen mit einem aktuellen Bewusstsein dafür, was mögliche Warnsignale für Betrug sein könnten."),
        ("2.2.2", "—",
         "Sind angemessene Maßnahmen zur Erkennung von Warnsignalen ('red flags') und Betrugsindikatoren vorhanden und funktionieren sie wirksam?",
         [],
         "Betrugsindikatoren sind spezifischere Anzeichen oder Warnsignale ('red flags') dafür, dass eine betrügerische Tätigkeit stattfindet, bei denen eine sofortige Reaktion erforderlich ist, um zu prüfen, ob weitere Schritte notwendig sind. Indikatoren können auch spezifisch für Tätigkeiten sein, die häufig im Rahmen von Strukturförderprogrammen auftreten, wie etwa Auftragsvergabe und Personalkosten. Die Kommission hat den Mitgliedstaaten folgende Informationen bereitgestellt: COCOF 09/0003/00 vom 18.2.2009 — Informationsvermerk über Betrugsindikatoren für EFRE, ESF und Kohäsionsfonds; OLAF-Kompendium anonymisierter Fälle — Strukturmaßnahmen; OLAF-Praxisleitfaden zu Interessenkonflikten; OLAF-Praxisleitfaden zu gefälschten Dokumenten. Diese Veröffentlichungen sollten eingehend gelesen und ihr Inhalt unter allen Mitarbeitenden, die solches Verhalten aufdecken könnten, verbreitet werden. Insbesondere müssen diese Indikatoren allen vertraut sein, die in Funktionen zur Überprüfung von Tätigkeiten der Begünstigten tätig sind."),
        ("2.2.3", "—",
         "Sofern weitere Aufdeckungsmaßnahmen vorhanden sind, bitte beschreiben.",
         [],
         ""),
        ("2.2.4", "—",
         "Prüfen, ob ein Verfahren für Hinweisgeber (Whistleblower) besteht.",
         [],
         "Die Wirksamkeit dieses Verfahrens prüfen (wurde ein Fall gemeldet?)."),
        ("2.2.5", "—",
         "Hat die Verwaltungsbehörde/zwischengeschaltete Stelle angemessene Verfahren und Werkzeuge zur Datenerhebung über die wirtschaftlichen Eigentümer der Begünstigten und der Auftragnehmer eingerichtet?",
         [],
         "Dies ist eine Neuerung in der Dachverordnung (prüfen, ob es von der Verwaltungsbehörde/zwischengeschalteten Stelle angemessen behandelt wird)."),
        ("2.2.6", "—",
         "Angeben, ob die vorstehenden Maßnahmen (einschließlich Verfahren) die Prävention, Aufdeckung und Korrektur von Unregelmäßigkeiten abdecken.",
         [],
         "Auf Grundlage Ihres fachlichen Urteils beurteilen, ob diese Maßnahmen angemessen sind (falls nicht, bitte Mängel auflisten)."),
    ]),
    ("Abschnitt 3 — Angemessene Maßnahmen für die Meldung und Überwachung von Unregelmäßigkeiten und (Verdachts-)Betrugsfällen einschließlich Interessenkonflikten — KA7 BK7.3 und BK7.4", [
        ("3.1", "KA7 BK7.3 · Art. 69(2), (12), Art. 74(1)(c)-(d) und Anhang XII CPR",
         "Sind angemessene Maßnahmen für die Meldung und Überwachung vorhanden für: Unregelmäßigkeiten; (Verdachts-)Betrugsfälle; Interessenkonflikte?",
         ["Verfahrenshandbücher der Verwaltungsbehörde"],
         "Beurteilen, ob es Kommunikation und Schulung der Mitarbeitenden zu diesen Meldemechanismen gab/gibt, um sicherzustellen, dass sie: verstehen, wo sie Verdachtsfälle betrügerischen Verhaltens oder einer Kontrolle melden sollen; darauf vertrauen, dass diese Verdachtsfälle von der Leitung aufgegriffen werden; darauf vertrauen, dass sie vertraulich melden können und dass die Organisation keine Vergeltung gegen Mitarbeitende duldet, die Verdachtsfälle melden."),
        ("3.2", "KA7 BK7.4 · Art. 69(12), Anhang XII CPR",
         "Gewährleisten die Meldemechanismen eine ausreichende Koordinierung zwischen den Verwaltungs- und/oder Prüfbehörden, den zuständigen Ermittlungsbehörden im Mitgliedstaat, der EUStA, OLAF und der Kommission?",
         [],
         "Bitte auflisten, welche Stellen an den Meldemechanismen beteiligt sind. Bitte angeben, ob die Meldung eine elektronische Meldung an die EK über das IMS umfasst und welche Stelle die zuständige Stelle des Mitgliedstaats ist."),
        ("3.3", "—",
         "Prüfen, dass alle relevanten Fälle der Kommission über das Unregelmäßigkeiten-Meldesystem (IMS) gemeldet wurden, im Einklang mit den Anforderungen des Anhangs XII CPR.",
         [],
         "Prüfen, ob angemessene Verfahren für die Meldung über das IMS vorhanden sind. Um Beispiele für Meldungen von Unregelmäßigkeiten bitten und beurteilen, ob diese im Einklang mit Anhang XII CPR stehen."),
        ("3.4", "—",
         "Werden Betrugsverdachtsfälle an die strafrechtlichen Ermittlungsbehörden weitergeleitet?",
         [],
         "Bitte angeben, wie die Verwaltungsbehörde/zwischengeschaltete Stelle die strafrechtlichen Ermittlungsbehörden benachrichtigt (auch die einschlägigen Verfahren prüfen). Welche Stellen werden benachrichtigt?"),
        ("3.5", "KA7 BK7.4 · Art. 69(2), (12), Art. 74(1)(c)-(d) und Anhang XII CPR",
         "Werden diese Mechanismen als angemessen erachtet?",
         [],
         "Beurteilen, ob ein Verfahren für Hinweisgeber (Whistleblowing) vorhanden ist, d. h. betreffend das Recht, eine externe unabhängige Kontaktstelle über Unregelmäßigkeiten oder Fehlverhalten zu informieren. Falls zutreffend, beurteilen, ob die Regeln angemessen sind, um Mitarbeitende im Falle einer Meldung vor internen Sanktionen zu schützen. Wurde das Verfahren bereits in der Praxis angewandt, bitte kurz beschreiben und beurteilen, inwieweit die Ergebnisse dessen Angemessenheit belegen."),
        ("3.6", "KA7 BK7.4 · Art. 69(2), (12), Art. 74(1)(c)-(d) und Anhang XII CPR",
         "Gewährleisten die Meldemechanismen eine ausreichende Koordinierung in Fragen der Betrugsbekämpfung mit der Prüfbehörde, den zuständigen Ermittlungsbehörden im Mitgliedstaat (einschließlich der Antikorruptionsbehörden), der Kommission, OLAF und der EUStA (sofern zutreffend), einschließlich der Meldung in der IMS-Datenbank?",
         [],
         "Beurteilen, ob die Verwaltungsbehörde ein Verfahren eingerichtet hat, das sicherstellt, dass Betrugsverdachtsfälle von der vom Mitgliedstaat benannten Stelle im Einklang mit den einschlägigen Anforderungen über das IMS an OLAF gemeldet werden. Falls (ein) Betrugsverdachtsfall/-fälle gemeldet wurde(n), beurteilen, ob das Verfahren korrekt angewandt wurde. Beurteilen, ob die Begünstigten darüber informiert werden, wie sie OLAF mit etwaigen ihnen vorliegenden Informationen ansprechen können. (Siehe COCOF 09/0003/00 vom 18.2.2009 — Informationsvermerk über Betrugsindikatoren für EFRE, ESF und Kohäsionsfonds, der auch Informationen zu den Meldeverfahren enthält.)"),
    ]),
]

# Anhang — Analyse der Methodik der Betrugsrisikobewertung (als Hinweis-Block)
ANNEX_TITLE = "Anhang — Analyse der Methodik der Betrugsrisikobewertung"
ANNEX_HINT = (
    "Hinweis: Beurteilen, ob die für die Betrugsrisikobewertung verwendete "
    "Methodik (auf Grundlage der EK-Methodik oder einer anderen) die folgenden "
    "wesentlichen Schritte umfasst: "
    "1. Quantifizierung der Eintrittswahrscheinlichkeit und der Auswirkung des "
    "spezifischen Betrugsrisikos (Bruttorisiko); "
    "2. Bewertung der Wirksamkeit der vorhandenen Kontrollen zur Minderung des "
    "Bruttorisikos; "
    "3. Bewertung des Nettorisikos nach Berücksichtigung der Wirkung der "
    "vorhandenen Kontrollen; "
    "4. Bewertung der Wirkung der geplanten zusätzlichen Kontrollen auf das "
    "Nettorisiko (Restrisiko); "
    "5. Festlegung des Zielrisikos, d. h. des Risikoniveaus, das die "
    "Verwaltungsbehörde als tolerierbar erachtet. "
    "Weicht die Methodik vollständig von der obigen ab, bitte beschreiben und "
    "ihre Angemessenheit im Verhältnis zu den Auswirkungen und der "
    "Eintrittswahrscheinlichkeit der für die Schlüsselprozesse der "
    "Programmdurchführung relevanten Betrugsrisiken beurteilen. Die "
    "Detailtests zu den Schritten 1 bis 5 (Stichprobe von Risiken aus dem "
    "BRB-Werkzeug, Bewertung von Brutto-, Netto- und Zielrisiko sowie der "
    "Aktionspläne) sind jeweils in einem gesonderten Arbeitspapier zu "
    "dokumentieren. Zudem ist der Gesamtprozess der BRB unter Berücksichtigung "
    "bewährter Praktiken zu überprüfen: angemessene Zusammensetzung des "
    "Bewertungsteams (Sachkunde und Erfahrung, nicht ausgelagert, idealerweise "
    "abteilungsübergreifend; die Prüfbehörde übernimmt keine entscheidende, "
    "sondern allenfalls eine beratende oder beobachtende Rolle); Nachweis, dass "
    "Informationsquellen wie Prüfberichte, Betrugsmeldungen und Kontroll-"
    "Selbstbewertungen berücksichtigt werden; klare Dokumentation des "
    "Selbstbewertungsprozesses zur Nachvollziehbarkeit der gezogenen "
    "Schlussfolgerung."
)

CONCLUSION = (
    "Schlussfolgerung: Verfügt die Verwaltungsbehörde über wirksame und "
    "verhältnismäßige Maßnahmen und Verfahren zur Betrugsbekämpfung unter "
    "Berücksichtigung der festgestellten Risiken (Kernanforderung 7, KA7)? "
    "Die Prüfer schließen, ob die Betrugsrisikobewertung, die Maßnahmen zur "
    "Prävention, Aufdeckung und Korrektur von Unregelmäßigkeiten sowie die "
    "Verfahren zur Meldung und Überwachung von Verdachtsfällen regelkonform "
    "eingerichtet sind und wirksam funktionieren."
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
            | (ChecklistTemplate.title == "KOM — Betrugsbekämpfung (KR7)")
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
                "Betrugsbekämpfung (Kernanforderung 7, KA7), Förderperiode "
                "2021-2027 — ins Deutsche übertragen und in die Designer-Struktur "
                "überführt. Englisches Original siehe Quelldokument."
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
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.3 (KA7)",
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

        # Sektionen + Fragen
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

        # Anhang — Analyse der BRB-Methodik (Hinweis-Block)
        h_annex = add_node(node_type="HEADING", title=ANNEX_TITLE)
        add_node(node_type="HINT", parent_id=h_annex.id, title=ANNEX_HINT)

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
