"""HA-freie Spec-Deklaration für Cover Policy."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="cover_policy",
    name="Cover Policy",
    description=(
        "Policy-gesteuerte Zielposition für ein Cover (Rollo/Jalousie). "
        "Berechnet Modus, Position, Grund und Blocker; treibt Aktoren nur, "
        "wenn apply_enabled gesetzt ist."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:roller-shade",
)
