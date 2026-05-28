"""HA-freie Spec-Deklaration für Benni Core · Devices.

Foundation-Modul: konsolidiert pro physischem Gerät rohe HA-Entitäten
zu einer typisierten Wahrheit mit Standard-Attribut-Schema. Multi-Instance:
ein Config-Entry pro Device.

Lastenheft: einhornzentrale/docs/lastenhefte/reviewed/device_core/lastenheft.md (v0.2)
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="benni_core_devices",
    name="Benni Core · Devices",
    description=(
        "Typisierte Geräte-Abstraktion: pro physischem Gerät EIN Sensor mit "
        "konsolidiertem State + Standard-Attributen. Ersetzt die YAML-Atomic-"
        "Schicht. Multi-Instance — eine Config-Entry pro Device. Liefert "
        "powered, power_state (aus Watt-Buckets), available, override-Status."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:devices",
)
