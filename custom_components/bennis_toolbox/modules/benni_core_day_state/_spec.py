"""HA-freie Spec-Deklaration für Benni Core · Day State.

Erster der drei "Herzen" der neuen benni_core-Architektur:
day_state, context_state, activity_state. Plus später benni_core_devices als
Device Layer.

Spec lebt isoliert in _spec.py damit die Modul-Registry sie ohne vollständigen
HA-Import laden kann (siehe modules/__init__.py).
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_core_day_state",
    name="Benni Core · Day State",
    description=(
        "Tagesphasen-Sensor laut Lastenheft Day State v1.1. Liefert die "
        "aktuelle Detailphase (8 Werte) als State plus Masterphase und "
        "alle Übergangszeiten als Attribute. Konsumiert nur Solar Noon "
        "als externe Eingabe — keine Geräte-Inputs."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR,),
    has_services=False,
    icon="mdi:weather-sunset",
)
