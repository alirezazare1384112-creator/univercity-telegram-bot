"""add weekly_activities and calendar_events drift

Revision ID: d4e5f6a7b8c9
Revises: c2b3d4e5f6a7
Create Date: 2026-11-25 03:30:00.000000

Brings the migration history in sync with the models:
- ``weekly_activities``: new table for the Activity Room weekly planner.
- ``calendar_events.event_type`` + ``course_id``: columns added to the
  model in the calendar redesign (PR #24) but never captured here. The
  serverless ``create_all`` bootstrap already creates them in production;
  this migration exists so ``alembic check`` (CI) sees no drift.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c2b3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- weekly_activities (Activity Room planner) -----------------------
    op.create_table(
        'weekly_activities',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('duration_hours', sa.Float(), nullable=False),
        sa.Column('category', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            'day_of_week BETWEEN 1 AND 7',
            name='ck_weekly_activities_day_of_week',
        ),
        sa.CheckConstraint(
            'duration_hours > 0 AND duration_hours <= 24',
            name='ck_weekly_activities_duration',
        ),
        sa.CheckConstraint(
            "category IN ('STUDY','SPORT','REST','WORK','PERSONAL','OTHER')",
            name='ck_weekly_activities_category',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_weekly_activities_user_id', 'weekly_activities', ['user_id'], unique=False
    )
    op.create_index(
        'ix_weekly_activities_day', 'weekly_activities', ['day_of_week'], unique=False
    )

    # --- calendar_events drift (PR #24 model columns, never migrated) ------
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('event_type', sa.String(length=16), nullable=False)
        )
        batch_op.add_column(
            sa.Column('course_id', sa.BigInteger(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_calendar_events_course_id_courses',
            'courses',
            ['course_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_check_constraint(
            'ck_calendar_events_event_type',
            "event_type IN ('EXAM','QUIZ','ASSIGNMENT','PROJECT',"
            "'PRESENTATION','CLASS','TASK','OTHER')",
        )


def downgrade() -> None:
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.drop_constraint('ck_calendar_events_event_type', type_='check')
        batch_op.drop_constraint('fk_calendar_events_course_id_courses', type_='foreignkey')
        batch_op.drop_column('course_id')
        batch_op.drop_column('event_type')

    op.drop_index('ix_weekly_activities_day', table_name='weekly_activities')
    op.drop_index('ix_weekly_activities_user_id', table_name='weekly_activities')
    op.drop_table('weekly_activities')
