"""Add unique constraint to username

Revision ID: 0417a58bdaad
Revises: 4cba8deffa67
Create Date: 2020-01-04 13:58:04.314245

"""

# revision identifiers, used by Alembic.
revision = '0417a58bdaad'
down_revision = '4cba8deffa67'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_unique_constraint("user_username_unique", "user", ["username"])


def downgrade():
    op.drop_constraint("user_username_unique", "user")
