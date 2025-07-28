"""Merge multiple heads

Revision ID: 9875b5577c20
Revises: add_last_memo_id_and_last_state_to_user_watch_states, c7dc2f1e8518
Create Date: 2025-07-28 13:11:39.461929

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9875b5577c20'
down_revision: Union[str, None] = ('add_last_memo_id_and_last_state_to_user_watch_states', 'c7dc2f1e8518')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
