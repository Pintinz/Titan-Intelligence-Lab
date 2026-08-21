"""POST-M24 Phase 2: `provider_cache_codec` must round-trip every DTO `SportsProviderRouter`
caches — including nested dataclasses, `datetime` fields, and `tuple`-typed fields — through a
JSON-safe structure, since the response cache now goes through a real `SyncCachePort` (Redis in
production) instead of holding raw Python objects in an in-process dict."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.provider_cache_codec import (
    ProviderCacheDecodeError,
    decode,
    encode,
)
from modules.sports.ports.provider_gateway import (
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderTeamRecord,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def test_round_trips_plain_values():
    assert decode(encode(None)) is None
    assert decode(encode([1, 2, 3])) == [1, 2, 3]
    assert decode(encode({"a": 1})) == {"a": 1}
    assert decode(encode("result")) == "result"


def test_round_trips_a_single_dataclass_with_nested_ref():
    record = ProviderTeamRecord(
        external_ref=ProviderRef("api_football", "42"), name="Arsenal", short_name="ARS", country="England",
    )

    restored = decode(encode(record))

    assert restored == record
    assert isinstance(restored.external_ref, ProviderRef)


def test_round_trips_datetime_fields():
    record = ProviderFixtureRecord(
        external_ref=ProviderRef("api_football", "100"),
        home_team_ref=ProviderRef("api_football", "42"),
        away_team_ref=ProviderRef("api_football", "43"),
        scheduled_at=NOW,
        competition_ref="39",
        season_label="2026",
    )

    restored = decode(encode(record))

    assert restored == record
    assert restored.scheduled_at == NOW


def test_round_trips_a_list_of_dataclasses():
    records = [
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "1"), name="A", short_name="A", country=None),
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "2"), name="B", short_name="B", country=None),
    ]

    restored = decode(encode(records))

    assert restored == records


def test_round_trips_a_tuple_typed_field_as_a_real_tuple():
    record = ProviderLineupRecord(
        fixture_ref=ProviderRef("api_football", "100"),
        team_ref=ProviderRef("api_football", "42"),
        formation="4-3-3",
        slots=(ProviderLineupSlotRecord(player_ref=ProviderRef("api_football", "7"), role="starter"),),
    )

    restored = decode(encode(record))

    assert restored == record
    assert isinstance(restored.slots, tuple)


def test_round_trips_none_result():
    assert decode(encode(None)) is None


def test_round_trips_optional_record_present():
    record = ProviderOddsRecord(fixture_ref=ProviderRef("api_football", "100"), home_win=2.1, draw=3.4, away_win=3.0)

    restored = decode(encode(record))

    assert restored == record


def test_decode_fails_closed_on_unrecognized_type_tag():
    with pytest.raises(ProviderCacheDecodeError):
        decode({"__provider_type__": "SomethingNotRegistered", "x": 1})
