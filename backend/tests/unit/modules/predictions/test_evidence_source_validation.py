from __future__ import annotations

from modules.predictions.domain.evidence_source_validation import filter_valid_source_ids


class TestFilterValidSourceIds:
    def test_keeps_ids_present_in_the_supplied_evidence(self):
        assert filter_valid_source_ids(["a", "b"], {"a", "b", "c"}) == ("a", "b")

    def test_drops_a_hallucinated_id_never_supplied_as_evidence(self):
        assert filter_valid_source_ids(["feature:form_corners", "fake:h2h"], {"feature:form_corners"}) == ("feature:form_corners",)

    def test_empty_candidates_returns_empty(self):
        assert filter_valid_source_ids([], {"a"}) == ()

    def test_empty_valid_set_drops_everything(self):
        assert filter_valid_source_ids(["a", "b"], set()) == ()

    def test_preserves_order_and_dedupes(self):
        assert filter_valid_source_ids(["b", "a", "a", "b"], {"a", "b"}) == ("b", "a")

    def test_accepts_a_list_of_valid_ids_not_only_a_set(self):
        assert filter_valid_source_ids(["a"], ["a", "b"]) == ("a",)
