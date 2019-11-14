"""Add index for usernames

Revision ID: c19c3956974d
Revises: fb50c54ea20e
Create Date: 2019-11-14 15:46:47.106805

"""

# revision identifiers, used by Alembic.
revision = 'c19c3956974d'
down_revision = 'fb50c54ea20e'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_index('ix_user_username', 'user', ['username'])


def downgrade():
    op.drop_index('ix_user_username')
