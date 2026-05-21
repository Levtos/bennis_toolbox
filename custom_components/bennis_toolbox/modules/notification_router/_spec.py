"""HA-freie Spec-Deklaration für Notification Router."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="notification_router",
    name="Notification Router",
    description=(
        "Routet Notifications kontextabhängig (Bio, Activity, Presence, "
        "Headset, Quiet Mode) mit Severity-Promotion, Rate-Limit, Dedupe und DND."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:bell-cog",
)
