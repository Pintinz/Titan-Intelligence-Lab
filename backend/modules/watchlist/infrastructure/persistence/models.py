from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="watchlist")


class Base(DeclarativeBase):
    metadata = metadata


class WatchlistEntryModel(Base):
    __tablename__ = "watchlist_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_ref", name="uq_watchlist_entry_per_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    entity_type: Mapped[str] = mapped_column(String(16), index=True)
    entity_ref: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
