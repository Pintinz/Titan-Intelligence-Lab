"""Knowledge Graph ontology metadata columns — Milestone 7 (Sports Semantic Intelligence
Platform). Additive only: every new column is nullable or carries a default, so existing
``kg_nodes``/``kg_edges`` rows and every existing ``KnowledgeGraphPopulationService.populate_*``
call site continue to work unchanged (docs/decisions.md — see the new ADR for this milestone).

Runs on every dialect (unlike the Postgres-only RLS/Storage/Realtime migrations 0010-0014) —
these are plain ``ADD COLUMN`` statements the SQLite fast-test engine handles identically.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

SCHEMA = "knowledge_graph"


def upgrade() -> None:
    with op.batch_alter_table("kg_nodes", schema=SCHEMA) as batch_op:
        batch_op.add_column(sa.Column("provider_refs", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("source", sa.String(64), nullable=False, server_default="ingestion"))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("status", sa.String(16), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("merged_into", sa.String(64), nullable=True))
    op.create_index("ix_kg_nodes_status", "kg_nodes", ["status"], unique=False, schema=SCHEMA)
    op.create_index("ix_kg_nodes_merged_into", "kg_nodes", ["merged_into"], unique=False, schema=SCHEMA)

    with op.batch_alter_table("kg_edges", schema=SCHEMA) as batch_op:
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"))
        batch_op.add_column(sa.Column("source", sa.String(64), nullable=False, server_default="ingestion"))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("directed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_kg_edges_valid_to", "kg_edges", ["valid_to"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_kg_edges_valid_to", table_name="kg_edges", schema=SCHEMA)
    with op.batch_alter_table("kg_edges", schema=SCHEMA) as batch_op:
        batch_op.drop_column("directed")
        batch_op.drop_column("version")
        batch_op.drop_column("source")
        batch_op.drop_column("confidence")

    op.drop_index("ix_kg_nodes_merged_into", table_name="kg_nodes", schema=SCHEMA)
    op.drop_index("ix_kg_nodes_status", table_name="kg_nodes", schema=SCHEMA)
    with op.batch_alter_table("kg_nodes", schema=SCHEMA) as batch_op:
        batch_op.drop_column("merged_into")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("confidence")
        batch_op.drop_column("status")
        batch_op.drop_column("version")
        batch_op.drop_column("source")
        batch_op.drop_column("aliases")
        batch_op.drop_column("provider_refs")
