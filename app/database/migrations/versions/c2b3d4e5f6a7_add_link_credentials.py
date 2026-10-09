"""add link credentials

Revision ID: c2b3d4e5f6a7
Revises: f1a2c3d4e5f6
Create Date: 2026-10-10 13:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2b3d4e5f6a7'
down_revision: Union[str, None] = 'f1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Two nullable TEXT columns hold the AES-GCM ciphertext and the
    # master-key-wrapped data key. Both are NULL when the user has not
    # saved credentials for this link.
    with op.batch_alter_table('university_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ciphertext_b64', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('wrapped_key_b64', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('university_links', schema=None) as batch_op:
        batch_op.drop_column('wrapped_key_b64')
        batch_op.drop_column('ciphertext_b64')
