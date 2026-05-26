"""HA-freie Spec-Deklaration für Benni Core · User State.

Zweites der drei "Herzen" der neuen benni_core-Architektur (nach
day_state). Verantwortet den Bio-State (sleep/waking/awake) plus
Sleep-/Wake-Timestamps und abgeleitete Dauern, laut Lastenheft
Context State v1.1 §4.1 und R-US-01..R-US-07.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_core_user_state",
    name="Benni Core · User State",
    description=(
        "Bio-State-Maschine (sleep/waking/awake) laut Lastenheft Context "
        "State v1.1. Konsumiert Wake-Trigger (PC, PS5, Fenster, Kaffee) "
        "und Day State (master_phase-Gate), persistiert Bio-State über "
        "HA-Restarts. Liefert Bio-State + Sleep-/Wake-Timestamps + Dauern."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR,),
    has_services=True,
    icon="mdi:bed",
)
