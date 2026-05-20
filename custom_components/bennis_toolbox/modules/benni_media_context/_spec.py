"""HA-freie Spec-Deklaration für Benni Media Context."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_media_context",
    name="Benni Media Context",
    description=(
        "Medien-/Player-Kontext mit Decision-Logik: Context, Subcontext, Device, "
        "Gaming Source/Platform, Headset/Entertainment/Quiet/Subwoofer."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:music-note",
)
