"""0006 pg_trgm-Extension

Legt die Extension ``pg_trgm`` in der Migrationskette an. Bisher wurde sie nur
beim App-Start in ``main.py`` erzeugt; Werkzeuge und Tests, die ausschließlich
``alembic upgrade head`` ausführen, hatten deshalb kein ``similarity()`` und
keine ``gin_trgm_ops``.

Downgrade entfernt die Extension bewusst NICHT: Sie ist datenbankweit, wird
von Trigram-Indizes (State Aid, Begünstigte, Sanktionen) und ggf. weiteren
Anwendungen in derselben Datenbank genutzt und war vor dieser Migration bereits
durch den App-Start vorhanden. Ein DROP würde fremde Indizes mitreißen.

Revision ID: b3d8e2f4a117
Revises: a7c2f5e9b310
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d8e2f4a117'
down_revision: Union[str, None] = 'a7c2f5e9b310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Absichtlich leer, siehe Modul-Docstring.
    pass
