"""Cross-provider team identity mapping (football-data.org <-> existing TitanIQ teams).

football-data.org uses its own numeric team ids, unrelated to api-football's — and there is no
fuzzy/name-based matching anywhere in the core reconciliation pipeline
(``EntityReconciliationService``), which only ever resolves identity via an exact
``(provider, external_id)`` lookup. Without an explicit mapping, a football-data.org-sourced
fixture's ``home_team_ref``/``away_team_ref`` would raise ``ReconciliationDependencyError`` (team
never seen under that provider+id), and a naively auto-reconciled football-data.org team record
would create a duplicate ``Team`` row for a club TitanIQ already has.

This service closes that gap with a "suggest, then admin confirms" flow — no silent auto-merge
(confirmed design decision, see the football-data.org integration plan). ``suggest_mappings`` is
a pure, read-only name-normalization matcher; ``confirm_mappings`` is the only thing that writes,
and it writes through the *existing*, already-public ``EntityReconciliationService.ref_index``
field — no change needed to ``entity_reconciliation_service.py`` for this part.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from modules.ingestion.domain.entities import ProviderRefIndexEntry
from modules.ingestion.domain.value_objects import EntityKind
from modules.ingestion.ports.repositories import ProviderRefIndexRepositoryPort
from modules.sports.ports.provider_gateway import ProviderTeamRecord

# Common club-name suffix noise that differs between how football-data.org and api-football
# render the same real club (e.g. "Chelsea FC" vs "Chelsea") — stripping it before comparison
# is what lets an otherwise-identical name match; it is not a claim that any given club's
# *official* name includes or excludes these words.
_SUFFIX_PATTERN = re.compile(r"\b(fc|cf|sc|afc|cfc)\b", re.IGNORECASE)


def _normalize_name(name: str) -> str:
    """Lowercases, strips diacritics, and removes common club-suffix noise so e.g.
    "Bayer 04 Leverkusen" and "Bayer Leverkusen" or "Chelsea FC" and "Chelsea" compare equal."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    without_suffixes = _SUFFIX_PATTERN.sub("", ascii_name)
    return re.sub(r"\s+", " ", without_suffixes).strip().lower()


@dataclass(frozen=True)
class ExistingTeamRef:
    """A TitanIQ team as seen by this service — deliberately not the full ``Team`` domain
    entity, since suggestion-matching only ever needs id + name."""

    id: str
    name: str


@dataclass(frozen=True)
class TeamMappingSuggestion:
    football_data_org_team_id: str
    football_data_org_team_name: str
    suggested_titaniq_team_id: str | None
    suggested_titaniq_team_name: str | None
    confidence: float  # 1.0 = exact normalized-name match, 0.0 = no candidate found at all


@dataclass(frozen=True)
class ConfirmedTeamMapping:
    football_data_org_team_id: str
    titaniq_team_id: str


@dataclass
class CrossProviderTeamMappingService:
    ref_index: ProviderRefIndexRepositoryPort

    def suggest_mappings(
        self, fd_teams: list[ProviderTeamRecord], existing_teams: list[ExistingTeamRef]
    ) -> list[TeamMappingSuggestion]:
        """Read-only — never writes anything. Each football-data.org team gets at most one
        suggested existing-team match, by exact normalized-name equality; ties (two existing
        teams normalizing to the same name) keep whichever was seen first in ``existing_teams``,
        since that's ambiguous enough that a human reviewing the suggestion should decide."""
        by_normalized_name: dict[str, ExistingTeamRef] = {}
        for team in existing_teams:
            by_normalized_name.setdefault(_normalize_name(team.name), team)

        suggestions = []
        for fd_team in fd_teams:
            match = by_normalized_name.get(_normalize_name(fd_team.name))
            suggestions.append(
                TeamMappingSuggestion(
                    football_data_org_team_id=fd_team.external_ref.external_id,
                    football_data_org_team_name=fd_team.name,
                    suggested_titaniq_team_id=match.id if match else None,
                    suggested_titaniq_team_name=match.name if match else None,
                    confidence=1.0 if match else 0.0,
                )
            )
        return suggestions

    async def confirm_mappings(self, mappings: list[ConfirmedTeamMapping]) -> None:
        """The only write path. Each confirmed pair becomes a second ``provider_ref_index`` row
        pointing at the same internal ``Team`` id api-football's own ref already points to —
        ``provider_ref_index`` is unique on ``(provider, external_id, entity_kind)``, not on
        ``entity_id``, so this coexists with the existing api-football ref rather than replacing
        it (see ``ProviderRefIndexEntry``'s docstring)."""
        for mapping in mappings:
            await self.ref_index.upsert(
                ProviderRefIndexEntry(
                    provider="football_data_org",
                    external_id=mapping.football_data_org_team_id,
                    entity_kind=EntityKind.TEAM,
                    entity_id=mapping.titaniq_team_id,
                )
            )
