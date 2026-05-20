"""Modul: Notification Router.

Status: PENDING — Spec ist registriert, die fachliche Logik ist im Repo
unter `_reference/notification_router/` als Referenz vorhanden, aber noch nicht in die
neue Toolbox-Architektur portiert. Setup ist no-op; ein Config-Entry kann
erstellt werden, registriert aber keine Entities und keine Services.

Port-Anleitung: siehe docs/module_adapter.md.
"""

from __future__ import annotations

from ..base import ModuleSpec, ModuleStatus

SPEC = ModuleSpec(
    module_id="notification_router",
    name="Notification Router",
    description="Routing/Throttling von Notifications",
    status=ModuleStatus.PENDING,
    platforms=(),
    icon="mdi:bell-cog",
)
