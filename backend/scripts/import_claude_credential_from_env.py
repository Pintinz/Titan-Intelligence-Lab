"""One-time activation for the Claude (Anthropic) fallback adapter (`claude_adapter.py`,
`TextIntelligenceRouter`'s `fallback_adapters`): reads `TITANIQ_CLAUDE_API_KEY` from the process
environment exactly once, encrypts it into the credential vault, and registers the "claude"
provider — the exact same `ProviderManagementService.import_from_env` migration path already used
for every other provider key that started life in `.env` (that method's own docstring: "the DB is
the only source of truth from that point on; nothing keeps reading the env var on subsequent
requests"). Never prints or logs the key itself.

Usage (set the env var first, in your own shell/`.env` — this script only reads it, it is never
given the key any other way):

    python -m scripts.import_claude_credential_from_env

Idempotent: re-running with the same env var re-credentials the existing "claude" provider rather
than duplicating it (`import_from_env`'s own contract). Until this script is run, `ClaudeAdapter`
sits in the fallback chain with no usable credential and is simply skipped —
`get_text_intelligence_provider` (composition.py) already wires it either way, so nothing else
needs to change once a real key is available.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from modules.admin.application.provider_management_service import EnvironmentVariableNotSetError, ProviderManagementService
from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import ProviderCategory
from modules.intelligence.infrastructure.claude_adapter import ClaudeAdapter


async def import_claude_credential(
    admin_service: ProviderManagementService, now: datetime,
) -> tuple[ProviderDefinition, ProviderCredential] | None:
    """Pure logic over an injected `ProviderManagementService` — real DB-backed service in
    `main()` below, an in-memory one in tests. Returns `None` (never raises) when the env var
    genuinely isn't set — an honest "nothing to do," not an error, since not every environment
    needs Claude configured."""
    try:
        return await admin_service.import_from_env(
            "TITANIQ_CLAUDE_API_KEY",
            ClaudeAdapter.provider_key,
            "Claude (Anthropic)",
            ProviderCategory.AI,
            now=now,
            credential_label="imported-from-env",
        )
    except EnvironmentVariableNotSetError:
        return None


async def main() -> None:
    from apps.api.composition import build_provider_management_service, get_engine

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        admin_service = build_provider_management_service(session)
        result = await import_claude_credential(admin_service, datetime.now(timezone.utc))

        if result is None:
            print(
                "TITANIQ_CLAUDE_API_KEY is not set — nothing to import. Set it in your "
                "environment (never pasted into chat/code) and re-run this script."
            )
            return

        await session.commit()
        provider, _credential = result
        print(f"Registered/re-credentialed provider '{provider.key}' ({provider.name}), id={provider.id}.")


if __name__ == "__main__":
    asyncio.run(main())
