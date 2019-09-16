"""Add suspension_notice to user

Revision ID: fb50c54ea20e
Revises: 5a62c0c174fd
Create Date: 2019-09-16 10:25:44.826419

"""

# revision identifiers, used by Alembic.
revision = 'fb50c54ea20e'
down_revision = '5a62c0c174fd'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('user', sa.Column('suspension_notice', sa.Unicode(4096)))


def downgrade():
    op.drop_column('user', 'suspension_notice')
