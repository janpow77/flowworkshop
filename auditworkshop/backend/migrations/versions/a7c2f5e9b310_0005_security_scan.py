"""0005 security scan runs

Tabelle workshop_security_scan_runs für die nicht-intrusive Webseiten-
Sicherheitsprüfung (Kernanforderung 6 — ISMS-Systemprüfung).

Revision ID: a7c2f5e9b310
Revises: d4e1b7c9a204
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7c2f5e9b310'
down_revision: Union[str, None] = 'd4e1b7c9a204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workshop_security_scan_runs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('scan_id', sa.String(length=36), nullable=False),
        sa.Column('target_url', sa.String(length=2000), nullable=False),
        sa.Column('target_host', sa.String(length=255), nullable=True),
        sa.Column('triggered_by', sa.String(length=80), nullable=False),
        sa.Column('authorization_confirmed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('authorization_declared_by', sa.String(length=255), nullable=True),
        sa.Column('authorization_text', sa.Text(), nullable=True),
        sa.Column('authorized_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('count_konform', sa.Integer(), server_default='0', nullable=False),
        sa.Column('count_gelb', sa.Integer(), server_default='0', nullable=False),
        sa.Column('count_rot', sa.Integer(), server_default='0', nullable=False),
        sa.Column('count_grau', sa.Integer(), server_default='0', nullable=False),
        sa.Column('overall', sa.String(length=16), nullable=True),
        sa.Column('findings', sa.JSON(), nullable=True),
        sa.Column('observed', sa.JSON(), nullable=True),
        sa.Column('screenshot_path', sa.String(length=500), nullable=True),
        sa.Column('architecture_path', sa.String(length=500), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scan_id', name='uq_security_scan_id'),
    )
    op.create_index('ix_security_scan_scan_id', 'workshop_security_scan_runs', ['scan_id'])
    op.create_index('ix_security_scan_started_at', 'workshop_security_scan_runs', ['started_at'])
    op.create_index('ix_security_scan_triggered_by', 'workshop_security_scan_runs', ['triggered_by'])


def downgrade() -> None:
    op.drop_index('ix_security_scan_triggered_by', table_name='workshop_security_scan_runs')
    op.drop_index('ix_security_scan_started_at', table_name='workshop_security_scan_runs')
    op.drop_index('ix_security_scan_scan_id', table_name='workshop_security_scan_runs')
    op.drop_table('workshop_security_scan_runs')
