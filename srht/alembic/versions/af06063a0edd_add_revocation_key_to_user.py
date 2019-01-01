"""Add revocation key to user

Revision ID: af06063a0edd
Revises: None
Create Date: 2019-01-01 09:33:41.320515

"""

# revision identifiers, used by Alembic.
revision = 'af06063a0edd'
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("user", sa.Column("oauth_revocation_token",
        sa.String(256), nullable=False, server_default="default_token"))
    op.alter_column("user", "oauth_revocation_token", server_default=None)


def downgrade():
    op.drop_column("user", "oauth_revocation_token")
