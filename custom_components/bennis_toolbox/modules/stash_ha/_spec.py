"""HA-freie Spec-Deklaration für Stash HA."""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..base import ModuleSpec, ModuleStatus


class _P(str, Enum):
    SENSOR = "sensor"
    IMAGE = "image"
    MEDIA_PLAYER = "media_player"


SPEC: Final[ModuleSpec] = ModuleSpec(
    module_id="stash_ha",
    name="Stash HA",
    description=(
        "Stash-Mediaplayer-Bridge: GraphQL-Client, Library-Statistik-Coordinator, "
        "Playback-Erkennung über play_duration-Delta, Cover-Image und Display-Only "
        "Media-Player."
    ),
    status=ModuleStatus.READY,
    platforms=(_P.SENSOR, _P.IMAGE, _P.MEDIA_PLAYER),
    has_services=True,
    icon="mdi:movie-play",
)
