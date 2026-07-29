# TitanIQ — Sports Ontology (Milestone 7)

The complete canonical entity and relationship catalog for the Knowledge Graph
([knowledge_graph.md](knowledge_graph.md)). `NodeType`/`EdgeType`
(`backend/modules/knowledge_graph/domain/value_objects.py`) are additive-only string enums —
`kg_nodes.node_type`/`kg_edges.edge_type` are literal `String(32)` columns with live data, so no
member is ever renamed or removed, only added (mirrors the Entity Expansion Matrix pattern in
[database_schema.md](database_schema.md) §11: not every entity has a population writer yet, but
every entity has a place reserved for one).

## 1. Entity Metadata

Every `KGNode` carries: Canonical ID (`id`, a `KGNodeId`), Provider References
(`provider_refs: dict`, e.g. `{"api_football": "12345"}`), Aliases (`aliases: list[str]`),
Metadata (`attributes: dict`), Source (`source: str`, default `"ingestion"`), Version
(`version: int`, bumped on every upsert), Status (`status: str` — `active` | `merged` |
`deprecated`), Created (`created_at`), Updated (`updated_at`), and Confidence
(`confidence: float`, default `1.0`). A merged node additionally carries `merged_into` (a
stringified `KGNodeId` — see [knowledge_graph.md](knowledge_graph.md) §5).

## 2. Node Types

Grouped by when a population writer started populating them — every member below already
exists in the enum regardless of group; "M5"/"M6" mark when `KnowledgeGraphPopulationService`
gained a writer for it, unmarked means ontology-only (reserved, no writer yet).

### M5 — populated since Milestone 5

Sport · Country · Competition · Season · Team · Player · Venue · Match · Statistics

### M6 — populated since Milestone 6

Organization · User · Subscription · Provider

### Ontology-only — reserved, no writer yet

Manager · Coach · Assistant Coach · Official · Referee · Fixture (distinct from Match: a
scheduled game vs. the played instance) · Round · Division · Conference · Lineup · Formation ·
Player Statistics · Team Statistics · Standing · Ranking · Transfer · Injury · Suspension ·
Event (Match Event / Historical Event) · Tournament · Award · Prediction · Feature · Feature
Group · Model · Dataset · News · News Article · News Event · Community Intelligence · Community
Topic · Sentiment · Recommendation · AI Report

Standing and Lineup are deliberately **not** separate graph nodes even once a writer exists for
them — see [knowledge_graph.md](knowledge_graph.md) §2.

## 3. Edge Metadata

Every `KGEdge` carries: Weight (`weight: float`, default `1.0`), Confidence
(`confidence: float`), Direction (`directed: bool`, `False` for inherently symmetric
relationships like `TEAMMATE_OF`/`RIVAL_OF`), Source (`source: str`), Timestamp (implicit —
see Validity Period), Version (`version: int`, bumped on every upsert), and a Validity Period
(`valid_from`/`valid_to`; `valid_to is None` means the edge is currently active).

## 4. Edge Types (Relationship Engine)

### M5

`PLAYS_FOR` (player → team) · `COMPETES_IN` (team → competition, or team → season with
rank/points attributes for a standing) · `SCHEDULED_AT` (match → venue) · `MANAGES`
(manager → team) · `INVOLVED_IN` (team/player → match, with a `side`/`role` attribute) ·
`REPORTED_BY` (news event → entity) · `PREDICTS` (prediction → fixture) · `DERIVED_FROM`
(feature → feature, or statistics → match/team) · `SIMILAR_TO` (entity → entity, weighted,
computed — see §6 below) · `BELONGS_TO` (generic hierarchical containment) · `LOCATED_IN`
(team/venue → country)

### M7 — player relationships

`TRANSFERRED_TO` · `INJURED_IN` · `RECEIVED_CARD` · `ASSISTED_GOAL` · `SCORED_GOAL` ·
`STARTED_MATCH` · `SUBSTITUTED` · `TEAMMATE_OF` (undirected) · `COACHED_BY`
(subject → coach)

### M7 — team relationships

`HOME_VENUE` · `RIVAL_OF` (undirected) · `WON_MATCH` · `LOST_MATCH` · `DREW_MATCH` ·
`USED_FORMATION`

### M7 — match relationships

`OFFICIATED_BY` · `CONTAINS_EVENT`

### M7 — feature/model/prediction relationships

`GENERATED_FROM` · `CONSUMES_FEATURE` · `GENERATED_BY` · `VALIDATED_BY`

### M7 — news/community relationships

`REFERENCES`

## 5. Graph Query Engine, Entity Resolution, Similarity, Semantic Search, Context Engine, Temporal Graph, RAG Foundation

See [knowledge_graph.md](knowledge_graph.md) §4–§11 for the query/reasoning capabilities built
on top of this ontology — this document is the entity/relationship catalog only, kept separate
so the two can be read (and diffed) independently as the ontology keeps growing after this
milestone.

## 6. What This Milestone Deliberately Does Not Build

- **ML embeddings / vector similarity** — the Similarity Engine is a graph-structural framework
  only (Jaccard neighbor overlap); a future embedding-backed adapter implements the same
  `SimilarityPort` (docs/decisions.md ADR-008).
- **RAG generation** — the RAG Foundation is retrieval-only (`GraphRetrievalPort`); no prompt
  construction or LLM call exists yet.
- **A dedicated graph database** — the graph stays relational (docs/decisions.md ADR-005,
  ADR-029); see [knowledge_graph.md](knowledge_graph.md) §3 for the revisit condition.
- **Node-versioning/event-sourcing storage** — Entity Evolution is derived from edge history,
  not a new per-node snapshot table.
- **Wiring M6 business-entity population into M6 services' write paths** —
  `populate_organization`/`populate_user`/`populate_subscription`/`populate_provider` exist and
  are tested standalone but aren't called from `IdentityService`/`TenancyService`/
  `BillingService` yet, to avoid a breaking constructor-signature change to already-tested
  Milestone 6 code.
