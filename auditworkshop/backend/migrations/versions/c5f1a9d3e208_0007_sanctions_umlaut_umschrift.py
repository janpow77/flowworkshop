"""0007 Sanktionen: Umlaute in name_normalized umschreiben

Nutzerentscheidung 2026-09-23 („mueller wenn es kein umlaut gibt“): Das
Sanktionsscreening vergleicht deutsche Umlaute künftig umgeschrieben
(Müller → mueller statt muller). Die Abfrageseite normalisiert über
``services.sanctions_service.normalize_name``; damit alte, persistierte Werte
weiterhin treffen, werden alle Einträge mit Umlaut oder ß im Namen hier mit
derselben Regel neu normalisiert. Die Regel ist hier bewusst eingefroren
(Tabelle + Bibliotheksprofil ``flowworkshop.sanctions``), damit spätere
Codeänderungen diese Migration nicht verändern.

Downgrade stellt die frühere Form (Umlaut gefaltet, Müller → muller) wieder her.

Revision ID: c5f1a9d3e208
Revises: b3d8e2f4a117
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from auditcore_entity_matching import legacy as _bibliothek

# revision identifiers, used by Alembic.
revision: str = 'c5f1a9d3e208'
down_revision: Union[str, None] = 'b3d8e2f4a117'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UMSCHRIFT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "ẞ": "SS"}
)
_BETROFFEN = "name ~ '[äöüÄÖÜßẞ]'"


def _neu_normalisieren(umschreiben: bool) -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("workshop_sanctions_entries"):
        return
    rows = bind.execute(
        sa.text(f"SELECT id, name FROM workshop_sanctions_entries WHERE {_BETROFFEN}")
    ).fetchall()
    for row_id, name in rows:
        text = name.translate(_UMSCHRIFT) if umschreiben else name
        bind.execute(
            sa.text("UPDATE workshop_sanctions_entries SET name_normalized = :n WHERE id = :i"),
            {"n": _bibliothek.flowworkshop_normalize_name(text), "i": row_id},
        )


def upgrade() -> None:
    _neu_normalisieren(umschreiben=True)


def downgrade() -> None:
    _neu_normalisieren(umschreiben=False)
