"""Status-Erkennung für Teilintegrationen.

Wir lesen den globalen HA-State, NICHT die Module der Teilintegrationen direkt.
Damit bleibt die Dachintegration entkoppelt: kein Import, kein harter
Abhängigkeitsgraph. Wenn eine Teilintegration nicht installiert ist, sehen
wir das einfach an `loaded=False`.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import KNOWN_MEMBERS, LEGACY_DOMAINS


@dataclass(slots=True)
class MemberStatus:
    domain: str
    name: str
    description: str
    installed: bool
    loaded: bool
    config_entries: int
    version: str | None
    notes: list[str]

    @property
    def healthy(self) -> bool:
        # Healthy = installiert UND (kein Config-Flow nötig ODER mindestens 1 Entry geladen)
        if not self.installed:
            return False
        if not self.loaded:
            return False
        return True

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "name": self.name,
            "description": self.description,
            "installed": self.installed,
            "loaded": self.loaded,
            "config_entries": self.config_entries,
            "version": self.version,
            "healthy": self.healthy,
            "notes": list(self.notes),
        }


async def collect_member_status(hass: HomeAssistant) -> list[MemberStatus]:
    """Sammle Status für jede bekannte Teilintegration."""
    results: list[MemberStatus] = []
    for domain, name, description in KNOWN_MEMBERS:
        notes: list[str] = []
        version: str | None = None
        installed = False
        try:
            integration = await async_get_integration(hass, domain)
            installed = True
            version = getattr(integration, "version", None)
            version = str(version) if version is not None else None
        except Exception:  # noqa: BLE001 - Integration nicht vorhanden ist erwartbar
            notes.append("not installed")

        entries = hass.config_entries.async_entries(domain) if installed else []
        loaded = any(getattr(e, "state", None) and str(e.state).endswith("LOADED") for e in entries)
        if installed and not entries:
            notes.append("no config entries")
        if installed and entries and not loaded:
            notes.append("entries not loaded")

        results.append(
            MemberStatus(
                domain=domain,
                name=name,
                description=description,
                installed=installed,
                loaded=loaded,
                config_entries=len(entries),
                version=version,
                notes=notes,
            )
        )
    # Legacy-Erkennung: nur warnen, nichts zu finalen Mitgliedern hinzufügen.
    for legacy_domain, new_domain in LEGACY_DOMAINS.items():
        legacy_entries = hass.config_entries.async_entries(legacy_domain)
        if not legacy_entries:
            continue
        for member in results:
            if member.domain == new_domain:
                member.notes.append(
                    f"legacy domain detected: {legacy_domain} "
                    f"({len(legacy_entries)} config entry/entries) — remove via UI"
                )
                break
    return results
