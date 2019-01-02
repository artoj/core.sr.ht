"""Remove nullable constraint from revocation token

Revision ID: 5a62c0c174fd
Revises: af06063a0edd
Create Date: 2019-01-02 11:09:44.745902

"""

# revision identifiers, used by Alembic.
revision = '5a62c0c174fd'
down_revision = 'af06063a0edd'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column("user", "oauth_revocation_token", nullable=True)


def downgrade():
    op.alter_column("user", "oauth_revocation_token", nullable=False)
