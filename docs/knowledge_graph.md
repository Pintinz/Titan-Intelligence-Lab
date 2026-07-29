# TitanIQ — Knowledge Graph

Status: **Sports Semantic Intelligence Platform, Milestone 7** — population (Milestone 5) plus
the full read/reasoning layer: Graph Query Engine, Entity Resolution, Similarity Framework,
Semantic Search, Context Engine, Temporal Graph support, Graph Population extensions/
performance/monitoring, and RAG Foundation retrieval interfaces. See
[ontology.md](ontology.md) for the complete node/edge type catalog and per-entity population
status. As of Milestone 9, this platform is a genuine consumer, not just a producer: the
Prediction Intelligence Platform's `ExplainabilityEngine` retrieves Knowledge Graph evidence for
every prediction via Milestone 8's `IntelligenceRetrievalService` (itself wrapping this
platform's `GraphRetrievalPort`) — see [prediction_engine.md](prediction_engine.md) §7.

## 1. Purpose

The Knowledge Graph is TitanIQ's central semantic intelligence layer. Every future AI module —
Explainability, AI Context, Recommendations, Semantic Search, Entity Relationships, Similarity
Search, News Intelligence, Community Intelligence, future RAG, AI Assistant, Outcome Learning —
is meant to obtain contextual intelligence from this platform rather than rebuilding
relationship logic independently.

## 2. Node Types and Edge Types

The complete Sports Ontology (every canonical entity and relationship type, which are populated
vs. reserved for a future writer, and every entity/edge's metadata fields) lives in
[ontology.md](ontology.md) rather than being duplicated here. In short: `NodeType`/`EdgeType`
are additive-only string enums (`kg_nodes.node_type`/`kg_edges.edge_type` are literal
`String(32)` columns with live data — no member is ever renamed or removed). `KGNode` carries
Canonical ID, Provider References, Aliases, Metadata, Source, Version, Status, Created, Updated,
Confidence. `KGEdge` carries Weight, Confidence, Direction, Source, Timestamp, Version, and a
Validity Period (`valid_from`/`valid_to`).

Standing and Lineup data are **not** separate node types — they live relationally in
`modules.sports` and are represented in the graph as edge attributes (a team's rank/points on a
`COMPETES_IN` edge) rather than as nodes with their own identity, keeping the graph focused on
entities with independent identity across time.

## 3. Storage Decision

The graph is stored relationally (`kg_nodes`/`kg_edges` in Postgres, `knowledge_graph` schema)
rather than a dedicated graph database ([ADR-005](decisions.md)). Milestone 7's Graph Query
Engine confirms this scope call still holds: every traversal (shortest path, neighborhood
expansion, relationship traversal, connected components, historical snapshots) is implemented
as pure-Python BFS over `list_from`/`list_to`, not recursive SQL CTEs — portable across SQLite
and Postgres without dialect-specific SQL, and simple enough to reason about at this milestone's
traffic scale ([ADR-029](decisions.md)). Migration 0016 adds composite indexes
(`from_node_id, edge_type` / `to_node_id, edge_type`) so the traversal's dominant query pattern
is served directly rather than relying on the planner to intersect single-column indexes.
Revisit relational-vs-graph-DB as a fresh ADR only if traversal latency becomes a measured
problem at real query volume — not a committed migration.

## 4. Graph Query Engine

`GraphQueryService` (`backend/modules/knowledge_graph/application/graph_query_service.py`)
implements `GraphQueryPort`:

- **Shortest Path** — BFS with parent-pointer path reconstruction, bounded by `max_depth`.
- **Neighborhood Search / Subgraph Extraction / Context Expansion** — a shared `_expand()` BFS
  core, bounded by `max_nodes`, returning a `Subgraph` (`nodes`, `edges`, `truncated`).
- **Relationship Traversal / Reverse Traversal** — single-edge-type walk (`traverse`), with a
  `reverse` flag for direction.
- **Connected Components** — union-find over a bounded candidate set of one `NodeType`.
- **Timeline / Historical Queries** — `at_time()` (a neighborhood snapshot filtered to edges
  valid at a past instant) and `edge_history()` (every edge, current and closed, sorted oldest
  first).
- **Influence Queries** — `most_connected()`, degree centrality by edge type and direction.

## 5. Entity Resolution

`EntityResolutionService` supports Provider Mapping (`find_by_provider_ref`), Alias Resolution
(`find_by_alias`, case-insensitive), Duplicate Detection (`detect_duplicates` — groups by shared
alias or provider_ref, deduped across both passes), Conflict Resolution + Canonical Merge
(`merge`), Entity Versioning (`KGNode.version`, bumped on every upsert), and Historical Identity
(`resolve_canonical` follows `merged_into` chains, with a cycle guard).

Merge is **non-destructive**: a duplicate node is never deleted. `merge()` marks it
`status="merged"` with a `merged_into` pointer, redirects its edges onto the canonical node via
the same idempotent `upsert_edge` the population service already uses, and folds its aliases/
provider_refs into the canonical. The duplicate's original edges are left untouched as
historical record of what it used to represent.

## 6. Similarity Engine

Framework only, no ML embeddings this milestone — `SimilarityPort` (`similarity`,
`most_similar`) has one implementation, `GraphStructuralSimilarity`: Jaccard overlap of two
nodes' immediate graph neighbors. Deterministic, explainable, and covers Player/Team/Coach/
Venue/Competition/Model/Feature similarity identically — the metric doesn't care what
`NodeType` it's given, only which other nodes it's connected to. A future embedding-backed
adapter implements the same port and slots in without touching any consumer ([ADR-008](decisions.md)).

`SimilarityService.compute_and_store()` persists a score ≥ `similarity_threshold` as a weighted,
undirected `SIMILAR_TO` edge; `recompute_for_type()` batch-recomputes for every node of a type
against its top-N peers, intended for periodic runs, not per-request use.

## 7. Semantic Search

`SemanticSearchService` — thin, domain-named wrappers over the Graph Query Engine, so a caller
doesn't need to know edge-direction conventions (e.g. `PLAYS_FOR` is player → team). Covers the
constitution's example queries directly: players for a team, teams/matches coached by a coach,
rivals of a team, injuries before a match, transfers involving a team, relationships between two
entities, and contextual entities around a fixture.

## 8. Context Engine

`ContextEngine.build_context()` is one generic builder: a bounded neighborhood expansion grouped
by `NodeType` into a `ContextBundle`. Every named `context_for_*` method (fixture, match, player,
team, competition, prediction, news, feature, model, explainability, historical comparison) is a
thin wrapper choosing a depth/breadth appropriate to that entity's typical fan-out — the same
"one implementation, many entity kinds" shape the Similarity Engine already established. This
engine is the intended context provider for the Prediction Engine, News Engine, Recommendation
Engine, and AI Assistant once those subsystems exist. No LLM/narrative generation happens here —
that's RAG Foundation's job (§10), and RAG itself is out of scope this milestone.

## 9. Temporal Graph

Relationship Versioning (`KGEdge.version`), Time-valid Edges (`valid_from`/`valid_to`), and
Historical Snapshots/Traversal (`GraphQueryService.at_time`/`edge_history`) exist since the
ontology-metadata migration (0015) and Graph Query Engine (§4). `TemporalGraphService` adds the
one operation population's `upsert_edge` explicitly reserves for a genuine relationship change:
`supersede_edge()` closes an old edge and opens a new one in a single call (e.g. a transfer
ending a player's `PLAYS_FOR` at their old team and starting one at their new team) — as opposed
to `upsert_edge`'s in-place idempotent update of an unchanged relationship. `entity_evolution()`
derives a node's relationship-change timeline (opened/closed events) from edge history rather
than a new node-versioning table — the graph stays relational, not event-sourced.

## 10. Graph Population Extensions, Performance, Monitoring

**Population**: `GraphPopulationBatchService` adds Batch Writes (`batch_upsert_nodes`),
Relationship Discovery (`discover_teammate_relationships` — infers `TEAMMATE_OF` between players
sharing a current team), Relationship Deletion (`delete_edge` — a real hard delete for erroneous
edges, distinct from `TemporalGraphService.close_edge`'s historical-preserving close), and
Historical Replay (`replay()` — applies a batch of population events in ascending timestamp
order regardless of the order they're handed in, so an out-of-sequence historical backfill
produces the same graph state as real-time ingestion would have). Incremental Updates,
Relationship Updates, and Duplicate Prevention were already covered by Milestone 5's idempotent
`upsert_node`/`upsert_edge`; Merge by Entity Resolution (§5).

**Performance**: composite traversal indexes (§3, migration 0016); `CachedKGNodeRepository`, a
read-through caching decorator over `KGNodeRepositoryPort` reusing `modules.ingestion`'s
existing generic `SyncCachePort`/Redis integration — no new caching concept introduced.
Traversal Speed and Memory Usage are addressed by the Graph Query Engine's bounded BFS (§4/§3),
not a separate mechanism.

**Monitoring**: `GraphMonitoringService` reports node/edge counts (overall and by type),
population/traversal timing (via `GraphMetricsRecorder`, an explicit opt-in instrumentation
object — nothing wraps methods automatically), Cache Hit Ratio (from any object exposing a
`hit_ratio` property, e.g. `CachedKGNodeRepository`), Merge Count, Duplicate Count, an "Entity
Resolution Accuracy" proxy metric (merges ÷ (merges + detected duplicates) — there is no
ground-truth label this milestone, so this is documented as a proxy, not a true precision
figure), and Graph Growth (`growth_since()`, diffing two snapshots).

## 11. RAG Foundation

Retrieval interfaces only — `GraphRetrievalPort` (`retrieve(RetrievalQuery) -> RetrievalResult`)
and its one implementation, `GraphNativeRetrieval`, turn a bounded neighborhood expansion into
structured `RetrievalDocument`s (subject/relation/related-entity/confidence/source). No
embeddings, no vector search, no prompt construction, and no LLM call exist in this port or its
implementation — RAG itself (retrieval **and** generation) is explicitly out of scope this
milestone. A future embedding-backed retriever implements the same port without touching any
consumer.

## 12. API

`apps/api/routers/graph_router.py` (`/api/v1/graph`, read-only, gated at any authenticated
user): Entity Search, Relationship Search, Graph Traversal, Timeline Queries, Similarity
Queries, Context Queries, Neighborhood Queries, Graph Statistics. See
[api_specification.md](api_specification.md).

## 13. Consumers

Recommendation Engine (similarity, "teams like this") · Explainability Engine (contextual
factors in a prediction's reasoning, via Context Engine) · Analytics Engine (comparative
analysis) · AI Assistant / Natural Language Intelligence (entity resolution, relationship
lookups, semantic search, future RAG retrieval).

## 14. Build Order

1. ~~Node/edge tables + write path from ingestion~~ — ✅ **done, Milestone 5**.
2. ~~Graph Query Engine, Entity Resolution, Similarity Framework, Semantic Search, Context
   Engine, Temporal Graph, Population extensions/performance/monitoring, RAG Foundation~~ — ✅
   **done, Milestone 7** (this document).
3. Embedding-backed similarity/retrieval adapters, actual RAG generation, Recommendation Engine
   integration — future milestones, once those subsystems exist to consume this platform.

## 15. Milestone 5 Population Notes (unchanged)

`KnowledgeGraphPopulationService` (`backend/modules/knowledge_graph/application/
population_service.py`) exposes one `upsert_node`/`upsert_edge` primitive pair plus named
convenience wrappers (`populate_sport`, `populate_country`, `populate_competition`,
`populate_season`, `populate_venue`, `populate_team`, `populate_team_competition`,
`populate_player`, `populate_fixture`, `populate_team_statistics`, `populate_standing`, plus
Milestone 6's `populate_organization`/`populate_user`/`populate_subscription`/
`populate_provider` — the latter four exist and are tested standalone but are not yet wired into
`IdentityService`/`TenancyService`/`BillingService`'s write paths, to avoid a breaking
constructor-signature change to already-tested Milestone 6 services) — called directly by
`EntityReconciliationService` after each entity is persisted, not as a separate pass over
already-written data.
