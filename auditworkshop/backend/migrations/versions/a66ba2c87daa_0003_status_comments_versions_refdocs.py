"""0003 status comments versions refdocs

Revision ID: a66ba2c87daa
Revises: f14eb310648f
Create Date: 2026-05-24 14:58:27.637581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a66ba2c87daa'
down_revision: Union[str, None] = 'f14eb310648f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Migration 0003: status/current_version + Kommentare, Versionen, RefDocs ###
    op.create_table('workshop_checklist_note_reads',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('node_id', sa.String(length=36), nullable=False),
    sa.Column('comment_id', sa.String(length=36), nullable=False),
    sa.Column('read_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'comment_id', name='uq_cl_note_read')
    )
    op.create_index(op.f('ix_workshop_checklist_note_reads_comment_id'), 'workshop_checklist_note_reads', ['comment_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_note_reads_node_id'), 'workshop_checklist_note_reads', ['node_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_note_reads_template_id'), 'workshop_checklist_note_reads', ['template_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_note_reads_user_id'), 'workshop_checklist_note_reads', ['user_id'], unique=False)
    op.create_table('workshop_checklist_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('version_number', sa.String(length=40), nullable=False),
    sa.Column('is_frozen', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
    sa.Column('tree_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by_id', sa.String(length=36), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['workshop_checklist_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workshop_checklist_versions_template_id'), 'workshop_checklist_versions', ['template_id'], unique=False)
    op.create_table('workshop_checklist_node_comments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('node_id', sa.String(length=36), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('parent_comment_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('edited_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['workshop_registrations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['node_id'], ['workshop_checklist_nodes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['workshop_checklist_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workshop_checklist_node_comments_author_id'), 'workshop_checklist_node_comments', ['author_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_node_comments_node_id'), 'workshop_checklist_node_comments', ['node_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_node_comments_parent_comment_id'), 'workshop_checklist_node_comments', ['parent_comment_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_node_comments_template_id'), 'workshop_checklist_node_comments', ['template_id'], unique=False)
    op.create_table('workshop_checklist_node_refdocs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('node_id', sa.String(length=36), nullable=False),
    sa.Column('document_name', sa.String(length=255), nullable=False),
    sa.Column('document_path', sa.String(length=500), nullable=True),
    sa.Column('reference_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['node_id'], ['workshop_checklist_nodes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workshop_checklist_node_refdocs_node_id'), 'workshop_checklist_node_refdocs', ['node_id'], unique=False)
    op.create_index(op.f('ix_workshop_checklist_node_refdocs_template_id'), 'workshop_checklist_node_refdocs', ['template_id'], unique=False)
    op.add_column('workshop_checklist_nodes', sa.Column('status', sa.String(length=16), server_default='pending', nullable=False))
    op.add_column('workshop_checklist_templates', sa.Column('current_version', sa.String(length=40), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('workshop_checklist_templates', 'current_version')
    op.drop_column('workshop_checklist_nodes', 'status')
    op.drop_index(op.f('ix_workshop_checklist_node_refdocs_template_id'), table_name='workshop_checklist_node_refdocs')
    op.drop_index(op.f('ix_workshop_checklist_node_refdocs_node_id'), table_name='workshop_checklist_node_refdocs')
    op.drop_table('workshop_checklist_node_refdocs')
    op.drop_index(op.f('ix_workshop_checklist_node_comments_template_id'), table_name='workshop_checklist_node_comments')
    op.drop_index(op.f('ix_workshop_checklist_node_comments_parent_comment_id'), table_name='workshop_checklist_node_comments')
    op.drop_index(op.f('ix_workshop_checklist_node_comments_node_id'), table_name='workshop_checklist_node_comments')
    op.drop_index(op.f('ix_workshop_checklist_node_comments_author_id'), table_name='workshop_checklist_node_comments')
    op.drop_table('workshop_checklist_node_comments')
    op.drop_index(op.f('ix_workshop_checklist_versions_template_id'), table_name='workshop_checklist_versions')
    op.drop_table('workshop_checklist_versions')
    op.drop_index(op.f('ix_workshop_checklist_note_reads_user_id'), table_name='workshop_checklist_note_reads')
    op.drop_index(op.f('ix_workshop_checklist_note_reads_template_id'), table_name='workshop_checklist_note_reads')
    op.drop_index(op.f('ix_workshop_checklist_note_reads_node_id'), table_name='workshop_checklist_note_reads')
    op.drop_index(op.f('ix_workshop_checklist_note_reads_comment_id'), table_name='workshop_checklist_note_reads')
    op.drop_table('workshop_checklist_note_reads')
    # ### end Alembic commands ###
