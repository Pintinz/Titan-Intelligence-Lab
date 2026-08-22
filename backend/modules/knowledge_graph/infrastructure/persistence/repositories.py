from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence import mappers
from modules.knowledge_graph.infrastructure.persistence.models import KGEdgeModel, KGNodeModel


@dataclass
class SqlAlchemyKGNodeRepository:
    session: AsyncSession

    async def get(self, node_id: KGNodeId) -> KGNode | None:
        model = await self.session.get(KGNodeModel, node_id.value)
        return mappers.node_to_domain(model) if model else None

    async def get_by_entity_ref(self, node_type: NodeType, entity_ref: str) -> KGNode | None:
        stmt = select(KGNodeModel).where(KGNodeModel.node_type == node_type.value, KGNodeModel.entity_ref == entity_ref)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.node_to_domain(model) if model else None

    async def list_by_type(self, node_type: NodeType) -> list[KGNode]:
        stmt = select(KGNodeModel).where(KGNodeModel.node_type == node_type.value)
        result = await self.session.execute(stmt)
        return [mappers.node_to_domain(row) for row in result.scalars().all()]

    async def count_by_type(self, node_type: NodeType) -> int:
        stmt = select(func.count()).select_from(KGNodeModel).where(KGNodeModel.node_type == node_type.value)
        return (await self.session.execute(stmt)).scalar_one()

    async def upsert(self, node: KGNode) -> KGNode:
        existing = await self.session.get(KGNodeModel, node.id.value)
        model = mappers.node_to_model(node, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.node_to_domain(model)


@dataclass
class SqlAlchemyKGEdgeRepository:
    session: AsyncSession

    async def get_current(self, from_node_id: KGNodeId, to_node_id: KGNodeId, edge_type: EdgeType) -> KGEdge | None:
        stmt = select(KGEdgeModel).where(
            KGEdgeModel.from_node_id == from_node_id.value,
            KGEdgeModel.to_node_id == to_node_id.value,
            KGEdgeModel.edge_type == edge_type.value,
            KGEdgeModel.valid_to.is_(None),
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.edge_to_domain(model) if model else None

    async def list_from(self, from_node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[KGEdge]:
        conditions = [KGEdgeModel.from_node_id == from_node_id.value]
        if edge_type is not None:
            conditions.append(KGEdgeModel.edge_type == edge_type.value)
        result = await self.session.execute(select(KGEdgeModel).where(*conditions))
        return [mappers.edge_to_domain(row) for row in result.scalars().all()]

    async def list_to(self, to_node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[KGEdge]:
        conditions = [KGEdgeModel.to_node_id == to_node_id.value]
        if edge_type is not None:
            conditions.append(KGEdgeModel.edge_type == edge_type.value)
        result = await self.session.execute(select(KGEdgeModel).where(*conditions))
        return [mappers.edge_to_domain(row) for row in result.scalars().all()]

    async def list_by_type(self, edge_type: EdgeType, limit: int = 5000) -> list[KGEdge]:
        stmt = select(KGEdgeModel).where(KGEdgeModel.edge_type == edge_type.value).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.edge_to_domain(row) for row in result.scalars().all()]

    async def count_by_type(self, edge_type: EdgeType) -> int:
        stmt = select(func.count()).select_from(KGEdgeModel).where(KGEdgeModel.edge_type == edge_type.value)
        return (await self.session.execute(stmt)).scalar_one()

    async def upsert(self, edge: KGEdge) -> KGEdge:
        existing = await self.session.get(KGEdgeModel, edge.id.value)
        model = mappers.edge_to_model(edge, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.edge_to_domain(model)

    async def close(self, edge_id: KGEdgeId, valid_to: datetime) -> KGEdge | None:
        model = await self.session.get(KGEdgeModel, edge_id.value)
        if model is None:
            return None
        model.valid_to = valid_to
        await self.session.flush()
        return mappers.edge_to_domain(model)

    async def delete(self, edge_id: KGEdgeId) -> bool:
        """Hard delete — distinct from `close()`. Reserved for erroneous edges (bad ingestion
        data) rather than genuine relationship transitions, which should be closed/superseded
        (`TemporalGraphService`) to preserve historical record."""
        model = await self.session.get(KGEdgeModel, edge_id.value)
        if model is None:
            return False
        await self.session.delete(model)
        await self.session.flush()
        return True
