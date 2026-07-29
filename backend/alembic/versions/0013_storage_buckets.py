"""Supabase Storage buckets + secure upload policies (docs/security.md, Milestone 6).

Bucket design (path convention ``{bucket}/{owner_id}/filename`` — the standard Supabase pattern
of using the first path segment as the ownership key, checked via
``(storage.foldername(name))[1] = auth.uid()::text``):

  - avatars, team-logos, competition-logos: PUBLIC read (displayed throughout the UI to any
    visitor). avatars are user-owned (self-upload/replace/delete); team-logos/competition-logos
    are catalog assets with no individual owner, so writes are administrator+ only — same
    "read broadly, write narrowly through a role gate" shape as the DB-level RLS design in
    migration 0011. Moderators additionally get DELETE on avatars for content moderation
    (removing an inappropriate profile picture) without needing full administrator rights.
  - ai-reports, generated-charts, uploads, temporary-files: PRIVATE, owner-scoped
    (SELECT/INSERT own folder only), with administrator+ SELECT for support/debugging — mirrors
    the billing.subscriptions "own or analyst+" shape, just at the administrator threshold
    since these can contain personal generated content.

No bucket grants unrestricted anon/authenticated write to someone else's folder under any
circumstance — every write policy that isn't public-read-only checks the folder-owner match.

Postgres-only, same dialect-guard rationale as 0010-0012 (SQLite has no ``storage`` schema).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_PUBLIC_BUCKETS = [
    ("avatars", 5242880, ["image/png", "image/jpeg", "image/webp", "image/gif"]),
    ("team-logos", 5242880, ["image/png", "image/jpeg", "image/webp", "image/svg+xml"]),
    ("competition-logos", 5242880, ["image/png", "image/jpeg", "image/webp", "image/svg+xml"]),
]

_PRIVATE_BUCKETS = [
    ("ai-reports", 20971520, ["application/pdf", "image/png", "image/jpeg"]),
    ("generated-charts", 20971520, ["image/png", "image/svg+xml", "application/pdf"]),
    ("uploads", 26214400, ["application/pdf", "image/png", "image/jpeg", "image/webp", "text/csv"]),
    ("temporary-files", 52428800, None),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for bucket_id, size_limit, mime_types in _PUBLIC_BUCKETS:
        mime_sql = "NULL" if mime_types is None else "ARRAY[" + ",".join(f"'{m}'" for m in mime_types) + "]::text[]"
        op.execute(
            f"INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
            f"VALUES ('{bucket_id}', '{bucket_id}', true, {size_limit}, {mime_sql}) "
            f"ON CONFLICT (id) DO NOTHING"
        )

    for bucket_id, size_limit, mime_types in _PRIVATE_BUCKETS:
        mime_sql = "NULL" if mime_types is None else "ARRAY[" + ",".join(f"'{m}'" for m in mime_types) + "]::text[]"
        op.execute(
            f"INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
            f"VALUES ('{bucket_id}', '{bucket_id}', false, {size_limit}, {mime_sql}) "
            f"ON CONFLICT (id) DO NOTHING"
        )

    # -- avatars: public read, owner write, moderator+ delete (moderation) ---------------------
    op.execute(
        "CREATE POLICY avatars_public_read ON storage.objects FOR SELECT "
        "USING (bucket_id = 'avatars')"
    )
    op.execute(
        "CREATE POLICY avatars_owner_insert ON storage.objects FOR INSERT "
        "WITH CHECK (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text)"
    )
    op.execute(
        "CREATE POLICY avatars_owner_update ON storage.objects FOR UPDATE "
        "USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text) "
        "WITH CHECK (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text)"
    )
    op.execute(
        "CREATE POLICY avatars_owner_delete ON storage.objects FOR DELETE "
        "USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text)"
    )
    op.execute(
        "CREATE POLICY avatars_moderator_delete ON storage.objects FOR DELETE "
        "USING (bucket_id = 'avatars' AND identity.has_role_at_least('moderator'))"
    )

    # -- team-logos / competition-logos: public read, administrator+ write ---------------------
    for bucket_id in ("team-logos", "competition-logos"):
        op.execute(
            f"CREATE POLICY {bucket_id.replace('-', '_')}_public_read ON storage.objects FOR SELECT "
            f"USING (bucket_id = '{bucket_id}')"
        )
        op.execute(
            f"CREATE POLICY {bucket_id.replace('-', '_')}_admin_write ON storage.objects FOR ALL "
            f"USING (bucket_id = '{bucket_id}' AND identity.has_role_at_least('administrator')) "
            f"WITH CHECK (bucket_id = '{bucket_id}' AND identity.has_role_at_least('administrator'))"
        )

    # -- ai-reports / generated-charts / uploads / temporary-files: private, owner-scoped ------
    for bucket_id, _size, _mime in _PRIVATE_BUCKETS:
        policy_prefix = bucket_id.replace("-", "_")
        op.execute(
            f"CREATE POLICY {policy_prefix}_owner_select ON storage.objects FOR SELECT "
            f"USING (bucket_id = '{bucket_id}' AND (storage.foldername(name))[1] = auth.uid()::text)"
        )
        op.execute(
            f"CREATE POLICY {policy_prefix}_owner_insert ON storage.objects FOR INSERT "
            f"WITH CHECK (bucket_id = '{bucket_id}' AND (storage.foldername(name))[1] = auth.uid()::text)"
        )
        op.execute(
            f"CREATE POLICY {policy_prefix}_owner_delete ON storage.objects FOR DELETE "
            f"USING (bucket_id = '{bucket_id}' AND (storage.foldername(name))[1] = auth.uid()::text)"
        )
        op.execute(
            f"CREATE POLICY {policy_prefix}_admin_select ON storage.objects FOR SELECT "
            f"USING (bucket_id = '{bucket_id}' AND identity.has_role_at_least('administrator'))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    all_buckets = [b for b, _, _ in _PUBLIC_BUCKETS] + [b for b, _, _ in _PRIVATE_BUCKETS]
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN SELECT policyname FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects'
            LOOP
                IF r.policyname LIKE 'avatars_%' OR r.policyname LIKE 'team_logos_%'
                   OR r.policyname LIKE 'competition_logos_%' OR r.policyname LIKE 'ai_reports_%'
                   OR r.policyname LIKE 'generated_charts_%' OR r.policyname LIKE 'uploads_%'
                   OR r.policyname LIKE 'temporary_files_%'
                THEN
                    EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', r.policyname);
                END IF;
            END LOOP;
        END $$;
        """
    )
    for bucket_id in all_buckets:
        op.execute(f"DELETE FROM storage.objects WHERE bucket_id = '{bucket_id}'")
        op.execute(f"DELETE FROM storage.buckets WHERE id = '{bucket_id}'")
