from __future__ import annotations

from modules.intelligence.application.news_relevance_filter import NewsRelevanceFilter, build_vocabulary, normalize_text


def test_normalize_text_lowercases_and_collapses_whitespace():
    assert normalize_text("  Arsenal   FC  ") == "arsenal fc"


def test_build_vocabulary_normalizes_and_drops_blank_names():
    vocab = build_vocabulary(["Arsenal", "", "  ", "Manchester United"])

    assert vocab == frozenset({"arsenal", "manchester united"})


def test_relevant_article_containing_a_canonical_team_name_passes():
    filt = NewsRelevanceFilter(vocabulary=build_vocabulary(["Arsenal", "Chelsea"]))

    assert filt.is_relevant("Arsenal injury update ahead of Chelsea clash", "Full team news inside.") is True


def test_irrelevant_article_does_not_pass():
    filt = NewsRelevanceFilter(vocabulary=build_vocabulary(["Arsenal", "Chelsea"]))

    assert filt.is_relevant("Local supermarket announces new opening", "Nothing football related here.") is False


def test_known_player_alias_matches():
    filt = NewsRelevanceFilter(vocabulary=build_vocabulary(["Robert Lewandowski"]))

    assert filt.is_relevant("Lewandowski-esque hattrick", "Robert Lewandowski scores again.") is True


def test_word_boundary_avoids_a_naive_substring_collision():
    """"Roma" must not match inside an unrelated word like "aroma"."""
    filt = NewsRelevanceFilter(vocabulary=build_vocabulary(["Roma"]))

    assert filt.is_relevant("A new aroma diffuser for your home", "Nothing football related.") is False


def test_empty_vocabulary_matches_nothing():
    filt = NewsRelevanceFilter(vocabulary=frozenset())

    assert filt.is_relevant("Arsenal win again", "Big win for the Gunners.") is False


def test_matching_is_case_insensitive():
    filt = NewsRelevanceFilter(vocabulary=build_vocabulary(["Arsenal"]))

    assert filt.is_relevant("ARSENAL CONFIRM NEW SIGNING", "details inside") is True
