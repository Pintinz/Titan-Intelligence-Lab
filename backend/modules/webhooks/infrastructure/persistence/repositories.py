from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId
from modules.webhooks.infrastructure.persistence import mappers
from modules.webhooks.infrastructure.persistence.models import WebhookDeliveryModel, WebhookEndpointModel


@dataclass
class SqlAlchemyWebhookEndpointRepository:
    session: AsyncSession

    async def get(self, endpoint_id: WebhookEndpointId) -> WebhookEndpoint | None:
        model = await self.session.get(WebhookEndpointModel, endpoint_id.value)
        return mappers.endpoint_to_domain(model) if model else None

    async def list_by_organization(self, organization_id: str) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpointModel).where(WebhookEndpointModel.organization_id == organization_id)
        result = await self.session.execute(stmt)
        return [mappers.endpoint_to_domain(row) for row in result.scalars().all()]

    async def list_subscribed_to(self, event_type: str) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpointModel).where(WebhookEndpointModel.is_active.is_(True))
        result = await self.session.execute(stmt)
        endpoints = [mappers.endpoint_to_domain(row) for row in result.scalars().all()]
        return [e for e in endpoints if e.is_subscribed(event_type)]

    async def upsert(self, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        existing = await self.session.get(WebhookEndpointModel, endpoint.id.value)
        model = mappers.endpoint_to_model(endpoint, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.endpoint_to_domain(model)

    async def delete(self, endpoint_id: WebhookEndpointId) -> None:
        model = await self.session.get(WebhookEndpointModel, endpoint_id.value)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


@dataclass
class SqlAlchemyWebhookDeliveryRepository:
    session: AsyncSession

    async def get(self, delivery_id: WebhookDeliveryId) -> WebhookDelivery | None:
        model = await self.session.get(WebhookDeliveryModel, delivery_id.value)
        return mappers.delivery_to_domain(model) if model else None

    async def list_by_endpoint(self, endpoint_id: WebhookEndpointId, limit: int = 100) -> list[WebhookDelivery]:
        stmt = (
            select(WebhookDeliveryModel)
            .where(WebhookDeliveryModel.endpoint_id == endpoint_id.value)
            .order_by(WebhookDeliveryModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.delivery_to_domain(row) for row in result.scalars().all()]

    async def list_pending_retries(self) -> list[WebhookDelivery]:
        stmt = select(WebhookDeliveryModel).where(WebhookDeliveryModel.status == DeliveryStatus.FAILED.value)
        result = await self.session.execute(stmt)
        return [mappers.delivery_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, delivery: WebhookDelivery) -> WebhookDelivery:
        existing = await self.session.get(WebhookDeliveryModel, delivery.id.value)
        model = mappers.delivery_to_model(delivery, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.delivery_to_domain(model)
