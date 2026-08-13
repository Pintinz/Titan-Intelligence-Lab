from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.intelligence.application.news_provenance import (
    CONFIDENCE_WEIGHT_MULTIPLIERS,
    ConfidenceInputs,
    NewsAvailabilityClassification,
    NewsEventConfidenceClassifier,
    classify_news_availability,
    is_information_available_before_kickoff,
)
from modules.intelligence.domain.value_objects import NewsEventConfidenceTier, NewsEventType, SyncTrigger, TrustLevel

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _availability(**overrides):
    defaults = dict(
        trigger=SyncTrigger.LIVE_SCHEDULED,
        sync_succeeded=True,
        validated=True,
        sync_time=T0,
        published_at=T0,
        has_genuine_timestamp=True,
    )
    defaults.update(overrides)
    return classify_news_availability(**defaults)


def test_genuine_live_scheduled_sync_is_verified_pre_match():
    result = _availability()

    assert result.classification == NewsAvailabilityClassification.VERIFIED_PRE_MATCH
    assert result.information_available_at == T0


def test_unvalidated_article_is_invalid_regardless_of_trigger():
    result = _availability(validated=False)

    assert result.classification == NewsAvailabilityClassification.INVALID
    assert result.information_available_at is None


def test_failed_sync_is_unknown_availability():
    result = _availability(sync_succeeded=False)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None


def test_manual_trigger_is_unknown_availability_not_verified():
    """The M9 production-safety posture: only a genuine automatic sync (LIVE_SCHEDULED) can ever
    produce VERIFIED_PRE_MATCH — a manually-triggered admin sync, even if fully successful and
    validated, cannot honestly claim the news was known before any given fixture's kickoff."""
    result = _availability(trigger=SyncTrigger.MANUAL)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME


def test_retry_trigger_is_unknown_availability():
    result = _availability(trigger=SyncTrigger.RETRY)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME


def test_untrusted_timestamp_is_unknown_availability_even_when_live_scheduled():
    result = _availability(has_genuine_timestamp=False)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None


def _confidence(**overrides):
    defaults = dict(
        event_type=NewsEventType.INJURY,
        is_official_source=False,
        source_trust_level=TrustLevel.UNVERIFIED,
        corroborating_source_count=0,
        contradicted=False,
        age_hours=1.0,
        ttl_hours=336.0,
    )
    defaults.update(overrides)
    return NewsEventConfidenceClassifier.classify(ConfidenceInputs(**defaults))


def test_contradicted_overrides_every_other_signal():
    tier = _confidence(contradicted=True, is_official_source=True, age_hours=1.0, ttl_hours=1000.0)

    assert tier is NewsEventConfidenceTier.CONTRADICTED


def test_expired_by_age_overrides_official_source():
    tier = _confidence(is_official_source=True, age_hours=100.0, ttl_hours=10.0)

    assert tier is NewsEventConfidenceTier.EXPIRED


def test_official_source_is_confirmed():
    tier = _confidence(is_official_source=True)

    assert tier is NewsEventConfidenceTier.CONFIRMED


def test_verified_trust_with_corroboration_is_probable():
    tier = _confidence(source_trust_level=TrustLevel.VERIFIED, corroborating_source_count=1)

    assert tier is NewsEventConfidenceTier.PROBABLE


def test_uncorroborated_unverified_transfer_is_rumour():
    tier = _confidence(event_type=NewsEventType.TRANSFER, source_trust_level=TrustLevel.UNVERIFIED, corroborating_source_count=0)

    assert tier is NewsEventConfidenceTier.RUMOUR


def test_uncorroborated_unverified_injury_is_uncertain_not_rumour():
    """RUMOUR is specifically a TRANSFER-speculation concept per the spec's own examples — the
    same unverified, uncorroborated report for a non-TRANSFER event type is merely UNCERTAIN."""
    tier = _confidence(event_type=NewsEventType.INJURY, source_trust_level=TrustLevel.UNVERIFIED, corroborating_source_count=0)

    assert tier is NewsEventConfidenceTier.UNCERTAIN


def test_confidence_weight_multipliers_cover_every_tier_and_zero_out_unreliable_tiers():
    assert set(CONFIDENCE_WEIGHT_MULTIPLIERS) == set(NewsEventConfidenceTier)
    assert CONFIDENCE_WEIGHT_MULTIPLIERS[NewsEventConfidenceTier.CONTRADICTED] == 0.0
    assert CONFIDENCE_WEIGHT_MULTIPLIERS[NewsEventConfidenceTier.EXPIRED] == 0.0
    assert CONFIDENCE_WEIGHT_MULTIPLIERS[NewsEventConfidenceTier.CONFIRMED] == 1.0


def test_information_available_strictly_before_kickoff_is_eligible():
    kickoff = T0 + timedelta(hours=2)
    assert is_information_available_before_kickoff(kickoff - timedelta(minutes=1), kickoff) is True


def test_information_available_exactly_at_kickoff_is_not_eligible():
    kickoff = T0 + timedelta(hours=2)
    assert is_information_available_before_kickoff(kickoff, kickoff) is False


def test_information_available_after_kickoff_is_not_eligible():
    kickoff = T0 + timedelta(hours=2)
    assert is_information_available_before_kickoff(kickoff + timedelta(minutes=1), kickoff) is False


# --- Milestone 12 §7: the five explicit BACKFILL provenance-safety cases ----------------------
# These call `classify_news_availability` directly — the single choke point every reconciliation
# call (including `NewsBackfillService`, via `IntelligenceEnrichmentOrchestrator.enrich_article`)
# routes through — so a passing test here is a guarantee about the real production code path,
# not a property of a fake or a test-only shortcut.


def test_case1_backfill_with_unknown_availability_is_unknown_availability_time():
    """CASE 1 — BACKFILL + unknown information availability -> UNKNOWN_AVAILABILITY_TIME."""
    result = _availability(trigger=SyncTrigger.BACKFILL, has_genuine_timestamp=False)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None


def test_case2_backfill_article_published_after_a_reference_kickoff_is_not_verified():
    """CASE 2 — BACKFILL + article timestamp after fixture kickoff -> NOT VERIFIED_PRE_MATCH.
    The trigger alone decides this (BACKFILL never reaches the LIVE_SCHEDULED branch) — a
    post-kickoff `published_at` isn't what disqualifies it, but the result must still never be
    VERIFIED_PRE_MATCH regardless of how the timestamp relates to any kickoff."""
    kickoff = T0
    published_after_kickoff = kickoff + timedelta(hours=3)

    result = _availability(trigger=SyncTrigger.BACKFILL, published_at=published_after_kickoff)

    assert result.classification != NewsAvailabilityClassification.VERIFIED_PRE_MATCH
    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None


def test_case3_backfill_article_published_before_kickoff_with_no_verified_provenance_is_not_verified():
    """CASE 3 — BACKFILL + article timestamp before fixture kickoff + no independently verified
    availability provenance -> NOT VERIFIED_PRE_MATCH. A historical article that merely *looks*
    pre-match (published well before some fixture's kickoff) still cannot become VERIFIED_PRE_MATCH
    on timestamp alone — only a genuine LIVE_SCHEDULED sync ever can. This is the core guarantee
    the whole milestone exists to prove: the trigger, not the calendar, is what's authoritative."""
    kickoff = T0 + timedelta(days=30)
    published_well_before_kickoff = T0

    result = _availability(trigger=SyncTrigger.BACKFILL, published_at=published_well_before_kickoff)

    assert result.classification != NewsAvailabilityClassification.VERIFIED_PRE_MATCH
    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None
    # information_available_at is None, so it is not even meaningful to ask
    # is_information_available_before_kickoff — there is nothing to compare against kickoff.
    assert result.information_available_at is None


def test_case4_live_scheduled_with_valid_pre_kickoff_availability_is_verified_pre_match():
    """CASE 4 — LIVE_SCHEDULED + valid pre-kickoff availability -> VERIFIED_PRE_MATCH. The one
    positive control: this is the only trigger/condition combination in the whole system that can
    ever produce VERIFIED_PRE_MATCH, and it still requires a genuine timestamp."""
    result = _availability(trigger=SyncTrigger.LIVE_SCHEDULED, has_genuine_timestamp=True)

    assert result.classification == NewsAvailabilityClassification.VERIFIED_PRE_MATCH
    assert result.information_available_at == T0

    kickoff = T0 + timedelta(hours=2)
    assert is_information_available_before_kickoff(result.information_available_at, kickoff) is True


def test_case5_admin_manual_with_unknown_availability_is_unknown_availability_time():
    """CASE 5 — ADMIN_MANUAL + unknown availability -> UNKNOWN_AVAILABILITY_TIME. Confirms the
    existing admin-sync trigger is held to the identical standard as the new BACKFILL trigger —
    neither is ever eligible to produce VERIFIED_PRE_MATCH, by the same single rule."""
    result = _availability(trigger=SyncTrigger.ADMIN_MANUAL)

    assert result.classification == NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME
    assert result.information_available_at is None


def test_backfill_can_never_produce_verified_pre_match_across_every_other_input_combination():
    """Exhaustive guard: for every combination of sync_succeeded/validated/has_genuine_timestamp,
    a BACKFILL trigger never once reaches VERIFIED_PRE_MATCH. If a future change to
    `classify_news_availability` ever adds a second path to VERIFIED_PRE_MATCH, this is the test
    that catches it."""
    for sync_succeeded in (True, False):
        for validated in (True, False):
            for has_genuine_timestamp in (True, False):
                result = _availability(
                    trigger=SyncTrigger.BACKFILL, sync_succeeded=sync_succeeded,
                    validated=validated, has_genuine_timestamp=has_genuine_timestamp,
                )
                assert result.classification != NewsAvailabilityClassification.VERIFIED_PRE_MATCH
