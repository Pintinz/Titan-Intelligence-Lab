"""Shared safeguard for one-off scripts that mutate model lifecycle state, training data, or
bulk records — retraining, champion promotion/retirement, backfills, deletions. Real incident
(2026-08-27): `backfill_match_winner_training_data.py`'s own champion-retirement step ran without
anyone being able to see, from the script invocation itself, which database it was about to
touch — it happened to be local, but the exact same command against a misconfigured shell would
have retired a live production champion with no confirmation at all.

Call `require_confirmation_outside_development()` once, near the top of `main()`, in any script
that promotes/retires/deletes/bulk-writes. It's a no-op in development (the default, matching
`modules.sports.infrastructure.persistence.database.Environment`'s own safe default); in staging
or production it refuses to proceed unless the caller explicitly passes
`--i-know-this-is-production` (or sets `TITANIQ_CONFIRM_PRODUCTION_ACTION=1`), so accidentally
running a destructive script against a real environment takes a deliberate, visible extra step,
not a silent default.
"""

from __future__ import annotations

import sys

from modules.sports.infrastructure.persistence.database import Environment, get_database_settings, get_environment


class ProductionSafetyError(RuntimeError):
    pass


def require_confirmation_outside_development(script_name: str) -> None:
    environment = get_environment()
    if environment is Environment.DEVELOPMENT:
        return

    confirmed = "--i-know-this-is-production" in sys.argv
    if not confirmed:
        import os

        confirmed = os.environ.get("TITANIQ_CONFIRM_PRODUCTION_ACTION") == "1"

    if not confirmed:
        settings = get_database_settings()
        host = _mask(settings.url)
        raise ProductionSafetyError(
            f"\n\n'{script_name}' is a destructive script (model lifecycle, training data, or bulk "
            f"writes) and TITANIQ_ENVIRONMENT={environment.value!r} — target database host: {host}.\n"
            "Refusing to run without explicit confirmation. Re-run with --i-know-this-is-production "
            "(or set TITANIQ_CONFIRM_PRODUCTION_ACTION=1) if this is really what you intend.\n"
        )

    print(f"[{script_name}] CONFIRMED: proceeding against TITANIQ_ENVIRONMENT={environment.value!r}.")


def _mask(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        host = urlsplit(url.replace("+asyncpg", "").replace("+aiosqlite", "")).hostname
    except ValueError:
        return "unknown"
    if not host:
        return "n/a (sqlite)"
    labels = host.split(".")
    return "*****." + ".".join(labels[-2:]) if len(labels) > 2 else host
