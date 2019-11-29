"""Allow external users to have null oauthtoken

Revision ID: 4cba8deffa67
Revises: c19c3956974d
Create Date: 2019-11-29 15:00:42.770643

"""

# revision identifiers, used by Alembic.
revision = '4cba8deffa67'
down_revision = 'c19c3956974d'

from alembic import context, op
import sqlalchemy as sa


def upgrade():
    transaction = context.get_bind().begin()
    try:
        op.alter_column("user", "oauth_token", nullable=True)
        op.alter_column("user", "oauth_token_expires", nullable=True)
        op.alter_column("user", "oauth_token_scopes", nullable=True)
        transaction.commit()
    except:
        # meta.sr.ht does not have these columns
        transaction.rollback()


def downgrade():
    transaction = context.get_bind().begin()
    try:
        op.alter_column("user", "oauth_token", nullable=False)
        op.alter_column("user", "oauth_token_expires", nullable=False)
        op.alter_column("user", "oauth_token_scopes", nullable=False)
        transaction.commit()
    except:
        # meta.sr.ht does not have these columns
        transaction.rollback()
