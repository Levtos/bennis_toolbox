"""Auto-detection helpers for the Plug Policy add/edit device flow.

When the user picks ``switch.living_pc_plug`` we derive the base slug
``living_pc_plug`` and look in ``hass.states`` for canonical sister
entities so the user does not have to type IDs:

- ``sensor.<slug>_power``    → power_entity suggestion
- ``sensor.<slug>_battery``  → battery_entity suggestion (mainly tablets)

Voltage/current/energy are commonly present but the policy engine does
not act on them — they're surfaced in the result as "siblings" so the
flow can mention them in the description without forcing extra inputs.

Pure logic; no homeassistant imports at module level. ``hass`` is duck-
typed (anything that exposes ``states.async_entity_ids()`` works).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SensorSuggestion:
    """Result of an auto-detection pass for one switch entity."""

    base_slug: str
    power_entity: str | None
    battery_entity: str | None
    siblings: tuple[str, ...]  # voltage/current/energy if present (informational)


# Priority is significant — Einhornzentrale wires every plug through an
# `_atomic` aggregator entity that smooths the raw power reading, so we
# prefer that over the underlying raw sensor. Battery follows the same
# convention. Raw `_power`/`_battery` stay as canonical fallback so
# vanilla setups still get a useful suggestion.
_SUFFIX_POWER = ("_power_atomic", "_power", "_active_power", "_power_w")
_SUFFIX_BATTERY = (
    "_battery_atomic", "_battery", "_battery_level", "_battery_percent",
)
_SUFFIX_SIBLINGS = (
    "_voltage", "_current", "_energy", "_energy_total", "_today_energy",
)


def base_slug(switch_entity: str | None) -> str | None:
    """Strip the domain prefix from ``switch.living_pc_plug`` → ``living_pc_plug``.

    Returns None for empty input. If no dot is present the input is
    treated as a slug already so users typing a partial value still get
    suggestions.
    """
    if not switch_entity:
        return None
    s = switch_entity.strip()
    if not s:
        return None
    return s.split(".", 1)[1] if "." in s else s


def _entity_ids(hass) -> list[str]:
    """Return all sensor entity_ids known to HA.

    Falls back to an empty list if hass exposes no states API (tests).
    """
    states = getattr(hass, "states", None)
    if states is None:
        return []
    # Prefer async_entity_ids when present; otherwise list states.
    aei = getattr(states, "async_entity_ids", None)
    if callable(aei):
        try:
            return list(aei("sensor"))
        except TypeError:
            return [eid for eid in aei() if eid.startswith("sensor.")]
    listing = getattr(states, "async_all", None)
    if callable(listing):
        return [s.entity_id for s in listing() if s.entity_id.startswith("sensor.")]
    return []


def _first_match(candidates: list[str], slug: str, suffixes: tuple[str, ...]) -> str | None:
    """Return the first sensor whose object_id == ``<slug><suffix>``.

    The order in ``suffixes`` is significance order — ``_power`` wins
    over ``_active_power`` when both exist, matching what most plug
    integrations expose.
    """
    by_object: dict[str, str] = {}
    for eid in candidates:
        _, _, obj = eid.partition(".")
        by_object[obj] = eid
    for suf in suffixes:
        eid = by_object.get(f"{slug}{suf}")
        if eid:
            return eid
    return None


def suggest_for_switch(hass, switch_entity: str | None) -> SensorSuggestion:
    """Pure suggestion pass; never raises, always returns a result.

    The caller decides whether to apply the result as a *default* in
    the form schema. Never override an explicit user value.
    """
    slug = base_slug(switch_entity)
    if not slug:
        return SensorSuggestion(base_slug="", power_entity=None, battery_entity=None, siblings=())
    sensors = _entity_ids(hass)
    power = _first_match(sensors, slug, _SUFFIX_POWER)
    battery = _first_match(sensors, slug, _SUFFIX_BATTERY)

    by_object = {eid.partition(".")[2]: eid for eid in sensors}
    siblings: list[str] = []
    for suf in _SUFFIX_SIBLINGS:
        eid = by_object.get(f"{slug}{suf}")
        if eid:
            siblings.append(eid)
    return SensorSuggestion(
        base_slug=slug,
        power_entity=power,
        battery_entity=battery,
        siblings=tuple(siblings),
    )


# ---------------------------------------------------------------------------
# Kind-aware field visibility.
#
# We keep the engine fully tolerant of missing keys — the schema controls
# only what the user *sees*. ``visible_fields_for_kind`` returns the
# concrete CONF_* keys that should appear in the "advanced" step for a
# given kind/policy combination. The basics step (name/switch/policy/
# kind) is always shown; the sensors step is always shown.
# ---------------------------------------------------------------------------


# Field group definitions, expressed as raw CONF strings so this file
# stays HA-free.
_COMMON_POWER_FIELDS = (
    "active_threshold",
    "idle_threshold",
    "deadband_lower",
    "deadband_upper",
    "stable_off_seconds",
    "unknown_behavior",
    "never_cut_when_active",
    "manual_on_cooldown_seconds",
)
_TABLET_FIELDS = ("tablet_low", "tablet_high", "manual_on_cooldown_seconds")
_DIFFUSER_FIELDS = (
    "diffuser_on_minutes", "diffuser_off_minutes", "manual_on_cooldown_seconds",
)
_DOCK_FIELDS = _COMMON_POWER_FIELDS + ("wake_signal_only",)


def advanced_fields_for_kind(kind: str, policy: str) -> tuple[str, ...]:
    """Return the CONF_* keys to render on the advanced step.

    Engine logic is unchanged regardless of what we render — missing
    keys fall back to defaults inside engine.py.
    """
    k = (kind or "generic").lower()
    if k == "tablet":
        fields: tuple[str, ...] = _TABLET_FIELDS
    elif k == "diffuser":
        fields = _DIFFUSER_FIELDS
    elif k == "h14_dock":
        fields = _DOCK_FIELDS
    else:
        # pc, denon, appliance, coffee_maker, bias_light, generic
        fields = _COMMON_POWER_FIELDS
    # allowed_contexts is only meaningful for Schedule-Context policy.
    if (policy or "").upper() == "SC":
        fields = fields + ("allowed_contexts",)
    return fields


def sensors_for_kind(kind: str) -> tuple[str, ...]:
    """Sensor fields shown on the "sensors" step for a given kind."""
    k = (kind or "generic").lower()
    if k == "tablet":
        # A tablet plug usually has both — power for "is being used", battery
        # for charge level; battery is the policy-relevant one.
        return ("power_entity", "battery_entity")
    return ("power_entity",)
