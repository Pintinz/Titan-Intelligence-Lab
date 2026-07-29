"""Competition structure contract — every sport plugin declares how its competitions are
organized so generic code (standings, fixture generation) never special-cases a sport by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.sports.domain.value_objects import SeasonStatus


class CompetitionFormat(str, Enum):
    ROUND_ROBIN = "round_robin"
    GROUP_AND_KNOCKOUT = "group_and_knockout"
    KNOCKOUT = "knockout"
    LADDER = "ladder"


@dataclass(frozen=True)
class CompetitionStructure:
    """Declares how a specific competition is organized.

    ``supports_draws`` and ``promotion_relegation`` are the two properties generic code
    (standings computation, fixture generation) needs without knowing the sport — e.g.
    football league play supports draws, knockout table tennis tournaments do not.
    """

    format: CompetitionFormat
    supports_draws: bool
    promotion_relegation: bool = False


# Ordered transitions a season may legally move through. A sport plugin may narrow this
# (e.g. skip straight to COMPLETED) but may never introduce a transition not listed here.
SeasonLifecycleRules: dict[SeasonStatus, tuple[SeasonStatus, ...]] = {
    SeasonStatus.UPCOMING: (SeasonStatus.ACTIVE,),
    SeasonStatus.ACTIVE: (SeasonStatus.COMPLETED,),
    SeasonStatus.COMPLETED: (),
}
