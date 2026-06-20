"""0004 sanctions delisted tombstone

Fuegt der Sanktionslisten-Tabelle eine `delisted`-Spalte hinzu, damit der
Refresh de-gelistete Eintraege als Tombstone markieren kann (Befund S3:
entfernte Personen blieben dauerhaft als "gelistet"). Plus zusammengesetzter
Index (source_key, delisted) fuer den gefilterten Index-Rebuild.

Revision ID: d4e1b7c9a204
Revises: a66ba2c87daa
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e1b7c9a204'
down_revision: Union[str, None] = 'a66ba2c87daa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workshop_sanctions_entries',
        sa.Column('delisted', sa.Boolean(), server_default='false', nullable=False),
    )
    op.create_index(
        'ix_sanctions_source_delisted',
        'workshop_sanctions_entries',
        ['source_key', 'delisted'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_sanctions_source_delisted', table_name='workshop_sanctions_entries')
    op.drop_column('workshop_sanctions_entries', 'delisted')
