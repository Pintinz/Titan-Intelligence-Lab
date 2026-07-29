"""Intelligence platform schema — News Intelligence & Community Intelligence (Milestone 8,
docs/news_intelligence.md, docs/community_intelligence.md, docs/decisions.md ADR-036+).

Runs on every dialect (like migration 0015/0016) — plain CREATE TABLE/INDEX statements the
SQLite fast-test engine handles identically; the fast test suite itself builds these tables via
``Base.metadata.create_all`` rather than running this migration, so this file is exercised
against live Postgres only (docs/decisions.md ADR-024's offline-SQL + MCP `execute_sql`
application pattern).

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-26
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

SCHEMA = "intelligence"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "news_sources",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("source_type", sa.String(32), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True, index=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publisher_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.news_sources.id"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active", index=True),
        schema=SCHEMA,
    )

    op.create_table(
        "news_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.news_sources.id"), nullable=False, index=True),
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.news_articles.id"), nullable=False, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("affected_entity_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("kg_edge_ids", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )

    op.create_table(
        "source_reliability_scores",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.news_sources.id"), nullable=False, unique=True, index=True
        ),
        sa.Column("reliability_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("historical_accuracy", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("bias_rating", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("verification_status", sa.String(16), nullable=False, server_default="unverified"),
        sa.Column("trust_level", sa.String(16), nullable=False, server_default="unverified"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "sentiment_results",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("target_entity_ref", sa.String(128), nullable=False, index=True),
        sa.Column("target_entity_type", sa.String(32), nullable=False),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("momentum", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("source_ref", sa.String(64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "impact_scores",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "news_event_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.news_events.id"), nullable=False, unique=True, index=True
        ),
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("factors", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("affected_teams", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("affected_players", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("affected_competitions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "summaries",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("summary_type", sa.String(32), nullable=False, index=True),
        sa.Column("subject_ref", sa.String(128), nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_article_ids", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )

    op.create_table(
        "community_posts",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("platform", sa.String(32), nullable=False, index=True),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("author_ref", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credibility_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.UniqueConstraint("platform", "external_id", name="uq_community_post_platform_ref"),
        schema=SCHEMA,
    )

    op.create_table(
        "community_topics",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("platform", sa.String(32), nullable=False, index=True),
        sa.Column("topic_label", sa.String(200), nullable=False),
        sa.Column("related_entity_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("post_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("momentum", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("platform", "topic_label", name="uq_community_topic_platform_label"),
        schema=SCHEMA,
    )

    op.create_table(
        "intelligence_sync_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("channel_type", sa.String(16), nullable=False, index=True),
        sa.Column("channel_key", sa.String(200), nullable=False, index=True),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "intelligence_sync_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("channel_type", sa.String(16), nullable=False, index=True),
        sa.Column("channel_key", sa.String(200), nullable=False, index=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor", sa.String(500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("channel_type", "channel_key", name="uq_intelligence_checkpoint_channel"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "intelligence_sync_checkpoints",
        "intelligence_sync_runs",
        "community_topics",
        "community_posts",
        "summaries",
        "impact_scores",
        "sentiment_results",
        "source_reliability_scores",
        "news_events",
        "news_articles",
        "news_sources",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
