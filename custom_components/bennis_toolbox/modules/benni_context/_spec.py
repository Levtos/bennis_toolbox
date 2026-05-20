"""HA-freie Spec-Deklaration für Benni Context."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_context",
    name="Benni Context",
    description=(
        "Fachlicher Owner für presence / bio / day / activity / master-context. "
        "Konsumiert Wake-Planner-Outputs als HA-Entities, ohne deren Logik neu zu implementieren."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:home-account",
)
