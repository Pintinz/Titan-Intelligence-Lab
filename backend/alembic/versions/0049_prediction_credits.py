"""Add predictions.prediction_credits and predictions.prediction_reward_events —
TitanIQ Mobile V1's server-side prediction credit system (AdMob rewarded-video unlocks, no
billing this release). `modules.billing`'s existing Entitlement/UsageCounter pair was
considered and rejected as the backing store: it models a per-window quota that resets every
`window_key`, while this needs a persistent lifetime balance that only grows via a verified
rewarded-ad grant — a different shape, not a rewrite of billing's real, correct-for-its-purpose
model. `prediction_credits` holds one row per user (created lazily on first access, not via a
signup hook); `prediction_reward_events` is the reward ledger, with `provider_event_id`'s unique
constraint as the actual duplicate-reward-grant guard (Phase 5/6 of the shaped spec).

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-23
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.create_table(
        "prediction_credits",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.Uuid(), nullable=False, unique=True, index=True),
        sa.Column("available_predictions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_free_predictions_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewarded_predictions_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewarded_ads_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=PREDICTIONS,
    )
    op.create_table(
        "prediction_reward_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("reward_type", sa.String(64), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("provider_event_id", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="granted"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider_event_id", name="uq_prediction_reward_event_provider_event"),
        schema=PREDICTIONS,
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {PREDICTIONS}.prediction_credits ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {PREDICTIONS}.prediction_reward_events ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {PREDICTIONS}.prediction_reward_events DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {PREDICTIONS}.prediction_credits DISABLE ROW LEVEL SECURITY")
    op.drop_table("prediction_reward_events", schema=PREDICTIONS)
    op.drop_table("prediction_credits", schema=PREDICTIONS)
