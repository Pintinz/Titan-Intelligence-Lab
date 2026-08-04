from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.market_registry_service import (
    InvalidMarketLifecycleTransitionError,
    MarketAlreadyRegisteredError,
    MarketNotFoundError,
    MarketNotReadyForProductionError,
    MarketRegistryService,
)
from modules.predictions.domain.entities import FeatureMarketMapping
from modules.predictions.domain.value_objects import (
    FeatureMarketMappingId,
    MarketKind,
    MarketStatus,
    OutcomeType,
    TargetType,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def service(market_repo, feature_mapping_repo):
    return MarketRegistryService(markets=market_repo, feature_mappings=feature_mapping_repo)


async def _register(service, key="football.match_result", **overrides):
    kwargs = dict(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        now=T0,
    )
    kwargs.update(overrides)
    return await service.register(**kwargs)


@pytest.mark.asyncio
async def test_register_creates_draft_version_1(service):
    market = await _register(service)

    assert market.status is MarketStatus.DRAFT
    assert market.version == 1
    assert market.is_production() is False


@pytest.mark.asyncio
async def test_register_without_outcome_registry_kwargs_defaults_empty(service):
    """Every pre-Milestone-9.2 caller (market_seeding.py x4 sports) omits the new kwargs — must
    keep registering successfully with empty/None defaults, not require the new fields."""
    market = await _register(service)

    assert market.outcome_type is None
    assert market.allowed_values == ()
    assert market.resolver_key is None
    assert market.gemini_prompt_template is None


@pytest.mark.asyncio
async def test_register_accepts_outcome_registry_kwargs(service):
    market = await _register(
        service,
        key="football.match_winner",
        outcome_type=OutcomeType.HOME_DRAW_AWAY,
        allowed_values=("HOME_WIN", "DRAW", "AWAY_WIN"),
        resolver_key="football.match_winner",
        gemini_prompt_template="Explain the {predicted_outcome} prediction.",
    )

    assert market.outcome_type is OutcomeType.HOME_DRAW_AWAY
    assert market.allowed_values == ("HOME_WIN", "DRAW", "AWAY_WIN")
    assert market.resolver_key == "football.match_winner"
    assert market.gemini_prompt_template == "Explain the {predicted_outcome} prediction."


@pytest.mark.asyncio
async def test_register_duplicate_key_raises(service):
    await _register(service)

    with pytest.raises(MarketAlreadyRegisteredError):
        await _register(service)


@pytest.mark.asyncio
async def test_unknown_market_key_raises_not_found(service):
    with pytest.raises(MarketNotFoundError):
        await service.submit_for_review("does.not.exist")


@pytest.mark.asyncio
async def test_full_lifecycle_to_production_requires_required_feature_mapping(service, feature_mapping_repo):
    market = await _register(service)
    await service.submit_for_review(market.market_key)
    await service.approve(market.market_key, reviewer="cto", now=T0)

    with pytest.raises(MarketNotReadyForProductionError):
        await service.promote_to_production(market.market_key, now=T0)

    await feature_mapping_repo.upsert(
        FeatureMarketMapping(
            id=FeatureMarketMappingId(uuid4()), market_id=market.id, feature_key="team_form_last_5", is_required=True
        )
    )

    promoted = await service.promote_to_production(market.market_key, now=T0)
    assert promoted.status is MarketStatus.PRODUCTION
    assert promoted.is_production() is True


@pytest.mark.asyncio
async def test_reject_returns_market_to_draft_with_reason(service):
    market = await _register(service)
    await service.submit_for_review(market.market_key)

    rejected = await service.reject(market.market_key, reviewer="cto", reason="no historical data", now=T0)

    assert rejected.status is MarketStatus.DRAFT
    assert rejected.rejection_reason == "no historical data"


@pytest.mark.asyncio
async def test_cannot_promote_directly_from_draft(service):
    market = await _register(service)

    with pytest.raises(InvalidMarketLifecycleTransitionError):
        await service.promote_to_production(market.market_key, now=T0)


@pytest.mark.asyncio
async def test_deprecate_archive_remove_terminal_chain(service, feature_mapping_repo):
    market = await _register(service)
    await service.submit_for_review(market.market_key)
    await service.approve(market.market_key, reviewer="cto", now=T0)
    await feature_mapping_repo.upsert(
        FeatureMarketMapping(
            id=FeatureMarketMappingId(uuid4()), market_id=market.id, feature_key="team_form_last_5", is_required=True
        )
    )
    await service.promote_to_production(market.market_key, now=T0)

    deprecated = await service.deprecate(market.market_key, now=T0)
    assert deprecated.status is MarketStatus.DEPRECATED

    archived = await service.archive(market.market_key, now=T0)
    assert archived.status is MarketStatus.ARCHIVED

    removed = await service.remove(market.market_key, now=T0)
    assert removed.status is MarketStatus.REMOVED

    with pytest.raises(InvalidMarketLifecycleTransitionError):
        await service.submit_for_review(market.market_key)
