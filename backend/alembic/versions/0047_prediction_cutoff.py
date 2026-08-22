"""Add predictions.predictions.prediction_cutoff — the persisted leakage boundary.

Closes a real gap found auditing the Premier League data-enrichment work: live prediction
generation already threads a `now` cutoff through evidence-gathering (news/injuries/transfers get
rejected past it), and a point-in-time-safe feature read path (`FeatureValueRepositoryPort.
get_as_of`) already existed and was already tested — but `PredictionContextBuilder.build` called
`get_latest()` instead, and nothing on `Prediction` itself recorded what cutoff a live generation
actually used. `modules/predictions/application/prediction_context_builder.py` now calls
`get_as_of(now)`; this migration adds the column that pins the record of that boundary.

Backfilled from `generated_at` for existing rows — every prior live-generated prediction always
used `generated_at` as its (unenforced) cutoff, so this is the accurate historical value, not a
placeholder.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("prediction_cutoff", sa.DateTime(timezone=True), nullable=True),
        schema=PREDICTIONS,
    )
    op.execute(
        f"UPDATE {PREDICTIONS}.predictions SET prediction_cutoff = generated_at "
        f"WHERE generated_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("predictions", "prediction_cutoff", schema=PREDICTIONS)
