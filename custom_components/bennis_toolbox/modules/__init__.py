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
#
# `benni_core_*` Module bilden gemeinsam das neue Fundament (drei Herzen +
# Device Layer). Sie stehen vorne, weil alle Aggregat-Module darauf aufbauen.
# Bestehende Alt-Module bleiben darunter, bis sie auf das neue Fundament
# migriert sind — siehe memory/toolbox_rebuild_plan.md.
REGISTERED_MODULE_IDS: Final[tuple[str, ...]] = (
    "benni_core_day_state",
    "benni_context",
    "benni_media_context",
    "notification_router",
    "plug_policy_engine",
    "title_classifier",
    "wake_planner",
    "maw",
    "stash_ha",
    "cover_policy",
)


def load_module(module_id: str) -> ModuleType:
    """Modul-Package laden. Wirft `ModuleNotFoundError` für unbekannte IDs."""
    if module_id not in REGISTERED_MODULE_IDS:
        raise ModuleNotFoundError(f"unknown toolbox module: {module_id}")
    return importlib.import_module(f"{__name__}.{module_id}")


def _try_load_spec_module(module_id: str) -> ModuleType | None:
    """Lade `<module>._spec` falls vorhanden — frei von HA-Imports.

    Bevorzugt für Enumeration / Tests: vermeidet das Laden der vollen
    Modul-Runtime nur um an die SPEC zu kommen.
    """
    try:
        return importlib.import_module(f"{__name__}.{module_id}._spec")
    except ModuleNotFoundError:
        return None


def get_spec(module_id: str) -> ModuleSpec:
    if module_id not in REGISTERED_MODULE_IDS:
        raise ModuleNotFoundError(f"unknown toolbox module: {module_id}")
    spec_mod = _try_load_spec_module(module_id)
    if spec_mod is None:
        spec_mod = load_module(module_id)
    spec = getattr(spec_mod, "SPEC", None)
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
