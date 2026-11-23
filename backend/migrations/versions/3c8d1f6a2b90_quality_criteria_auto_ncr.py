# ruff: noqa: E501 - hand-written column lists
"""quality: acceptance criteria library, criterion and outcome columns on inspections, source data on issues

Revision ID: 3c8d1f6a2b90
Revises: fa7962ecb6f7
Create Date: 2026-11-23 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c8d1f6a2b90"
down_revision: str | Sequence[str] | None = "fa7962ecb6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('inspections_criteria',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('standards_ref', sa.String(length=200), nullable=True),
    sa.Column('discipline', sa.String(length=100), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('characteristic', sa.String(length=200), nullable=True),
    sa.Column('method', sa.String(length=200), nullable=True),
    sa.Column('unit', sa.String(length=30), nullable=True),
    sa.Column('rule_type', sa.String(length=12), nullable=False),
    sa.Column('nominal', sa.String(length=40), nullable=True),
    sa.Column('lower_limit', sa.String(length=40), nullable=True),
    sa.Column('upper_limit', sa.String(length=40), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('supplementary', sa.JSON(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_inspections_criteria_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inspections_criteria')),
    sa.UniqueConstraint('project_id', 'code', name='uq_inspections_criteria_code')
    )
    op.create_index(op.f('ix_inspections_criteria_project_id'), 'inspections_criteria', ['project_id'], unique=False)

    op.add_column('inspections', sa.Column('criterion_id', sa.Integer(), nullable=True))
    op.add_column('inspections', sa.Column('measured_value', sa.String(length=40), nullable=True))
    op.add_column('inspections', sa.Column('conditional', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('inspections', sa.Column('report_id', sa.Integer(), nullable=True))
    op.add_column('inspections', sa.Column('proposed_severity', sa.String(length=10), nullable=True))
    op.create_index(op.f('ix_inspections_criterion_id'), 'inspections', ['criterion_id'], unique=False)
    op.create_foreign_key(op.f('fk_inspections_criterion_id_inspections_criteria'), 'inspections', 'inspections_criteria', ['criterion_id'], ['id'], ondelete='RESTRICT')

    op.add_column('inspections_items', sa.Column('criterion_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_inspections_items_criterion_id'), 'inspections_items', ['criterion_id'], unique=False)
    op.create_foreign_key(op.f('fk_inspections_items_criterion_id_inspections_criteria'), 'inspections_items', 'inspections_criteria', ['criterion_id'], ['id'], ondelete='RESTRICT')

    op.add_column('inspections_settings', sa.Column('auto_report_on_failure', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('ncr_reports', sa.Column('source_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ncr_reports', 'source_data')
    op.drop_column('inspections_settings', 'auto_report_on_failure')

    op.drop_constraint(op.f('fk_inspections_items_criterion_id_inspections_criteria'), 'inspections_items', type_='foreignkey')
    op.drop_index(op.f('ix_inspections_items_criterion_id'), table_name='inspections_items')
    op.drop_column('inspections_items', 'criterion_id')

    op.drop_constraint(op.f('fk_inspections_criterion_id_inspections_criteria'), 'inspections', type_='foreignkey')
    op.drop_index(op.f('ix_inspections_criterion_id'), table_name='inspections')
    op.drop_column('inspections', 'proposed_severity')
    op.drop_column('inspections', 'report_id')
    op.drop_column('inspections', 'conditional')
    op.drop_column('inspections', 'measured_value')
    op.drop_column('inspections', 'criterion_id')

    op.drop_index(op.f('ix_inspections_criteria_project_id'), table_name='inspections_criteria')
    op.drop_table('inspections_criteria')
