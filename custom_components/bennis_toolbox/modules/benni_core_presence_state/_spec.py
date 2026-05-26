"""HA-freie Spec-Deklaration für Benni Core · Presence State.

Drittes der drei "Herzen" der neuen benni_core-Architektur (nach day_state
und user_state). Implementiert die Presence-Logik (zuhause / abwesend /
bei_eltern) plus Heimband, Transition-Kontext und Preheat nach Lastenheft
Context State v1.1 §4.2-4.5 und R-PS-01..R-PS-11.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_core_presence_state",
    name="Benni Core · Presence State",
    description=(
        "Räumlicher Kontext (zuhause/abwesend/bei_eltern + Heimband + "
        "Transition + Preheat) laut Lastenheft Context State v1.1. "
        "GPS-Hierarchie mit Freshness-Fallback, Home-Gate-Stabilisierung "
        "60s/150s, WLAN als Halte-Signal, bei_eltern via WLAN-Abwesenheit "
        "im Heimbereich, Preheat über Ring oder Quellzonen."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=False,
    icon="mdi:map-marker",
)
