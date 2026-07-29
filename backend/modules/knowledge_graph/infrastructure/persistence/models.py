"""SQLAlchemy models for the `knowledge_graph` schema (docs/database_schema.md §5).

Milestone 7 adds entity/edge metadata columns (see domain/entities.py docstring) using
client-side Python defaults (``default=``, not ``server_default=``) — deliberately, to avoid
the async-refresh-after-flush pitfall documented in docs/decisions.md (a ``server_default``
column is marked "expired" after INSERT and needs an explicit ``session.refresh()`` before the
mapper can safely read it back; a client-side default is already set on the Python object,
sidestepping the issue entirely, consistent with every other column already on these models).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="knowledge_graph")


class Base(DeclarativeBase):
    metadata = metadata


class KGNodeModel(Base):
    __tablename__ = "kg_nodes"
    __table_args__ = (UniqueConstraint("node_type", "entity_ref", name="uq_kg_node_type_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_ref: Mapped[str] = mapped_column(String(128), index=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(64), default="ingestion")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_into: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class KGEdgeModel(Base):
    __tablename__ = "kg_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kg_nodes.id"), index=True)
    to_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kg_nodes.id"), index=True)
    edge_type: Mapped[str] = mapped_column(String(32), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(64), default="ingestion")
    version: Mapped[int] = mapped_column(Integer, default=1)
    directed: Mapped[bool] = mapped_column(Boolean, default=True)
