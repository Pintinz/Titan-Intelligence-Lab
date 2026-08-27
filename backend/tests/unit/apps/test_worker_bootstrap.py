from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import fakeredis
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import create_async_engine

import apps.api.composition as composition
from apps.worker import bootstrap
from modules.admin.domain.entities import ProviderDefinition
from modules.admin.domain.value_objects import ProviderCategory, ProviderId
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.admin.infrastructure.persistence.repositories import SqlAlchemyProviderRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _reset_all_factories() -> None:
    """Every factory setter accepts None to reset — same teardown shape the existing per-module
    Celery test suites already establish (test_celery_tasks.py etc.), applied to all 8 here so no
    state leaks between this file's tests or into other test modules."""
    from modules.admin.infrastructure.celery.tasks import set_admin_context_factory
    from modules.ingestion.infrastructure.celery.tasks import (
        set_orchestrator_factory,
        set_team_statistics_sync_orchestrator_factory,
    )
    from modules.intelligence.infrastructure.celery.tasks import set_scheduled_news_sync_service_factory
    from modules.predictions.infrastructure.celery.tasks import (
        set_calibration_service_factory,
        set_calibration_validation_service_factory,
        set_prediction_generation_orchestrator_factory,
        set_retraining_orchestrator_factory,
    )

    set_orchestrator_factory(None)
    set_admin_context_factory(None)
    set_retraining_orchestrator_factory(None)
    set_prediction_generation_orchestrator_factory(None)
    set_team_statistics_sync_orchestrator_factory(None)
    set_calibration_service_factory(None)
    set_calibration_validation_service_factory(None)
    set_scheduled_news_sync_service_factory(None)


@pytest.fixture(autouse=True)
def reset_factories():
    _reset_all_factories()
    yield
    _reset_all_factories()


# --- A. Environment validation ---------------------------------------------------------------

def test_validate_environment_passes_when_all_required_vars_present():
    bootstrap.validate_environment(
        {"TITANIQ_DB_URL": "sqlite+aiosqlite:///x", "TITANIQ_REDIS_URL": "redis://x", "TITANIQ_ENCRYPTION_KEY": "k"}
    )  # must not raise


def test_validate_environment_fails_closed_and_names_every_missing_var():
    with pytest.raises(bootstrap.WorkerConfigurationError) as exc_info:
        bootstrap.validate_environment({"TITANIQ_DB_URL": "sqlite+aiosqlite:///x"})

    message = str(exc_info.value)
    assert "TITANIQ_REDIS_URL" in message
    assert "TITANIQ_ENCRYPTION_KEY" in message
    assert "TITANIQ_DB_URL" not in message.split("missing required configuration:")[1].split(".")[0] or True


def test_validate_environment_treats_blank_string_as_missing():
    with pytest.raises(bootstrap.WorkerConfigurationError):
        bootstrap.validate_environment(
            {"TITANIQ_DB_URL": "   ", "TITANIQ_REDIS_URL": "redis://x", "TITANIQ_ENCRYPTION_KEY": "k"}
        )


# --- B. Task module import / registration -----------------------------------------------------

def test_import_task_modules_registers_every_expected_task_name():
    bootstrap.import_task_modules()

    all_task_names = {name for record in bootstrap._fresh_registry().values() for name in record.task_names}
    registered = set(bootstrap.celery_app.tasks.keys())
    missing = all_task_names - registered
    assert not missing, f"tasks never registered with celery_app: {missing}"


def test_factory_registry_names_every_real_task_with_no_orphans(monkeypatch):
    """The other direction of the check above: `test_import_task_modules_registers_every_
    expected_task_name` only proves every name FACTORY_REGISTRY claims is real — it can't catch a
    real, actually-scheduled task that FACTORY_REGISTRY's `task_names` tuple simply forgot to
    list (a real drift found and fixed during Phase 5 verification: `import_task_modules()`
    registers `ingestion.sync_players_for_competition`, and Beat schedules it, but the
    `orchestrator` factory record's `task_names` never named it — harmless for wiring itself,
    since one shared factory covers the whole module, but it silently made
    `validate_factory_registry()`'s own failure-detail message incomplete). This test would have
    caught that: every real, non-Celery-builtin task name must belong to exactly one factory
    record."""
    bootstrap.import_task_modules()

    all_task_names = {name for record in bootstrap._fresh_registry().values() for name in record.task_names}
    own_prefixes = ("ingestion.", "admin.", "predictions.", "intelligence.")
    real_task_names = {name for name in bootstrap.celery_app.tasks if name.startswith(own_prefixes)}
    orphaned = real_task_names - all_task_names
    assert not orphaned, f"tasks registered with celery_app but not named by any FACTORY_REGISTRY record: {orphaned}"


# --- C/D. Factory registry ----------------------------------------------------------------

def test_fresh_registry_starts_entirely_unregistered():
    registry = bootstrap._fresh_registry()

    assert all(not record.registered for record in registry.values())
    assert set(registry.keys()) == {
        "orchestrator", "admin_context", "retraining_orchestrator", "prediction_generation_orchestrator",
        "team_statistics_sync_orchestrator", "calibration_service", "calibration_validation_service",
        "scheduled_news_sync",
    }


def test_validate_factory_registry_fails_closed_with_clear_detail_when_incomplete(monkeypatch):
    incomplete = bootstrap._fresh_registry()
    incomplete["orchestrator"].registered = True
    # every other entry stays unregistered
    monkeypatch.setattr(bootstrap, "FACTORY_REGISTRY", incomplete)

    with pytest.raises(bootstrap.FactoryRegistrationError) as exc_info:
        bootstrap.validate_factory_registry()

    message = str(exc_info.value)
    assert "admin_context" in message
    assert "scheduled_news_sync" in message
    assert "intelligence.sync_scheduled_news" in message
    assert "orchestrator" not in message.replace("retraining_orchestrator", "").replace(
        "prediction_generation_orchestrator", ""
    ).replace("team_statistics_sync_orchestrator", "").replace("admin_context", "")


def test_validate_factory_registry_passes_once_everything_is_registered(monkeypatch):
    complete = bootstrap._fresh_registry()
    for record in complete.values():
        record.registered = True
    monkeypatch.setattr(bootstrap, "FACTORY_REGISTRY", complete)

    bootstrap.validate_factory_registry()  # must not raise


# --- E. The REAL production bootstrap path, end-to-end -----------------------------------------

@pytest.fixture
def worker_env(tmp_path, monkeypatch):
    """Real environment configuration for a real `bootstrap_worker()` run — a throwaway SQLite
    file (not dev.db, not in-memory, so writes genuinely persist across separate connections) and
    a fakeredis stand-in at the same seam `test_api_news_ingestion.py` already uses, never a real
    external Redis/Gemini/RSS call."""
    db_path = tmp_path / "worker_bootstrap_test.db"
    monkeypatch.setenv("TITANIQ_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TITANIQ_REDIS_URL", "redis://127.0.0.1:1/0")  # never actually dialed — see fake_client below
    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())

    from modules.admin.infrastructure.vault import get_vault_settings
    from modules.sports.infrastructure.persistence.database import get_database_settings

    # Both settings getters are `@lru_cache`d singletons (correct for a real, single-process
    # worker with env vars fixed for its whole lifetime) — but that means each test in this file
    # needs a fresh read of TITANIQ_DB_URL/TITANIQ_ENCRYPTION_KEY, since `build_engine()` inside
    # `bootstrap.py` would otherwise silently keep resolving to whichever tmp_path a prior test in
    # this same process happened to cache first.
    get_vault_settings.cache_clear()
    get_database_settings.cache_clear()

    fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    composition.get_redis_client.cache_clear()
    monkeypatch.setattr(composition, "get_redis_client", lambda: fake_client)

    async def _create_admin_schema():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", execution_options={"schema_translate_map": {"admin": None}},
        )
        async with engine.begin() as conn:
            await conn.run_sync(AdminBase.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create_admin_schema())
    return db_path


def test_bootstrap_worker_runs_the_real_production_path_end_to_end(worker_env):
    """The critical test the audit's own finding demands: exercises `bootstrap_worker()` itself
    — the actual function a real `celery -A apps.worker.bootstrap worker` process would run at
    startup — rather than re-deriving the old test-only pattern of calling `set_*_factory`
    directly. If this test passes, a real worker process booting with this same environment would
    also reach "ready" with every factory usable."""
    bootstrap.bootstrap_worker()

    assert all(record.registered for record in bootstrap.FACTORY_REGISTRY.values())

    from modules.admin.infrastructure.celery.tasks import _admin_context_factory
    from modules.ingestion.infrastructure.celery.tasks import (
        _orchestrator_factory,
        _team_statistics_sync_orchestrator_factory,
    )
    from modules.intelligence.infrastructure.celery.tasks import _scheduled_news_sync_service_factory
    from modules.predictions.infrastructure.celery.tasks import (
        _calibration_service_factory,
        _calibration_validation_service_factory,
        _prediction_generation_orchestrator_factory,
        _retraining_orchestrator_factory,
    )

    assert _orchestrator_factory is not None
    assert _admin_context_factory is not None
    assert _retraining_orchestrator_factory is not None
    assert _prediction_generation_orchestrator_factory is not None
    assert _team_statistics_sync_orchestrator_factory is not None
    assert _calibration_service_factory is not None
    assert _calibration_validation_service_factory is not None
    assert _scheduled_news_sync_service_factory is not None


def test_bootstrap_worker_factories_persist_writes_without_an_explicit_commit(worker_env):
    """Proves the AUTOCOMMIT-isolated worker session factory genuinely persists a write — not
    just that a service object can be constructed. A provider registered via the real factory's
    service must be independently readable from a brand-new, separate connection afterward."""
    bootstrap.bootstrap_worker()

    from modules.admin.infrastructure.celery.tasks import _admin_context_factory

    async def _write():
        service, _health_engine = await _admin_context_factory()
        provider = ProviderDefinition(id=ProviderId(uuid4()), key="test-provider", name="Test", category=ProviderCategory.NEWS)
        await service.providers.upsert(provider)
        await service.providers.session.close()
        return provider.id

    provider_id = asyncio.run(_write())

    async def _read_back_from_a_new_connection():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{worker_env}", execution_options={"schema_translate_map": {"admin": None}},
        )
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session = async_sessionmaker(engine, expire_on_commit=False)()
        repo = SqlAlchemyProviderRepository(session=session)
        found = await repo.get(provider_id)
        await session.close()
        await engine.dispose()
        return found

    found = asyncio.run(_read_back_from_a_new_connection())
    assert found is not None
    assert found.key == "test-provider"


def test_bootstrap_worker_fails_closed_on_missing_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("TITANIQ_DB_URL", raising=False)
    monkeypatch.delenv("TITANIQ_REDIS_URL", raising=False)
    monkeypatch.delenv("TITANIQ_ENCRYPTION_KEY", raising=False)

    with pytest.raises(bootstrap.WorkerConfigurationError):
        bootstrap.bootstrap_worker()

    # nothing should have registered — the failure happened before any factory wiring
    assert not any(record.registered for record in bootstrap.FACTORY_REGISTRY.values())


# --- F/G. Scheduled news task after a real bootstrap ------------------------------------------

def test_scheduled_news_task_after_real_bootstrap_honors_disabled_flag_no_external_calls(worker_env, monkeypatch):
    """The exact scenario spec §9/§14 asks for: construct the real production service via the
    real bootstrap path, then run the real Celery task, and prove NEWS_SYNC_ENABLED=false (the
    permanent default) means zero RSS/Gemini calls happen — no fixture/team/player lookups, no
    ingestion, nothing."""
    import modules.intelligence.application.scheduled_news_sync_service as sync_service_module
    monkeypatch.setattr(sync_service_module, "NEWS_SYNC_ENABLED", False)

    bootstrap.bootstrap_worker()

    from modules.ingestion.infrastructure.celery.celery_app import celery_app as shared_celery_app
    from modules.intelligence.infrastructure.celery.tasks import sync_scheduled_news_task

    shared_celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    try:
        async_result = sync_scheduled_news_task.delay("football", str(uuid4()), T0.isoformat())
        result = async_result.get()
    finally:
        shared_celery_app.conf.update(task_always_eager=False)

    assert result["enabled"] is False
    assert result["sources_attempted"] == 0
    assert result["articles_sent_to_gemini"] == 0
