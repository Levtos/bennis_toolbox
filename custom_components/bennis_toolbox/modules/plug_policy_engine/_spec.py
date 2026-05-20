"""HA-freie Spec-Deklaration für Plug Policy Engine."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="plug_policy_engine",
    name="Plug Policy Engine",
    description=(
        "Policy-getriebenes Schalten von Steckdosen "
        "(AO/HB/AC/SC/CS/SPECIAL + spezielle Device-Kinds)."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.BINARY_SENSOR),
    has_services=True,
    icon="mdi:power-socket-de",
)
