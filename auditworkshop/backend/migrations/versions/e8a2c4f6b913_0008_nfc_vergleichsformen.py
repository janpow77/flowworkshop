"""0008 Vergleichsformen: zerlegt geschriebene Zeichen per NFC zusammenführen

Nutzerentscheidung R2 vom 23.09.2026 („alle empfehlungen“, auditcore v0.3.0):
Zerlegt geschriebene Umlaute (u + Trema) werden vor der Normalisierung per NFC
zusammengeführt. Die Abfrageseite normalisiert seitdem über
``flowworkshop.sanctions`` 2026.09.3 (Sanktionsscreening) bzw.
``flowworkshop.state_aid`` 2026.09.2 (Beihilfen, Entitäten). Damit
persistierte Suchformen weiter exakt treffen, werden hier nur Zeilen neu
normalisiert, deren Name nicht bereits in NFC vorliegt – für alle übrigen
ändert sich die Vergleichsform nicht.

Die Profilversionen sind hier fest benannt, damit spätere Codeänderungen diese
Migration nicht verändern. Downgrade stellt die Formen der Vorgängerprofile
(2026.09.2 bzw. 2026.09.1) wieder her.

Revision ID: e8a2c4f6b913
Revises: c5f1a9d3e208
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from auditcore_entity_matching import load_profile, normalize

# revision identifiers, used by Alembic.
revision: str = 'e8a2c4f6b913'
down_revision: Union[str, None] = 'c5f1a9d3e208'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (Tabelle, Namensspalte, Suchformspalte, Profil, Version neu, Version alt, Länge)
_ZIELE = (
    ("workshop_sanctions_entries", "name", "name_normalized",
     "flowworkshop.sanctions", "2026.09.3", "2026.09.2", None),
    ("workshop_state_aid_awards", "beneficiary_name", "beneficiary_name_normalized",
     "flowworkshop.state_aid", "2026.09.2", "2026.09.1", 500),
    ("workshop_company_entities", "canonical_name", "canonical_name_normalized",
     "flowworkshop.state_aid", "2026.09.2", "2026.09.1", 500),
)


def _neu_normalisieren(neu: bool) -> None:
    bind = op.get_bind()
    inspektor = sa.inspect(bind)
    for tabelle, name, suchform, profil_id, v_neu, v_alt, laenge in _ZIELE:
        if not inspektor.has_table(tabelle):
            continue
        profil = load_profile(profil_id, v_neu if neu else v_alt)
        zeilen = bind.execute(
            sa.text(
                f"SELECT id, {name} FROM {tabelle} "
                f"WHERE {name} IS NOT NULL AND {name} <> normalize({name}, NFC)"
            )
        ).fetchall()
        for zeilen_id, wert in zeilen:
            form = normalize(wert, profil)
            if laenge:
                form = form[:laenge]
            bind.execute(
                sa.text(f"UPDATE {tabelle} SET {suchform} = :f WHERE id = :i"),
                {"f": form, "i": zeilen_id},
            )


def upgrade() -> None:
    _neu_normalisieren(neu=True)


def downgrade() -> None:
    _neu_normalisieren(neu=False)
