"""Modul: Plug Policy Engine.

Status: PENDING — Spec ist registriert, die fachliche Logik ist im Repo
unter `_reference/plug_policy_engine/` als Referenz vorhanden, aber noch nicht in die
neue Toolbox-Architektur portiert. Setup ist no-op; ein Config-Entry kann
erstellt werden, registriert aber keine Entities und keine Services.

Port-Anleitung: siehe docs/module_adapter.md.
"""

from __future__ import annotations

from ..base import ModuleSpec, ModuleStatus

SPEC = ModuleSpec(
    module_id="plug_policy_engine",
    name="Plug Policy Engine",
    description="Policy-getriebenes Schalten von Steckdosen",
    status=ModuleStatus.PENDING,
    platforms=(),
    icon="mdi:power-socket-de",
)
