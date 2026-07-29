"""Knowledge Graph schema — kg_nodes, kg_edges (docs/knowledge_graph.md §2-3,
docs/database_schema.md §5, docs/decisions.md ADR-005)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SCHEMA = "knowledge_graph"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "kg_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("node_type", sa.String(32), nullable=False, index=True),
        sa.Column("entity_ref", sa.String(128), nullable=False, index=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("node_type", "entity_ref", name="uq_kg_node_type_ref"),
        schema=SCHEMA,
    )

    op.create_table(
        "kg_edges",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("from_node_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.kg_nodes.id"), nullable=False, index=True),
        sa.Column("to_node_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.kg_nodes.id"), nullable=False, index=True),
        sa.Column("edge_type", sa.String(32), nullable=False, index=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("kg_edges", schema=SCHEMA)
    op.drop_table("kg_nodes", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
