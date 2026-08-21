"""Checkout flow — pending checkouts and inbound-webhook idempotency (Milestone 6 follow-on,
Flutterwave V4 payment integration).

``pending_checkouts`` correlates a provider charge reference to what should happen once the
webhook confirms payment — the checkout endpoint's synchronous response is never trusted to
activate a subscription (docs constitution). ``processed_payment_events`` makes webhook
processing idempotent: the same event id can never be applied twice, regardless of how many
times the provider redelivers it.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-20
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

BILLING = "billing"


def upgrade() -> None:
    op.create_table(
        "pending_checkouts",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("reference", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False, index=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey(f"{BILLING}.plans.id"), nullable=False),
        sa.Column("provider_charge_id", sa.String(64), nullable=True, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema=BILLING,
    )

    op.create_table(
        "processed_payment_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider", sa.String(32), nullable=False, index=True),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_processed_payment_event"),
        schema=BILLING,
    )


def downgrade() -> None:
    op.drop_table("processed_payment_events", schema=BILLING)
    op.drop_table("pending_checkouts", schema=BILLING)
