"""Modul-Registry der Toolbox.

Jedes Modul wohnt unter `modules/<module_id>/` und exportiert ein
`SPEC: ModuleSpec` sowie die Funktionen aus `base.ModuleProtocol`. Die
Registry lädt nichts vor; Module werden erst importiert, wenn sie auch
wirklich aktiviert oder im Config-Flow angefragt werden — so fällt eine
Stub-Implementation nicht auf den Rest.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Final

from .base import ModuleSpec, ModuleStatus

_LOGGER = logging.getLogger(__name__)

# Reihenfolge = Anzeigereihenfolge im Config-Flow-Selector.
REGISTERED_MODULE_IDS: Final[tuple[str, ...]] = (
    "benni_context",
    "benni_media_context",
    "notification_router",
    "plug_policy_engine",
    "title_classifier",
    "wake_planner",
    "maw",
    "stash_ha",
)


def load_module(module_id: str) -> ModuleType:
    """Modul-Package laden. Wirft `ModuleNotFoundError` für unbekannte IDs."""
    if module_id not in REGISTERED_MODULE_IDS:
        raise ModuleNotFoundError(f"unknown toolbox module: {module_id}")
    return importlib.import_module(f"{__name__}.{module_id}")


def get_spec(module_id: str) -> ModuleSpec:
    mod = load_module(module_id)
    spec = getattr(mod, "SPEC", None)
    if not isinstance(spec, ModuleSpec):
        raise RuntimeError(
            f"module '{module_id}' does not export a valid SPEC: ModuleSpec"
        )
    return spec


def all_specs() -> list[ModuleSpec]:
    """Specs aller registrierten Module, defensiv: defekte Module werden
    übersprungen statt das ganze Setup zu killen."""
    out: list[ModuleSpec] = []
    for mid in REGISTERED_MODULE_IDS:
        try:
            out.append(get_spec(mid))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("module %s failed to expose SPEC: %s", mid, err)
    return out


def selectable_specs() -> list[ModuleSpec]:
    """Module, die der Nutzer im Config-Flow auswählen darf."""
    return [s for s in all_specs() if s.status is not ModuleStatus.HIDDEN]


__all__ = [
    "ModuleSpec",
    "ModuleStatus",
    "REGISTERED_MODULE_IDS",
    "all_specs",
    "get_spec",
    "load_module",
    "selectable_specs",
]
