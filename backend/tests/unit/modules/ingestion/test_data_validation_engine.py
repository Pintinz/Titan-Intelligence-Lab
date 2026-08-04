from datetime import datetime, timezone
from uuid import uuid4

from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)
engine = DataValidationEngine()


def _ref(external_id="1", provider="mock") -> ProviderRef:
    return ProviderRef(provider=provider, external_id=external_id)


def test_valid_country_passes():
    result = engine.validate_country(ProviderCountryRecord(code="GB", name="United Kingdom"))
    assert result.is_valid


def test_country_with_bad_code_fails():
    result = engine.validate_country(ProviderCountryRecord(code="GBR", name="United Kingdom"))
    assert not result.is_valid
    assert "2 letters" in result.issues[0]


def test_country_missing_name_fails():
    result = engine.validate_country(ProviderCountryRecord(code="GB", name=""))
    assert not result.is_valid


def test_valid_team_passes():
    result = engine.validate_team(ProviderTeamRecord(external_ref=_ref(), name="Arsenal", short_name="ARS", country="England"))
    assert result.is_valid


def test_team_missing_name_fails():
    result = engine.validate_team(ProviderTeamRecord(external_ref=_ref(), name="", short_name="ARS", country="England"))
    assert not result.is_valid
    assert any("name" in issue for issue in result.issues)


def test_team_missing_external_id_fails():
    result = engine.validate_team(ProviderTeamRecord(external_ref=_ref(external_id=""), name="Arsenal", short_name="ARS", country="England"))
    assert not result.is_valid


def test_valid_player_passes():
    result = engine.validate_player(
        ProviderPlayerRecord(external_ref=_ref(), team_ref=_ref("t1"), name="Alex Carter", date_of_birth=datetime(1995, 1, 1, tzinfo=timezone.utc), position="forward"),
        now=T0,
    )
    assert result.is_valid


def test_player_future_birthdate_fails():
    result = engine.validate_player(
        ProviderPlayerRecord(external_ref=_ref(), team_ref=_ref("t1"), name="Alex Carter", date_of_birth=datetime(2030, 1, 1, tzinfo=timezone.utc), position="forward"),
        now=T0,
    )
    assert not result.is_valid
    assert "future" in result.issues[0]


def test_player_implausible_birth_year_fails():
    result = engine.validate_player(
        ProviderPlayerRecord(external_ref=_ref(), team_ref=_ref("t1"), name="Alex Carter", date_of_birth=datetime(1800, 1, 1, tzinfo=timezone.utc), position="forward"),
        now=T0,
    )
    assert not result.is_valid


def test_player_with_no_birthdate_passes():
    result = engine.validate_player(
        ProviderPlayerRecord(external_ref=_ref(), team_ref=_ref("t1"), name="Alex Carter", date_of_birth=None, position="forward"),
        now=T0,
    )
    assert result.is_valid


def _fixture(**overrides) -> ProviderFixtureRecord:
    kwargs = dict(
        external_ref=_ref("fx1"), home_team_ref=_ref("home"), away_team_ref=_ref("away"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    kwargs.update(overrides)
    return ProviderFixtureRecord(**kwargs)


def test_valid_fixture_passes():
    assert engine.validate_fixture(_fixture(), now=T0).is_valid


def test_fixture_home_equals_away_fails():
    result = engine.validate_fixture(_fixture(away_team_ref=_ref("home")), now=T0)
    assert not result.is_valid
    assert any("differ" in issue for issue in result.issues)


def test_fixture_missing_competition_ref_fails():
    result = engine.validate_fixture(_fixture(competition_ref=""), now=T0)
    assert not result.is_valid


def test_fixture_missing_season_label_fails():
    result = engine.validate_fixture(_fixture(season_label=""), now=T0)
    assert not result.is_valid


def test_fixture_implausible_date_fails():
    result = engine.validate_fixture(_fixture(scheduled_at=datetime(1850, 1, 1, tzinfo=timezone.utc)), now=T0)
    assert not result.is_valid
    assert any("date consistency" in issue for issue in result.issues)


def test_fixture_provider_mismatch_fails():
    result = engine.validate_fixture(
        _fixture(home_team_ref=ProviderRef(provider="other_provider", external_id="home")), now=T0
    )
    assert not result.is_valid
    assert any("provider integrity" in issue for issue in result.issues)


def test_valid_standing_passes():
    assert engine.validate_standing(ProviderStandingRecord(team_ref=_ref(), rank=1, points=45.0, record={})).is_valid


def test_standing_rank_zero_fails():
    result = engine.validate_standing(ProviderStandingRecord(team_ref=_ref(), rank=0, points=45.0, record={}))
    assert not result.is_valid


def test_standing_negative_points_fails():
    result = engine.validate_standing(ProviderStandingRecord(team_ref=_ref(), rank=1, points=-5.0, record={}))
    assert not result.is_valid


def test_valid_team_statistics_passes():
    result = engine.validate_team_statistics(
        ProviderTeamStatisticsRecord(fixture_ref=_ref(), team_ref=_ref(), stat_set={"points": 90})
    )
    assert result.is_valid


def test_empty_team_statistics_fails():
    result = engine.validate_team_statistics(ProviderTeamStatisticsRecord(fixture_ref=_ref(), team_ref=_ref(), stat_set={}))
    assert not result.is_valid


def test_valid_lineup_passes():
    lineup = ProviderLineupRecord(
        fixture_ref=_ref(), team_ref=_ref(), formation="4-3-3",
        slots=(ProviderLineupSlotRecord(player_ref=_ref("p1"), role="starter"),),
    )
    assert engine.validate_lineup(lineup).is_valid


def test_lineup_with_no_slots_fails():
    lineup = ProviderLineupRecord(fixture_ref=_ref(), team_ref=_ref(), formation=None, slots=())
    assert not engine.validate_lineup(lineup).is_valid


def test_lineup_with_invalid_role_fails():
    lineup = ProviderLineupRecord(
        fixture_ref=_ref(), team_ref=_ref(), formation=None,
        slots=(ProviderLineupSlotRecord(player_ref=_ref("p1"), role="captain"),),
    )
    result = engine.validate_lineup(lineup)
    assert not result.is_valid
    assert any("invalid values" in issue for issue in result.issues)


def test_valid_odds_passes():
    result = engine.validate_odds(ProviderOddsRecord(fixture_ref=_ref(), home_win=2.1, draw=3.4, away_win=3.6))
    assert result.is_valid


def test_odds_with_only_two_outcomes_passes():
    """A two-outcome sport (no draw) is still a valid record."""
    result = engine.validate_odds(ProviderOddsRecord(fixture_ref=_ref(), home_win=1.8, draw=None, away_win=2.0))
    assert result.is_valid


def test_odds_at_or_below_1_0_fails():
    result = engine.validate_odds(ProviderOddsRecord(fixture_ref=_ref(), home_win=1.0, draw=3.4, away_win=3.6))
    assert not result.is_valid
    assert any("invalid values" in issue for issue in result.issues)


def test_odds_with_no_outcomes_populated_fails():
    result = engine.validate_odds(ProviderOddsRecord(fixture_ref=_ref()))
    assert not result.is_valid
    assert any("missing values" in issue for issue in result.issues)


def test_find_duplicate_refs_detects_repeats():
    refs = [_ref("a"), _ref("b"), _ref("a"), _ref("c"), _ref("a")]
    issues = engine.find_duplicate_refs(refs)
    assert len(issues) == 1
    assert "3 times" in issues[0]


def test_find_duplicate_refs_empty_when_all_unique():
    refs = [_ref("a"), _ref("b"), _ref("c")]
    assert engine.find_duplicate_refs(refs) == []
