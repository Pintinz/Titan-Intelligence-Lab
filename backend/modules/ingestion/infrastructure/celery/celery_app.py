"""Celery application (docs/roadmap.md Milestone 5 "Background Processing"). Redis as both
broker and result backend — already a required dependency, no new infra service to run.

``task_always_eager`` stays False by default (real deployments run `celery -A ... worker`
against this app) but tests flip it on via ``configure_for_tests()`` so task bodies execute
synchronously in-process, the standard way to test Celery task logic without a running broker
or worker (docs/decisions.md — same "test the real code, fake/skip the transport" pattern used
throughout this codebase, applied to task execution instead of a network call).
"""

from __future__ import annotations

from celery import Celery
from celery.signals import task_failure

from modules.features.infrastructure.online.redis_feature_store import get_redis_settings
from modules.ingestion.infrastructure.celery.beat_schedule import BEAT_SCHEDULE
from modules.ingestion.infrastructure.celery.dead_letter import record_dead_letter


def _default_broker_url() -> str:
    # TITANIQ_REDIS_URL is only required to actually connect to a broker (a real worker, or a
    # non-eager task submission) — importing this module (e.g. at test collection time) must
    # not hard-fail just because that env var isn't set yet in the current environment.
    try:
        return get_redis_settings().url
    except Exception:
        return "redis://localhost:6379/0"


celery_app = Celery("titaniq_ingestion")

celery_app.conf.update(
    broker_url=_default_broker_url(),
    result_backend=_default_broker_url(),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # a task lost mid-execution (worker crash) is redelivered, not dropped
    worker_prefetch_multiplier=1,  # don't let one worker hoard tasks other workers could run
    task_time_limit=600,
    # Milestone 24: previously routed ingestion.*/admin.* to separate "live"/"default" queues, but
    # no production worker invocation ever consumed them (confirmed by repo-wide search — the only
    # consumer was a one-off manual `-Q celery,live,default` launch in M23). That silently stranded
    # every routed task indefinitely. Removed rather than fixed-by-flag: a `celery worker` started
    # with no `-Q` argument (the only invocation this project has ever documented or scripted)
    # already consumes the default queue every task now uses, so this is correct with zero
    # deployment changes required, not a new mechanism to remember to configure.
    task_default_retry_delay=30,
    beat_schedule=BEAT_SCHEDULE,
)


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, einfo=None, **extra):
    """Routes a task to the dead letter queue once its retries are truly exhausted — a
    mid-retry failure just retries (Celery's own mechanism), this only fires on the final one."""
    request = getattr(sender, "request", None)
    retries = getattr(request, "retries", 0) if request else 0
    max_retries = getattr(sender, "max_retries", 0) if sender else 0
    if retries >= max_retries:
        record_dead_letter(
            task_name=sender.name if sender else "unknown",
            task_id=task_id or "unknown",
            args=list(args or []),
            kwargs=dict(kwargs or {}),
            error=str(exception),
        )


def configure_for_tests() -> None:
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True, broker_url="memory://", task_store_eager_result=True)
