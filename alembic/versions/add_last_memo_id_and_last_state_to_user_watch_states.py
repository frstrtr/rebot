"""
Alembic migration to add last_memo_id (Integer, nullable) and last_state (Text, nullable) columns to user_watch_states table.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_last_memo_id_and_last_state_to_user_watch_states'
down_revision = None  # Set this to the previous revision if you have one
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_watch_states', sa.Column('last_memo_id', sa.Integer(), nullable=True))
    op.add_column('user_watch_states', sa.Column('last_state', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('user_watch_states', 'last_state')
    op.drop_column('user_watch_states', 'last_memo_id')
