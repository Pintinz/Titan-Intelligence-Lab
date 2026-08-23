"""Add the model-artifacts Supabase Storage bucket.

Backs `SupabaseStorageArtifactStore` (modules/predictions/infrastructure/ml/
supabase_artifact_store.py) — the durable replacement for `LocalFilesystemArtifactStore`, whose
own docstring already labeled it "the dev/offline-test adapter" but was, until this fix, wired
into production too (composition.py), silently losing every trained model's artifact on each
deploy since the container's local disk doesn't survive one.

Unlike migration 0013's PUBLIC_BUCKETS/PRIVATE_BUCKETS (avatars, ai-reports, etc.), this bucket
has no individual end-user owner — it's backend-owned system data written only via the service
role key (bypasses RLS entirely), so no per-user `(storage.foldername(name))[1] = auth.uid()`
policy applies here. No RLS policy is added at all: with RLS enabled and zero policies, the table
default-denies every request through the anon/authenticated key paths, while the service role key
bypasses RLS unconditionally — exactly "backend-only access, closed to everyone else."

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-23
"""

from __future__ import annotations

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_BUCKET_ID = "model-artifacts"
_SIZE_LIMIT = 104857600  # 100 MiB — generous headroom over any real serialized sklearn/boosting artifact


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        f"VALUES ('{_BUCKET_ID}', '{_BUCKET_ID}', false, {_SIZE_LIMIT}, NULL) "
        f"ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DELETE FROM storage.objects WHERE bucket_id = '{_BUCKET_ID}'")
    op.execute(f"DELETE FROM storage.buckets WHERE id = '{_BUCKET_ID}'")
