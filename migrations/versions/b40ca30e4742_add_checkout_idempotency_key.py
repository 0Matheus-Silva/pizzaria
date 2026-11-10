"""add checkout idempotency key

Revision ID: b40ca30e4742
Revises: 615cc6990407
Create Date: 2026-10-21 21:34:14.271946

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b40ca30e4742'
down_revision = '615cc6990407'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('checkout_key', sa.String(length=64), nullable=True))
    op.execute("UPDATE orders SET checkout_key = public_id WHERE checkout_key IS NULL")
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.alter_column('checkout_key', existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index('uq_orders_checkout_key', ['checkout_key'], unique=True)


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('uq_orders_checkout_key')
        batch_op.drop_column('checkout_key')
