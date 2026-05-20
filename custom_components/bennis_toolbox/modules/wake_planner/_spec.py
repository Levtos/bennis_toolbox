"""Spec-Deklaration des Wake-Planner-Moduls.

Bewusst frei von `homeassistant`-Imports, damit Tooling (Tests, Registry)
die Spec ohne laufende HA-Installation lesen kann.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

# Platform.SENSOR.value == "sensor", Platform.BINARY_SENSOR.value == "binary_sensor"
# — wir verwenden die String-Konstanten direkt, damit kein HA-Import nötig ist.
# Die Umbrella mappt das beim Setup gegebenenfalls auf homeassistant.const.Platform.
class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


# Die echte ModuleSpec-Dataclass importieren wir aus base, das selbst
# HA-frei ist.
from ..base import ModuleSpec, ModuleStatus  # noqa: E402


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="wake_planner",
    name="Wake Planner",
    description="Weckzeiten- und Routinenplanung mit Regeln, Kalender- und Feiertags-Quellen",
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_panel=True,
    has_websocket=True,
    has_services=True,
    icon="mdi:alarm",
)
