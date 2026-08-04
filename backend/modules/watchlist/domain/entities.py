from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId


@dataclass
class WatchlistEntry:
    """One user following one entity — a match, team, competition, or prediction. ``entity_ref``
    is the stringified id of that entity in its own module (FixtureId/TeamId/CompetitionId/
    PredictionId); watchlist deliberately holds no FK into those tables, the same loose
    entity_type/entity_ref reference pattern already used by the Knowledge Graph and by
    Prediction.subject_ref — watchlist doesn't own sports/prediction data, it only references it."""

    id: WatchlistEntryId
    user_id: UserId
    entity_type: WatchlistEntityType
    entity_ref: str
    created_at: datetime
