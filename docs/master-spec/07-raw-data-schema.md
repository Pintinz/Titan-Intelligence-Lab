# 07 — Raw Data Schema

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). This document specifies the `raw`
> schema — the untouched, provider-shaped tables the Feature Engineering Pipeline reads from and
> nothing else ever writes ML-facing logic against directly.

## 1. Design Principle

Raw tables store what a provider actually sent, normalized only enough to have consistent column
types and a shared `sport_code`/entity-id scheme across providers — not normalized into
ML-ready shape. A provider-specific quirk (an odd enum value, a sport-specific stat only some
leagues track) is preserved in a `raw_payload jsonb` column rather than forced into a column that
doesn't fit every provider, so nothing is silently dropped between "what the provider sent" and
"what's stored."

## 2. Core Entity Tables

```sql
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.venues (
    id              uuid PRIMARY KEY,
    sport_code      text NOT NULL,
    provider_key    text NOT NULL,          -- which external API this row came from
    provider_ref    text NOT NULL,          -- that provider's own id for this venue
    name            text NOT NULL,
    city            text,
    country         text,
    capacity        integer,
    surface         text,
    raw_payload     jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_key, provider_ref)
);

CREATE TABLE raw.teams (
    id              uuid PRIMARY KEY,
    sport_code      text NOT NULL,
    provider_key    text NOT NULL,
    provider_ref    text NOT NULL,
    name            text NOT NULL,
    short_name      text,
    country         text,
    venue_id        uuid REFERENCES raw.venues(id),
    logo_url        text,
    raw_payload     jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_key, provider_ref)
);
CREATE INDEX ix_raw_teams_venue_id ON raw.teams (venue_id);

CREATE TABLE raw.players (
    id              uuid PRIMARY KEY,
    sport_code      text NOT NULL,
    provider_key    text NOT NULL,
    provider_ref    text NOT NULL,
    team_id         uuid REFERENCES raw.teams(id),
    name            text NOT NULL,
    position        text,
    date_of_birth   date,
    raw_payload     jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_key, provider_ref)
);
CREATE INDEX ix_raw_players_team_id ON raw.players (team_id);
```

## 3. Fixtures & Results

```sql
CREATE TABLE raw.competitions (
    id              uuid PRIMARY KEY,
    sport_code      text NOT NULL,
    provider_key    text NOT NULL,
    provider_ref    text NOT NULL,
    name            text NOT NULL,
    country         text,
    season_label    text NOT NULL,
    raw_payload     jsonb NOT NULL DEFAULT '{}',
    UNIQUE (provider_key, provider_ref, season_label)
);

CREATE TABLE raw.fixtures (
    id                  uuid PRIMARY KEY,
    sport_code          text NOT NULL,
    provider_key        text NOT NULL,
    provider_ref        text NOT NULL,
    competition_id       uuid NOT NULL REFERENCES raw.competitions(id),
    home_team_id        uuid NOT NULL REFERENCES raw.teams(id),
    away_team_id        uuid NOT NULL REFERENCES raw.teams(id),
    venue_id            uuid REFERENCES raw.venues(id),
    scheduled_at         timestamptz NOT NULL,
    status               text NOT NULL,       -- 'scheduled' | 'live' | 'finished' | 'postponed' | 'cancelled'
    raw_payload          jsonb NOT NULL DEFAULT '{}',
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_key, provider_ref)
);
CREATE INDEX ix_raw_fixtures_competition_id ON raw.fixtures (competition_id);
CREATE INDEX ix_raw_fixtures_home_team_id ON raw.fixtures (home_team_id);
CREATE INDEX ix_raw_fixtures_away_team_id ON raw.fixtures (away_team_id);
CREATE INDEX ix_raw_fixtures_scheduled_at ON raw.fixtures (scheduled_at);

-- Results are a 1:1 extension of a finished fixture, not a separate lifecycle entity —
-- separated from `fixtures` so a scheduled fixture never carries nullable score columns.
CREATE TABLE raw.results (
    fixture_id          uuid PRIMARY KEY REFERENCES raw.fixtures(id),
    home_score           integer NOT NULL,
    away_score           integer NOT NULL,
    period_scores        jsonb NOT NULL DEFAULT '[]',  -- e.g. per-set/per-quarter/per-inning breakdown
    finished_at           timestamptz NOT NULL,
    raw_payload           jsonb NOT NULL DEFAULT '{}'
);
```

## 4. Statistics

```sql
CREATE TABLE raw.team_statistics (
    id              uuid PRIMARY KEY,
    fixture_id       uuid NOT NULL REFERENCES raw.fixtures(id),
    team_id          uuid NOT NULL REFERENCES raw.teams(id),
    sport_code       text NOT NULL,
    stats            jsonb NOT NULL,   -- sport-specific stat bag: shots/possession/corners (football),
                                        -- rebounds/turnovers (basketball), hits/errors (baseball), etc.
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (fixture_id, team_id)
);
CREATE INDEX ix_raw_team_statistics_fixture_id ON raw.team_statistics (fixture_id);

CREATE TABLE raw.player_statistics (
    id              uuid PRIMARY KEY,
    fixture_id       uuid NOT NULL REFERENCES raw.fixtures(id),
    player_id        uuid NOT NULL REFERENCES raw.players(id),
    sport_code       text NOT NULL,
    stats            jsonb NOT NULL,
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (fixture_id, player_id)
);
CREATE INDEX ix_raw_player_statistics_fixture_id ON raw.player_statistics (fixture_id);
```

## 5. Lineups, Injuries, Standings

```sql
CREATE TABLE raw.lineups (
    id              uuid PRIMARY KEY,
    fixture_id       uuid NOT NULL REFERENCES raw.fixtures(id),
    team_id          uuid NOT NULL REFERENCES raw.teams(id),
    player_id        uuid NOT NULL REFERENCES raw.players(id),
    role             text NOT NULL,      -- 'starter' | 'bench' | 'unavailable'
    position          text,
    raw_payload        jsonb NOT NULL DEFAULT '{}',
    UNIQUE (fixture_id, player_id)
);
CREATE INDEX ix_raw_lineups_fixture_id ON raw.lineups (fixture_id);

CREATE TABLE raw.injuries (
    id              uuid PRIMARY KEY,
    player_id        uuid NOT NULL REFERENCES raw.players(id),
    team_id          uuid NOT NULL REFERENCES raw.teams(id),
    status            text NOT NULL,      -- 'out' | 'doubtful' | 'questionable' | 'returned'
    description        text,
    reported_at         timestamptz NOT NULL,
    expected_return_at  timestamptz,
    raw_payload          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_raw_injuries_player_id ON raw.injuries (player_id);
CREATE INDEX ix_raw_injuries_reported_at ON raw.injuries (reported_at);

CREATE TABLE raw.standings (
    id              uuid PRIMARY KEY,
    competition_id   uuid NOT NULL REFERENCES raw.competitions(id),
    team_id          uuid NOT NULL REFERENCES raw.teams(id),
    rank              integer NOT NULL,
    played            integer NOT NULL,
    won               integer NOT NULL,
    drawn             integer,             -- null for sports with no draw (e.g. baseball)
    lost              integer NOT NULL,
    points            numeric,
    snapshot_at         timestamptz NOT NULL,
    raw_payload          jsonb NOT NULL DEFAULT '{}',
    UNIQUE (competition_id, team_id, snapshot_at)
);
CREATE INDEX ix_raw_standings_competition_id ON raw.standings (competition_id);
```

## 6. Events, Head-to-Head, Odds

```sql
CREATE TABLE raw.events (
    id              uuid PRIMARY KEY,
    fixture_id       uuid NOT NULL REFERENCES raw.fixtures(id),
    team_id          uuid REFERENCES raw.teams(id),
    player_id        uuid REFERENCES raw.players(id),
    event_type        text NOT NULL,      -- 'goal' | 'card' | 'substitution' | 'timeout' | ...
    occurred_minute    integer,
    raw_payload         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_raw_events_fixture_id ON raw.events (fixture_id);

-- Head-to-head is a derived-but-still-raw view: the pair of teams and the list of past fixture
-- ids between them, refreshed on ingestion rather than computed ad hoc by the feature layer,
-- since "which fixtures count as this pair's history" is itself provider-sourced in some feeds.
CREATE TABLE raw.head_to_head (
    id              uuid PRIMARY KEY,
    team_a_id        uuid NOT NULL REFERENCES raw.teams(id),
    team_b_id        uuid NOT NULL REFERENCES raw.teams(id),
    fixture_id        uuid NOT NULL REFERENCES raw.fixtures(id),
    UNIQUE (team_a_id, team_b_id, fixture_id)
);

CREATE TABLE raw.odds (
    id              uuid PRIMARY KEY,
    fixture_id       uuid NOT NULL REFERENCES raw.fixtures(id),
    provider_key     text NOT NULL,
    market_key        text NOT NULL,      -- provider's own market label, mapped to markets.market_definitions later
    outcome            text NOT NULL,
    price               numeric NOT NULL,
    recorded_at          timestamptz NOT NULL DEFAULT now(),
    raw_payload           jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_raw_odds_fixture_id ON raw.odds (fixture_id);
CREATE INDEX ix_raw_odds_recorded_at ON raw.odds (recorded_at);
```

## 7. Invariants

- **Append-mostly.** `fixtures.status` and `results` rows update as an event progresses
  (scheduled → live → finished), but historical `team_statistics`/`player_statistics`/`odds` rows
  are never overwritten in place — a new snapshot is a new row, timestamped, so the Feature
  Engineering Pipeline's `as_of` filtering (§ [03](03-data-engineering-architecture.md) §2 "Leakage
  prevention") has real historical snapshots to filter against, not just the latest known state.
- **Provider-traceable.** Every row carries `provider_key` + `provider_ref`, so any raw value can be
  traced back to exactly which external API produced it — required for debugging a bad feature back
  to its source.
- **No ML logic here.** No derived/computed column lives in `raw` — that's what
  [`08-feature-store-schema.md`](08-feature-store-schema.md) is for.
