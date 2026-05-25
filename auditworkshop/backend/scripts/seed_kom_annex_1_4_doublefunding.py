"""
flowworkshop · scripts/seed_kom_annex_1_4_doublefunding.py

Seedet die KOM-Mustercheckliste "Annex 1.4 — Double funding"
(Doppelfinanzierung) als deutsche, in die audit_designer-Struktur überführte
Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Hinweise für Prüfer →
Sektion (Überschrift) → Fragen (mit Rechtsgrundlage, Antwortset
Ja/Nein/Teilweise/Entfällt, Belegen und "Notes for auditor" als HINT-Kindknoten)
→ Schlussfolgerung. Englisches Original bleibt als source_document hinterlegt.

Idempotent: vorhandener Seed (gleiche source_document_name oder gleicher Titel)
wird zuvor entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_4_doublefunding.py
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

SOURCE_DOC = "Annex 1.4 Double funding (1) (2).docx"
SOURCE_PATH = "checklist_sources/annex_1_4_doublefunding.docx"
TITLE = "KOM — Doppelfinanzierung"

INSTRUCTION = (
    "Hinweis: Die thematische Checkliste dient der Beurteilung, ob die "
    "Verwaltungsbehörde über wirksame Verfahren zur Vermeidung von "
    "Doppelfinanzierung verfügt. Doppelfinanzierung kann in verschiedenen "
    "Konstellationen auftreten: a) Doppelfinanzierung der Vorhaben (oder von "
    "Ausgaben innerhalb dieser Vorhaben) in zwei EU-finanzierten Programmen oder "
    "zwei verschiedenen EU-Fonds (z. B. nationales EFRE-Verkehrsprogramm und "
    "regionales EFRE-Programm für ein Verkehrsinfrastrukturvorhaben oder EFRE und "
    "Horizont für ein Forschungsvorhaben); b) Doppelfinanzierung einer einzelnen "
    "Kostenposition innerhalb eines Vorhabens (z. B. als Realkosten geltend "
    "gemachte Ausgaben, die zugleich durch eine vereinfachte Kostenoption "
    "abgedeckt sind); c) Doppelfinanzierung gegenüber der Kommission (z. B. wird "
    "das Ergebnis des Vorhabens für die Etappenziele unter der ARF "
    "berücksichtigt und die Realkosten werden unter unserem Programm geltend "
    "gemacht). Selbst wenn keine Doppelfinanzierung mit EU-Instrumenten (und "
    "damit im Sinne der Dachverordnung) vorliegt, bleibt die Doppelung "
    "problematisch: War die Ausgabe bereits durch ein nationales Programm "
    "abgedeckt, ist sie dann noch erforderlich? Bei staatlicher Beihilfe — wurde "
    "die Beihilfeintensität eingehalten? Die ursprünglich grau hervorgehobenen "
    "Fragen sind auf Ebene der Vorhaben zu prüfen (Kernanforderung 2 und 4); die "
    "Maßnahmen auf Programmebene (Kernanforderung 1) werden durch Überprüfung "
    "der eingerichteten Verfahren beurteilt. Doppelfinanzierung lässt sich auch "
    "auf Makroebene prüfen (z. B. durch Abgleich der Liste der geförderten "
    "Vorhaben eines Programms mit anderen Datenbanken auf Ausnahmen/Überschneidungen)."
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
    ("Vermeidung von Doppelfinanzierung", [
        ("1", "Art. 11 CPR",
         "Beachten die durch das Programm finanzierten Arten von Tätigkeiten die (gegebenenfalls) in der Partnerschaftsvereinbarung beschriebene Abgrenzung?",
         ["Partnerschaftsvereinbarung (Abschnitt 2)", "Aufforderungen zur Einreichung von Vorschlägen", "Fördervereinbarungen (für die Vorhaben in der Stichprobe)"],
         "Die Partnerschaftsvereinbarung muss die Koordinierung, Abgrenzung und Komplementarität zwischen den Fonds sowie gegebenenfalls die Koordinierung zwischen nationalen und regionalen Programmen enthalten. (Beispiel: Die Partnerschaftsvereinbarung kann festlegen, dass der einzige Fonds zur Finanzierung von Schulungen im jeweiligen Mitgliedstaat der ESF ist, oder dass Programm X nationale Straßen und Programm Y Landstraßen finanziert, oder dass eine klare geografische Abgrenzung besteht.)"),
        ("2", "Art. 63(9) CPR · KA/BK 2.4, 4.2, 9.1",
         "Haben die Programmbehörden (Verwaltungsbehörde, Prüfbehörde) Zugang zu den Systemen, Datenbanken und Registern der nationalen Fördermittelgeber, um Doppelfinanzierung zu vermeiden?",
         None,
         "Die Programmbehörden sollten die erforderlichen Maßnahmen ergreifen, um die interinstitutionelle Koordinierung und Kommunikation zwischen den nationalen Bewilligungsbehörden sicherzustellen, damit ausreichende Mittel und Informationen zur Verfügung stehen, um Doppelfinanzierung zu vermeiden."),
        ("3", "Art. 63(9) CPR · KA/BK 2.4",
         "Ergreift die Verwaltungsbehörde zum Zeitpunkt der Auswahl der Vorhaben Maßnahmen, um Doppelfinanzierung (aus anderen Fonds oder anderen Programmen) zu vermeiden? Falls ja, bitte die Maßnahmen auflisten.",
         ["Protokolle oder Schriftverkehr zwischen Verwaltungsbehörden", "Prüfungen in verschiedenen IT-Systemen und/oder offenen Plattformen", "sonstiger Prüfpfad, der eine solche Tätigkeit belegt", "Verfahren", "Checklisten", "Eigenerklärungen der Begünstigten"],
         "Die Verwaltungsbehörden eines Mitgliedstaats könnten (vor der Auswahl) Sitzungen organisieren, um zu prüfen, ob die zur Förderung unter Programm X vorgeschlagenen Vorhaben nicht bereits zur Förderung unter Programm Y genehmigt wurden. Wichtig ist, dass die Erörterungen inhaltlich (nicht nur formal) erfolgen. Die Verwaltungsbehörde kann Prüfungen in den IT-Systemen anderer Fonds/Programme durchführen (einschließlich Google/ähnlicher Suchmaschinen/Arachne, veröffentlichter Listen ausgewählter Vorhaben auf den Programm-Websites) oder in offenen Datenplattformen (z. B. Kohesio). Im Rahmen der Verwaltungskontrolle sollten die Prüfer die Publizitätsmaßnahmen der Begünstigten (z. B. Website, Bautafeln) prüfen, um festzustellen, ob diese Förderung aus anderen Quellen erhalten haben, und anschließend prüfen, ob die für ihr Vorhaben eingereichten Rechnungen nicht auch im Rahmen anderer Vorhaben eingereicht wurden (zudem die Verwaltungsbehörde fragen, wie die Abgrenzung sichergestellt wurde). Die Begünstigten können auch (durch Eigenerklärungen) erklären, dass keine Doppelfinanzierung vorliegt; die Verwaltungsbehörde sollte dies mit anderen Quellen abgleichen (z. B. Prüfungen in verschiedenen IT-Systemen). Für die Vorhaben in der Stichprobe sollte der Prüfer eine Überprüfung in den verfügbaren IT-Systemen vornehmen."),
        ("4", "Art. 63(9) CPR · KA/BK 2.4",
         "Sind die von der Verwaltungsbehörde zum Zeitpunkt der Auswahl getroffenen Maßnahmen im Hinblick auf Doppelfinanzierung angemessen?",
         None,
         ""),
        ("5", "Art. 63(9) CPR · KA/BK 2.4, 9.1",
         "Sehen die nationalen Förderfähigkeitsregeln oder die Aufforderungen zur Einreichung von Vorschlägen eine klare Abgrenzung der Kostenkategorien vor?",
         ["Nationale Förderfähigkeitsregeln", "Aufforderungen zur Einreichung von Vorschlägen"],
         "Zur Minderung des Risikos einer Doppelfinanzierung innerhalb des Vorhabens wird empfohlen, dass eine Kostenposition (z. B. ein Laptop) nicht unter zwei verschiedenen Kostenkategorien förderfähig ist. Dies kann als Empfehlung zur Verbesserung des Systems angesehen werden, ist jedoch nicht verpflichtend. Falls nicht vorhanden, siehe nächste Frage. Diese klare Abgrenzung ist im Fall von Pauschalsätzen (vereinfachte Kostenoptionen) verpflichtend."),
        ("6", "Art. 63(9) CPR · KA/BK 2.4, 4.2, 9.1",
         "Gibt es für den Fall, dass eine Kostenposition in zwei verschiedenen Kostenkategorien (Budgetlinien) abgedeckt ist, eine Überprüfung zur Vermeidung von Doppelfinanzierung?",
         ["Anwendbares Verfahren / anwendbare Verfahren", "Fördervereinbarung oder Antragsformular"],
         "Falls dies in der Praxis vorkommt (z. B. ist Papier in den indirekten Kosten, aber auch in der externen Sachverständigenleistung enthalten), sollten Überprüfungen zur Vermeidung der Doppelfinanzierung eingerichtet sein. Für die Vorhaben in der Stichprobe sollte der Prüfer im Buchführungssystem / in den Finanzaufstellungen auf Hinweise auf mehrere Finanzierungsquellen prüfen und die erforderlichen Nachweise verlangen, dass in solchen Fällen die Doppelfinanzierung vermieden wurde. Zu beachten ist, dass dies auch bei vereinfachten Kostenoptionen vorkommen kann (z. B. wird ein Pauschalsatz von 20 % für Personal verwendet, der Begünstigte hat jedoch zusätzlich ein Gehalt für die Projektleitung als Realkosten geltend gemacht, das erstattet wurde)."),
        ("7", "Art. 63(9) CPR · KA/BK 4.2, 9.1",
         "Verfügt die Verwaltungsbehörde über ein Verfahren / über Maßnahmen, um zu überprüfen, dass die doppelte Geltendmachung derselben Ausgabenposition vermieden wird?",
         ["Verfahren", "sonstiger Prüfpfad (z. B. Rechnungen mit Vorhabencode)"],
         "Eine von Programmen genutzte Lösung bestand beispielsweise darin, den Code des Vorhabens auf der Rechnung anzubringen (bevor diese in das IT-System hochgeladen und der Betrag zur Erstattung beantragt wurde). Darüber hinaus sollte die Verwaltungsbehörde verlangen und überwachen, dass der Begünstigte einen eindeutigen Buchungscode für das Vorhaben sowie das Buchführungssystem des Begünstigten verwendet (um nachvollziehen zu können, welche Vorhaben finanziert werden). Eine weitere Möglichkeit bestünde darin, dass die Verwaltungsbehörde in den IT-Systemen des jeweiligen Mitgliedstaats nach der betreffenden Rechnungsnummer (und dem zugehörigen Auftragnehmer) sucht. Für die Vorhaben in der Stichprobe sollte der Prüfer die Finanzaufstellungen / das Buchführungssystem des Begünstigten prüfen, um besser nachzuvollziehen, welche Vorhaben finanziert werden und ob für eine bestimmte Ausgabenposition eine Überschneidung besteht."),
        ("8", "Art. 63(9) CPR · KA/BK 4.2, 9.1",
         "Sind die eingerichteten Maßnahmen / Verfahren angemessen?",
         None,
         ""),
        ("9", "Art. 63(9) CPR · KA/BK 4.2, 9.1",
         "Falls das Nichtvorliegen von Doppelfinanzierung durch Eigenerklärungen nachgewiesen wird: Wird die Information mit anderen Informationsquellen abgeglichen?",
         ["Verfügbare IT-Systeme"],
         "Die Verwaltungsbehörde kann beispielsweise in den verschiedenen IT-Systemen des jeweiligen Mitgliedstaats (oder auf EU-Ebene) nach relevanten Informationen suchen. Der Prüfer sollte für die Vorhaben in der Stichprobe ebenfalls Überprüfungen vornehmen."),
        ("10", "Art. 63(9) CPR · KA/BK 4.2, 9.1",
         "Hat das Programm Beschwerden oder sonstige Informationen im Zusammenhang mit Doppelfinanzierung erhalten (z. B. von Hinweisgebern)?",
         ["Beschwerderegister", "Beschwerdedokument", "Folgedokumente"],
         "Sowohl unmittelbar auf Ebene der Kommission als auch auf Programmebene können Hinweisgeber einen solchen Fall gemeldet haben."),
        ("11", "Art. 63(9) CPR · KA/BK 3.3",
         "Falls eine solche Beschwerde oder sonstige Information eingegangen ist: Wurde sie angemessen untersucht?",
         None,
         ""),
        ("12", "Art. 63(9) CPR · KA/BK 2.4, 4.2, 9.1",
         "Liegen Ihnen Hinweise auf einen Fall von Doppelfinanzierung vor?",
         ["Mögliche Beschwerden", "IT-Systeme"],
         "Sowohl unmittelbar auf Ebene der Kommission als auch auf Programmebene können Hinweisgeber/die Presse einen solchen Fall gemeldet haben."),
    ]),
]

CONCLUSION = (
    "Schlussfolgerung: Bitte die wesentlichen Feststellungen auflisten. Die "
    "Prüfer schließen, ob die Verwaltungsbehörde über wirksame Verfahren zur "
    "Vermeidung von Doppelfinanzierung verfügt und ob für die geprüften Vorhaben "
    "keine Doppelfinanzierung vorliegt."
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
                "Thematische Musterprüfcheckliste der Europäischen Kommission zur "
                "Vermeidung von Doppelfinanzierung, Förderperiode 2021-2027 — ins "
                "Deutsche übertragen und in die Designer-Struktur überführt. "
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
                "prepared_by": "", "prepared_date": "",
                "reviewed_by": "", "reviewed_date": "",
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.4 (Double funding)",
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
