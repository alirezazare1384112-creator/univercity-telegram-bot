"""add user photo_url

Revision ID: f1a2c3d4e5f6
Revises: 69b68d48fda1
Create Date: 2026-10-10 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2c3d4e5f6'
down_revision: Union[str, None] = '69b68d48fda1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the photo_url column to the users table.
    # Telegram sends this URL inside the signed initData payload, so it is
    # safe to trust and store. Null when the user has no profile photo.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('photo_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('photo_url')
