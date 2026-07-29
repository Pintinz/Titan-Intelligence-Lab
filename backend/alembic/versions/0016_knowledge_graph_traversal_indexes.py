"""Knowledge Graph traversal indexes — Milestone 7 Graph Performance ("Optimize for
Indexing... Traversal Speed"). `kg_edges` already has single-column indexes on
``from_node_id``/``to_node_id``/``edge_type`` (migration 0008) and ``valid_to`` (migration
0015), but `GraphQueryService.touching_edges`/`traverse` filter on (node, edge_type) together —
a composite index serves that combined filter directly instead of relying on the query planner
to intersect two single-column indexes. Pure index additions: no column/data changes, safe to
run on every dialect.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SCHEMA = "knowledge_graph"


def upgrade() -> None:
    op.create_index(
        "ix_kg_edges_from_node_edge_type", "kg_edges", ["from_node_id", "edge_type"], unique=False, schema=SCHEMA
    )
    op.create_index(
        "ix_kg_edges_to_node_edge_type", "kg_edges", ["to_node_id", "edge_type"], unique=False, schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_kg_edges_to_node_edge_type", table_name="kg_edges", schema=SCHEMA)
    op.drop_index("ix_kg_edges_from_node_edge_type", table_name="kg_edges", schema=SCHEMA)
