"""
flowworkshop · scripts/seed_kom_annex_1_8_durability.py

Seedet die KOM-Mustercheckliste "Annex 1.8 — Quality of projects and durability"
als deutsche, in die audit_designer-Struktur überführte Checkliste:
Allgemeine Angaben (Kopfblock als Felder) → Teil 1/2/3 (Überschriften) →
Fragen (mit Rechtsgrundlage, Antwortset Ja/Nein/Teilweise/Entfällt, Belegen
und "Notes for auditor" als HINT-Kindknoten). Englisches Original bleibt als
source_document hinterlegt.

Idempotent: vorhandener Seed (gleiche source_document_name) wird zuvor entfernt.
Aufruf:  docker exec auditworkshop-backend python scripts/seed_kom_annex_1_8_durability.py
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

SOURCE_DOC = "Annex 1.8 Quality of projects and durability (1).docx"
SOURCE_PATH = "checklist_sources/annex_1_8_durability.docx"
TITLE = "KOM — Qualität und Dauerhaftigkeit der Vorhaben"

INSTRUCTION = (
    "Hinweis: Die Checkliste dient der Beurteilung der Qualität und der "
    "Dauerhaftigkeit der Vorhaben. Geprüft wird, ob das Vorhaben den "
    "Qualitätsanforderungen je nach Art der Investition entspricht, ob die "
    "Verwaltungsbehörde die Durchführung und Aufrechterhaltung der Investition "
    "ordnungsgemäß überwacht hat und ob die Begünstigten die "
    "Dauerhaftigkeitsanforderungen — insbesondere die Zweckbindungsfrist nach "
    "Art. 65 CPR — eingehalten haben. Die Fragen leiten sich aus der Verordnung "
    "ab und spiegeln die wesentlichen Prüfpunkte wider."
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
    ("Teil 1 — Qualität des Vorhabens bei Bewilligung", [
        ("1.1", "KA2 BK2.4 · Art. 63(1) und 73(2) CPR",
         "Entspricht der Förderantrag den Qualitätsanforderungen je nach Art der Investition?",
         [],
         "Der Prüfer sollte diesen Punkt anhand der beiden nachfolgenden Fragen beurteilen."),
        ("1.1.1", "KA2 BK2.4 · Art. 63(1) und 73(2) CPR",
         "Beruht das Vorhaben auf einer Machbarkeitsstudie (Planungen) / Bedarfsanalyse / Bedarfsermittlung, die nach den geltenden Rechtsvorschriften erstellt und genehmigt wurde?",
         ["Aufruf zur Einreichung von Vorschlägen / Ausschreibungsunterlagen", "Projektantrag / Anlagen usw."],
         "Der Prüfer sollte überprüfen, ob die Verwaltungsbehörde / zwischengeschaltete Stelle festgestellt hat, welche spezifischen Vorschriften / Anforderungen auf das geprüfte Vorhaben / die geprüfte Investition anzuwenden sind, und ob diese eingehalten wurden."),
        ("1.1.2", "KA2 BK2.4 · Art. 63(1) CPR",
         "Wurden alle erforderlichen Genehmigungen eingeholt?",
         ["Projektantrag / Anlagen"],
         ""),
        ("1.2", "KA2 BK2.4 · Art. 63(1) CPR",
         "Sind die Outputs und Ergebnisse des Vorhabens im Projektantrag klar beschrieben, sodass eine angemessene Qualität des Outputs gewährleistet ist?",
         ["Projektantrag", "Arbeitsunterlagen der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         ""),
        ("1.3", "KA2 BK2.4 · Art. 73(2) CPR",
         "Liegt eine Bewertung der Fähigkeit der Begünstigten vor, diese Investitionen aufrechtzuerhalten? Ist diese Bewertung schlüssig?",
         ["Verfahrenshandbuch und Arbeitsunterlagen der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         "Der Prüfer sollte überprüfen, ob die Verwaltungsbehörde / zwischengeschaltete Stelle prüft, dass die Begünstigten über ausreichende technische und administrative Kapazitäten zur Durchführung und Aufrechterhaltung des Vorhabens verfügen (z. B. angemessene finanzielle Mittel / erforderliche Genehmigungen / Personal mit dem nötigen Fachwissen zur Aufrechterhaltung des Vorhabens nach dessen Durchführung). Stimmt der Prüfer der Bewertung zu?"),
        ("1.4", "KA2 BK2.2 · KA3 BK3.1 und BK3.3 · Art. 63, 65 und 73(3) CPR",
         "Enthält die Fördervereinbarung Auflagen zum Betrieb und zur Instandhaltung der Investitionen?",
         ["Fördervereinbarung", "Vertrag", "sonstiges Dokument zu den Förderbedingungen usw."],
         "Der Prüfer sollte überprüfen, ob die Anforderungen an die Dauerhaftigkeit in der Fördervereinbarung klar beschrieben sind. Bei Investitionen in Infrastruktur oder produktiven Investitionen muss die / der Begünstigte die Investition während 5 Jahren ab der Abschlusszahlung an die / den Begünstigten oder innerhalb der nach den Beihilfevorschriften festgelegten Frist (falls anwendbar) aufrechterhalten. Der Mitgliedstaat kann die im ersten Unterabsatz genannte Frist auf 3 Jahre verkürzen, wenn es um die Aufrechterhaltung von Investitionen oder von durch KMU geschaffenen Arbeitsplätzen geht. Aus dem ESF+ geförderte Vorhaben müssen die Förderung zurückzahlen, wenn sie nach den Beihilfevorschriften einer Verpflichtung zur Aufrechterhaltung der Investition unterliegen."),
    ]),
    ("Teil 2 — Qualität und Überwachung während der Durchführung", [
        ("2.1", "KA2 BK2.4 · Art. 73 CPR",
         "Wurden Änderungen der im Vorhaben vorgesehenen Ziele / Investitionen von der Verwaltungsbehörde hinsichtlich Begründung und Kosten bewertet? Hatten diese Änderungen Auswirkungen auf die Qualität des Vorhabens oder hätten sie solche haben können?",
         ["Fördervereinbarung / Vertrag / Arbeitsunterlagen der Verwaltungsbehörde zu den Verwaltungskontrollen usw."],
         ""),
        ("2.2", "KA4 BK4.1 und BK4.2 · Art. 74 CPR",
         "Wurde das Vorhaben durch die (risikobasierten) Verwaltungskontrollen der Verwaltungsbehörde / zwischengeschalteten Stelle abgedeckt?",
         ["Arbeitsunterlagen, Checklisten der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         ""),
        ("2.2.1", "KA4 BK4.1 und BK4.2 · Art. 74 CPR",
         "Hat die Verwaltungsbehörde während des Durchführungszeitraums Vor-Ort-Überprüfungen der Investitionen durchgeführt?",
         ["Arbeitsunterlagen, Checklisten der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         ""),
        ("2.2.2", "KA4 BK4.2 und BK4.3 · Art. 74 CPR",
         "Hat die Verwaltungsbehörde / zwischengeschaltete Stelle Mängel hinsichtlich der Qualität der Investition / des Outputs festgestellt?",
         [],
         ""),
        ("2.2.3", "KA4 BK4.3 und BK4.5 · Art. 74 CPR",
         "Sind die Feststellungen in Bericht(en) enthalten und werden sie nachverfolgt?",
         ["Arbeitsunterlagen, Checklisten, Berichte der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         ""),
        ("2.2.4", "KA4 BK4.3 · Art. 74 CPR",
         "Gab es Finanzkorrekturen wegen mangelhafter Ausführung von Bauleistungen / Dienstleistungen / Lieferung von Waren?",
         ["Arbeitsunterlagen, Checklisten, Berichte der Verwaltungsbehörde / zwischengeschalteten Stelle"],
         ""),
        ("2.3", "Art. 74 CPR",
         "Haben die Prüfer, sofern zutreffend, Probleme festgestellt, die die ordnungsgemäße Durchführung des Vorhabens und/oder dessen Qualität beeinträchtigen?",
         [],
         ""),
    ]),
    ("Teil 3 — Zweckbestimmung, Dauerhaftigkeit und Überwachung nach Abschluss", [
        ("3.1", "Art. 65 und 74 CPR",
         "Werden die Outputs des Vorhabens (Waren / Investitionen usw.) entsprechend ihrer vorgesehenen Zweckbestimmung genutzt?",
         [],
         "Der Prüfer sollte überprüfen, ob die Projekt-Outputs von der / dem Begünstigten / den Endempfängern genutzt werden und ob die Dauerhaftigkeitsanforderungen erfüllt sind / wurden."),
        ("3.2", "VO (EU) 2021/1057 · Art. 69(4)",
         "Sind angemessene Verfahren vorhanden, um die Realität und Verlässlichkeit der Projektindikatoren und ihren Beitrag zu den Programmzielen sicherzustellen?",
         ["Verfahren der Verwaltungsbehörde, Checklisten"],
         "Bitte beachten: Es gibt Fälle, in denen die Indikatoren erst nach dem Durchführungszeitraum erreicht werden müssen. In diesem Fall sollte die Verwaltungsbehörde die Verlässlichkeit der Berichterstattung zu diesem Zeitpunkt prüfen und — falls die Indikatoren nicht erreicht werden und dies ein finanzielles Risiko darstellt oder zu einer Finanzkorrektur führt — die angemessenen Maßnahmen ergreifen."),
        ("3.2 (Publizität)", "Art. 46-48 und 74 CPR",
         "Beachten die Begünstigten die Vorschriften der EU und des Mitgliedstaats zur Öffentlichkeitsarbeit (Publizität)?",
         ["Vor-Ort-Überprüfung, Arbeitsunterlagen der Verwaltungsbehörde / zwischengeschalteten Stelle, Website der / des Begünstigten, sonstige Belege (z. B. Bilder)"],
         "Der Prüfer sollte überprüfen, ob die / der Begünstigte für angemessene Sichtbarkeit und Transparenz der Unionsförderung gesorgt und das Emblem der Union gemäß Anhang IX verwendet hat. (Hinweis: Im Original ist diese Frage wegen einer Nummerierungsdoppelung ebenfalls mit 3.2 bezeichnet.)"),
        ("3.3", "KA4 BK4.1 und BK4.2 · Art. 74 CPR",
         "Hat die Verwaltungsbehörde / zwischengeschaltete Stelle eine ordnungsgemäße Überwachung des Vorhabens beim Abschluss und nach der Durchführung sichergestellt?",
         ["Verfahrenshandbücher der Verwaltungsbehörde / zwischengeschalteten Stelle, Berichterstattung der / des Begünstigten usw."],
         ""),
        ("3.3.1", "KA4 BK4.1 und BK4.2 · Art. 74 CPR",
         "Hat die Verwaltungsbehörde / zwischengeschaltete Stelle beim Abschluss des Vorhabens / während der Zweckbindungsfrist eine Vor-Ort-Überprüfung durchgeführt?",
         ["Arbeitsunterlagen der Verwaltungsbehörde / zwischengeschalteten Stelle zur Vor-Ort-Überprüfung"],
         ""),
        ("3.3.2", "KA4 BK4.2, BK4.3 und BK4.5 · Art. 65 und 74 CPR",
         "Hat die Verwaltungsbehörde / zwischengeschaltete Stelle die in der Fördervereinbarung und den geltenden Vorschriften vorgesehenen Auflagen überprüft und ordnungsgemäß dokumentiert, insbesondere zu: Nutzung der Vorhaben und Erreichung der Ergebnisse; Öffentlichkeitsarbeit (Publizität); Zweckbindungsfrist; Instandhaltung?",
         [],
         ""),
        ("3.3.4", "KA4 BK4.3 und BK4.5 · Art. 74 CPR",
         "Hat die Verwaltungsbehörde / zwischengeschaltete Stelle die festgestellten Feststellungen / Empfehlungen ordnungsgemäß nachverfolgt?",
         [],
         ""),
        ("3.4", "Art. 74 CPR",
         "Haben die Prüfer, sofern zutreffend, Probleme festgestellt, die die ordnungsgemäße Durchführung des Vorhabens und/oder dessen Qualität beeinträchtigen?",
         [],
         ""),
    ]),
]

CONCLUSION = (
    "Schlussfolgerung: Entsprechen die Qualität und die Dauerhaftigkeit des "
    "Vorhabens den regulatorischen Anforderungen? Die Prüfer schließen, ob das "
    "Vorhaben den Qualitätsanforderungen entspricht, ob die Verwaltungsbehörde "
    "die Durchführung und Aufrechterhaltung der Investition ordnungsgemäß "
    "überwacht hat und ob die Dauerhaftigkeitsanforderungen — insbesondere die "
    "Zweckbindungsfrist nach Art. 65 CPR — eingehalten wurden."
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
                "Musterprüfcheckliste der Europäischen Kommission zur Qualität und "
                "Dauerhaftigkeit der Vorhaben, Förderperiode 2021-2027 — ins Deutsche "
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
                "kom_reference": "EC audit checklists 2021-2027 — Annex 1.8 (Quality of projects and durability)",
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
