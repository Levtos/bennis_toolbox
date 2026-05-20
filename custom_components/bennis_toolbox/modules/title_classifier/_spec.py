"""HA-freie Spec-Deklaration für Title Classifier."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    NUMBER = "number"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="title_classifier",
    name="Title Classifier",
    description="Stabile Enums aus volatilen Titeln (media / game / activity)",
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.NUMBER),
    has_panel=True,
    has_websocket=True,
    has_services=True,
    icon="mdi:tag-multiple",
)
