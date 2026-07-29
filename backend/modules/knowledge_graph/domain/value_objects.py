"""Value objects for the Knowledge Graph (docs/knowledge_graph.md, docs/ontology.md).

Milestone 5 shipped population-only for a 9-node/11-edge subset. Milestone 7 (Sports Semantic
Intelligence Platform) completes the ontology — every canonical entity/relationship named in
the constitution now has a `NodeType`/`EdgeType` member — without renaming or removing any
existing member, since both are persisted as literal strings in `String(32)` columns
(`kg_nodes.node_type`, `kg_edges.edge_type`) with a live schema. Not every member has a writer
yet; docs/ontology.md tracks which are populated vs. ontology-only, mirroring the Entity
Expansion Matrix pattern already established for the relational schema
(docs/database_schema.md §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class NodeType(str, Enum):
    """docs/ontology.md §1. `M5` = populated since Milestone 5; `M6` = populated since
    Milestone 6 (real M6 entities — identity/tenancy/billing — now have KG population wired
    alongside sports data); unmarked = ontology-only, reserved for a future population writer.
    """

    # -- M5: populated ---------------------------------------------------------------------
    SPORT = "sport"
    COUNTRY = "country"
    COMPETITION = "competition"
    SEASON = "season"
    TEAM = "team"
    PLAYER = "player"
    VENUE = "venue"
    MATCH = "match"
    STATISTICS = "statistics"

    # -- M6: populated (business entities now represented in the semantic graph) ------------
    ORGANIZATION = "organization"
    USER = "user"
    SUBSCRIPTION = "subscription"
    PROVIDER = "provider"

    # -- ontology-only: reserved, no writer yet ----------------------------------------------
    MANAGER = "manager"
    COACH = "coach"
    ASSISTANT_COACH = "assistant_coach"
    OFFICIAL = "official"
    REFEREE = "referee"
    FIXTURE = "fixture"  # distinct from MATCH: scheduled game vs. the played instance
    ROUND = "round"
    DIVISION = "division"
    CONFERENCE = "conference"
    LINEUP = "lineup"
    FORMATION = "formation"
    PLAYER_STATISTICS = "player_statistics"
    TEAM_STATISTICS = "team_statistics"
    STANDING = "standing"
    RANKING = "ranking"
    TRANSFER = "transfer"
    INJURY = "injury"
    SUSPENSION = "suspension"
    EVENT = "event"
    TOURNAMENT = "tournament"
    AWARD = "award"
    PREDICTION = "prediction"
    FEATURE = "feature"
    FEATURE_GROUP = "feature_group"
    MODEL = "model"
    DATASET = "dataset"
    NEWS = "news"
    NEWS_ARTICLE = "news_article"
    NEWS_EVENT = "news_event"
    COMMUNITY_INTELLIGENCE = "community_intelligence"
    COMMUNITY_TOPIC = "community_topic"
    SENTIMENT = "sentiment"
    RECOMMENDATION = "recommendation"
    AI_REPORT = "ai_report"


class EdgeType(str, Enum):
    """docs/ontology.md §2. M5 additions documented there already
    (BELONGS_TO/LOCATED_IN). Milestone 7 additions cover the full relationship-engine list
    from the constitution — grouped below by subject, matching the spec's own grouping."""

    # -- M5 ------------------------------------------------------------------------------------
    PLAYS_FOR = "plays_for"
    COMPETES_IN = "competes_in"
    SCHEDULED_AT = "scheduled_at"
    MANAGES = "manages"
    INVOLVED_IN = "involved_in"
    REPORTED_BY = "reported_by"
    PREDICTS = "predicts"
    DERIVED_FROM = "derived_from"
    SIMILAR_TO = "similar_to"
    BELONGS_TO = "belongs_to"
    LOCATED_IN = "located_in"

    # -- M7: player relationships --------------------------------------------------------------
    TRANSFERRED_TO = "transferred_to"
    INJURED_IN = "injured_in"
    RECEIVED_CARD = "received_card"
    ASSISTED_GOAL = "assisted_goal"
    SCORED_GOAL = "scored_goal"
    STARTED_MATCH = "started_match"
    SUBSTITUTED = "substituted"
    TEAMMATE_OF = "teammate_of"
    COACHED_BY = "coached_by"

    # -- M7: team relationships -----------------------------------------------------------------
    HOME_VENUE = "home_venue"
    RIVAL_OF = "rival_of"
    WON_MATCH = "won_match"
    LOST_MATCH = "lost_match"
    DREW_MATCH = "drew_match"
    USED_FORMATION = "used_formation"

    # -- M7: match relationships ----------------------------------------------------------------
    OFFICIATED_BY = "officiated_by"
    CONTAINS_EVENT = "contains_event"

    # -- M7: feature/model/prediction relationships ---------------------------------------------
    GENERATED_FROM = "generated_from"
    CONSUMES_FEATURE = "consumes_feature"
    GENERATED_BY = "generated_by"
    VALIDATED_BY = "validated_by"

    # -- M7: news/community relationships ---------------------------------------------------------
    REFERENCES = "references"


@dataclass(frozen=True)
class KGNodeId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class KGEdgeId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
