from __future__ import annotations

from modules.predictions.domain import football_semantic_mapping as mapping


class TestDescribe:
    def test_known_feature_returns_football_concept(self):
        assert mapping.describe("football.fixture.form_possession_pct_diff_last5") == \
            "recent territorial/possession control advantage"

    def test_unknown_feature_falls_back_honestly_not_fabricated(self):
        result = mapping.describe("football.fixture.some_never_registered_key")
        assert result == "some never registered key"
        assert result not in mapping._CONCEPTS.values()


class TestTeamForFeature:
    def test_diff_feature_is_side_neutral(self):
        assert mapping.team_for_feature("football.fixture.form_goals_diff_last5") is None

    def test_home_specific_feature_attributes_to_home(self):
        assert mapping.team_for_feature("football.fixture.home_form_goals") == "home side"


class TestMarketFocusConcepts:
    def test_every_market_maps_to_a_nonempty_real_concept_list(self):
        for market_key, concepts in mapping.MARKET_FOCUS_CONCEPTS.items():
            assert market_key.startswith("football.")
            assert len(concepts) > 0
            for concept in concepts:
                assert concept  # non-empty string, real feature-key suffix
