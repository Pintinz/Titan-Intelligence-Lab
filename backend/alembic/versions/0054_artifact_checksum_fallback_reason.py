"""Add models.artifact_checksum and predictions.fallback_reason — forensic audit §3/§13/§15
Critical Fix #2/#3 (2026-08-25).

Two additive columns, same "nullable, never backfilled" posture as 0051/0053:

- `predictions.models.artifact_checksum` — sha256 hex digest of the exact bytes saved to
  `artifact_ref` at training time. `ModelLoaderService.load()` verifies a loaded artifact's actual
  hash against this column whenever it's set, raising `ArtifactIntegrityError` (which
  `PredictionEngine._resolve_predictor` treats as any other load failure — falls back safely,
  never breaks generation) on mismatch. `None` for any model registered before this column
  existed, or by a training path not yet updated to compute one — verification is simply skipped
  for those, never treated as itself a failure.

- `predictions.predictions.fallback_reason` — why `predictor_provenance` is "formula_fallback",
  when it is: NO_ARTIFACT_REGISTERED / ARTIFACT_LOAD_FAILURE / ARTIFACT_INTEGRITY_MISMATCH /
  ARTIFACT_DESERIALIZE_FAILURE / UNKNOWN_ARTIFACT_ERROR. `None` when no fallback occurred, or for
  predictions generated before this column existed — the same "never inferred after the fact"
  posture 0051/0053 already established for their own columns.

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column("artifact_checksum", sa.String(64), nullable=True),
        schema=PREDICTIONS,
    )
    op.add_column(
        "predictions",
        sa.Column("fallback_reason", sa.String(32), nullable=True),
        schema=PREDICTIONS,
    )


def downgrade() -> None:
    op.drop_column("predictions", "fallback_reason", schema=PREDICTIONS)
    op.drop_column("models", "artifact_checksum", schema=PREDICTIONS)
