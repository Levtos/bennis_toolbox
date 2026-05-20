"""Modul-Contract.

Jedes Toolbox-Modul exportiert in seinem `__init__.py`:

    SPEC: ModuleSpec
    async def async_setup_entry(hass, entry) -> bool
    async def async_unload_entry(hass, entry) -> bool
    async def async_get_entities(hass, entry, platform) -> list[Entity]
    SERVICES: dict[str, ServiceDef]                # optional
    WEBSOCKETS: list[Callable]                     # optional
    async def async_register_panel(hass) -> None   # optional
    class ConfigStep                                # statische Helfer für config_flow

Status-Werte:
- READY   — Modul ist produktiv lauffähig.
- PENDING — Modul ist im Repo skizziert, aber noch nicht End-to-End verdrahtet.
            Erscheint im UI mit Hinweis "noch nicht verfügbar". Wird beim
            Setup als no-op behandelt.
- STUB    — Platzhalter ohne Logik. Erscheint im UI ausgegraut.
- HIDDEN  — wird nicht angezeigt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.const import Platform


class ModuleStatus(str, Enum):
    READY = "ready"
    PENDING = "pending"
    STUB = "stub"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    name: str
    description: str
    status: ModuleStatus = ModuleStatus.PENDING
    platforms: tuple["Platform", ...] = field(default_factory=tuple)
    has_panel: bool = False
    has_websocket: bool = False
    has_services: bool = False
    icon: str = "mdi:puzzle"
