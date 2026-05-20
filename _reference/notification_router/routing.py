"""Pure, side-effect-free routing engine.

Kept independent from Home Assistant so the decision logic is unit-testable
without requiring a HASS instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .const import (
    ACT_PRIVATE_TIME, ACT_WORK_HOME,
    ALL_ROUTES,
    BIO_AWAKE, BIO_SLEEP, BIO_WAKING,
    EC_APPLIANCE_DONE, EC_DEVICE_HEALTH, EC_DOORBELL, EC_LOCK, EC_SECURITY,
    HOME_EQUIVALENT_PRESENCE,
    MODE_CRITICAL, MODE_NORMAL, MODE_SILENT, MODE_SOFT, MODE_URGENT,
    PRES_AWAY,
    ROUTE_BUS_ONLY, ROUTE_DASHBOARD, ROUTE_LIGHT, ROUTE_MEDIA,
    ROUTE_PERSISTENT, ROUTE_PUSH,
    SEV_CRITICAL, SEV_INFO, SEV_NORMAL, SEV_URGENT,
    SEVERITY_ORDER,
)


@dataclass
class Context:
    """Snapshot of all context inputs for a routing decision."""
    bio_state: str | None = None
    activity_state: str | None = None
    presence: str | None = None
    media_active: bool = False
    headset_active: bool = False
    quiet_mode_active: bool = False
    doorbell_state: str | None = None
    opening_safety: str | None = None
    lock_battery_low: bool = False
    dnd_override: bool = False
    in_quiet_hours: bool = False

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_type: str               # event class
    severity: str = SEV_NORMAL
    title: str = ""
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str | None = None


@dataclass
class Decision:
    mode: str
    routes: list[str]
    suppressed_routes: list[str]
    reason: str
    title: str
    message: str
    severity: str
    context: dict[str, Any]
    masked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "routes": self.routes,
            "suppressed_routes": self.suppressed_routes,
            "reason": self.reason,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "context": self.context,
            "masked": self.masked,
        }


def _is_critical(ev: Event) -> bool:
    return ev.severity == SEV_CRITICAL


def _bump_severity_for_class(ev: Event, ctx: Context) -> str:
    """Some event classes self-promote in critical context."""
    sev = ev.severity
    if ev.event_type == EC_SECURITY and SEVERITY_ORDER.get(sev, 0) < SEVERITY_ORDER[SEV_URGENT]:
        # Security warnings always at least urgent.
        sev = SEV_URGENT
    if ev.event_type == EC_DEVICE_HEALTH and ctx.lock_battery_low and sev == SEV_INFO:
        sev = SEV_NORMAL
    return sev


def _severity_to_mode(sev: str) -> str:
    return {
        SEV_INFO: MODE_SOFT,
        SEV_NORMAL: MODE_NORMAL,
        SEV_URGENT: MODE_URGENT,
        SEV_CRITICAL: MODE_CRITICAL,
    }.get(sev, MODE_NORMAL)


def decide(ev: Event, ctx: Context) -> Decision:
    """Return the routing decision for *ev* in *ctx*.

    Pure function: no I/O, no HASS access. Reasoning is encoded in the
    ``reason`` string for debug visibility.
    """
    reasons: list[str] = []
    suppressed: list[str] = []

    sev = _bump_severity_for_class(ev, ctx)
    if sev != ev.severity:
        reasons.append(f"severity bumped from {ev.severity} -> {sev} by class policy")

    is_security = ev.event_type == EC_SECURITY
    is_doorbell = ev.event_type == EC_DOORBELL
    critical = sev == SEV_CRITICAL or is_security and sev == SEV_URGENT

    # Default routes by severity
    routes: list[str] = []
    if sev == SEV_INFO:
        routes = [ROUTE_DASHBOARD, ROUTE_BUS_ONLY]
    elif sev == SEV_NORMAL:
        routes = [ROUTE_PUSH, ROUTE_DASHBOARD]
    elif sev == SEV_URGENT:
        routes = [ROUTE_PUSH, ROUTE_PERSISTENT, ROUTE_MEDIA, ROUTE_DASHBOARD]
    elif sev == SEV_CRITICAL:
        routes = [ROUTE_PUSH, ROUTE_PERSISTENT, ROUTE_MEDIA, ROUTE_LIGHT, ROUTE_DASHBOARD]

    # Doorbell baseline: light + push + media
    if is_doorbell:
        routes = [ROUTE_PUSH, ROUTE_LIGHT, ROUTE_MEDIA, ROUTE_DASHBOARD]
        reasons.append("doorbell baseline routes")

    # Appliance done: low-key push
    if ev.event_type == EC_APPLIANCE_DONE and sev in (SEV_INFO, SEV_NORMAL):
        routes = [ROUTE_PUSH, ROUTE_DASHBOARD]
        reasons.append("appliance_done -> push+dashboard")

    # ----- Context filters -----

    def drop(route: str, why: str) -> None:
        if route in routes:
            routes.remove(route)
            suppressed.append(route)
            reasons.append(f"dropped {route}: {why}")

    # Sleep policy: only critical breaks through loudly.
    if ctx.bio_state == BIO_SLEEP and not critical:
        drop(ROUTE_MEDIA, "bio_state=sleep, audio suppressed")
        drop(ROUTE_LIGHT, "bio_state=sleep, no ring effect")
        if sev in (SEV_INFO, SEV_NORMAL):
            drop(ROUTE_PUSH, "bio_state=sleep, defer non-critical push")
            drop(ROUTE_PERSISTENT, "bio_state=sleep, defer persistent")
            if ROUTE_DASHBOARD not in routes:
                routes.append(ROUTE_DASHBOARD)
            if ROUTE_BUS_ONLY not in routes:
                routes.append(ROUTE_BUS_ONLY)
            reasons.append("sleep+low severity -> deferred to bus/dashboard")

    # Waking: soften
    if ctx.bio_state == BIO_WAKING and not critical:
        drop(ROUTE_MEDIA, "bio_state=waking, soften")

    # Headset active -> prefer light/push over audio
    if ctx.headset_active and not critical:
        drop(ROUTE_MEDIA, "headset_active, audio likely unheard")
        if ROUTE_LIGHT not in routes and sev in (SEV_NORMAL, SEV_URGENT):
            routes.append(ROUTE_LIGHT)
            reasons.append("headset_active -> add light ring")
        if ROUTE_PUSH not in routes:
            routes.append(ROUTE_PUSH)
            reasons.append("headset_active -> ensure push")

    # Quiet mode active -> no audio
    if ctx.quiet_mode_active and not critical:
        drop(ROUTE_MEDIA, "quiet_mode_active")

    # Quiet hours behave similarly
    if ctx.in_quiet_hours and not critical:
        drop(ROUTE_MEDIA, "quiet_hours")
        if sev == SEV_INFO:
            drop(ROUTE_PUSH, "quiet_hours+info")

    # work_home -> less intrusive
    if ctx.activity_state == ACT_WORK_HOME and not critical:
        drop(ROUTE_MEDIA, "work_home, less intrusive")
        if sev == SEV_INFO:
            drop(ROUTE_PUSH, "work_home+info")

    # Media currently playing -> avoid clobbering audio
    if ctx.media_active and not critical:
        drop(ROUTE_MEDIA, "media currently active")

    # Presence away -> ensure push remains; light/media useless
    presence_home_like = ctx.presence in HOME_EQUIVALENT_PRESENCE
    if ctx.presence == PRES_AWAY:
        drop(ROUTE_LIGHT, "presence=abwesend, local light useless")
        drop(ROUTE_MEDIA, "presence=abwesend, local audio useless")
        if ROUTE_PUSH not in routes and sev != SEV_INFO:
            routes.append(ROUTE_PUSH)
            reasons.append("away -> ensure push")
    elif presence_home_like:
        # bei_eltern is home-equivalent: do not escalate as if away.
        pass

    # private_time -> mask details
    masked = False
    title = ev.title
    message = ev.message
    if ctx.activity_state == ACT_PRIVATE_TIME and not critical:
        masked = True
        title = title or "Benachrichtigung"
        # Mask: replace message with generic placeholder for outward-facing routes
        message = "(privater Modus)"
        reasons.append("activity=private_time -> message masked")

    # DND override: only critical / security breaks through
    if ctx.dnd_override and not critical:
        for r in list(routes):
            if r not in (ROUTE_DASHBOARD, ROUTE_BUS_ONLY):
                drop(r, "DND active")

    # Security critical override: ALWAYS push + persistent, even under DND/sleep
    if is_security and sev in (SEV_URGENT, SEV_CRITICAL):
        for must in (ROUTE_PUSH, ROUTE_PERSISTENT):
            if must not in routes:
                routes.append(must)
                if must in suppressed:
                    suppressed.remove(must)
                reasons.append(f"security override -> ensure {must}")

    # Lock low battery (device health) policy: push only, no audio
    if ev.event_type in (EC_DEVICE_HEALTH, EC_LOCK) and not critical:
        drop(ROUTE_MEDIA, "device_health/lock no audio")

    # Ensure dashboard / bus always there
    if ROUTE_DASHBOARD not in routes:
        routes.append(ROUTE_DASHBOARD)
    if ROUTE_BUS_ONLY not in routes:
        routes.append(ROUTE_BUS_ONLY)

    # Deduplicate while preserving order
    seen: set[str] = set()
    routes = [r for r in routes if not (r in seen or seen.add(r))]
    suppressed = [r for r in suppressed if r in ALL_ROUTES and r not in routes]

    # Final mode
    if not any(r in routes for r in (ROUTE_PUSH, ROUTE_PERSISTENT, ROUTE_MEDIA, ROUTE_LIGHT)):
        mode = MODE_SILENT
    else:
        mode = _severity_to_mode(sev)
        if ctx.bio_state == BIO_SLEEP and not critical:
            mode = MODE_SOFT if mode != MODE_SILENT else mode

    if not reasons:
        reasons.append("default routing")

    return Decision(
        mode=mode,
        routes=routes,
        suppressed_routes=suppressed,
        reason="; ".join(reasons),
        title=title,
        message=message,
        severity=sev,
        context=ctx.snapshot(),
        masked=masked,
    )
