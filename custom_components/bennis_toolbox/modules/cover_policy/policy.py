"""Pure decision engine for cover_policy — HA-free.

Returns a `Decision` describing the desired mode, target position, reason
string, list of blockers and whether the decision wants to forcibly clear
an active manual override (only true when window_open wins absolutely).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    BIO_SLEEP,
    BIO_WAKING,
    DAY_DAYTIME,
    DAY_NIGHT_LIKE,
    HOUSEHOLD_EMPTY,
    MODE_GLARE_PC,
    MODE_GLARE_TV,
    MODE_HEAT_PROTECT,
    MODE_MANUAL,
    MODE_OPEN,
    MODE_PRIVACY,
    MODE_SLEEP,
    MODE_WAKE,
    MODE_WINDOW_OPEN,
    PRESENCE_AWAY,
    TV_MEDIA_CONTEXTS,
)


@dataclass(frozen=True)
class Context:
    """Snapshot of all source inputs for one decision."""

    # Tri-state booleans: True / False / None (unknown).
    window_open: bool | None = None
    heat_protect_active: bool | None = None

    bio_state: str | None = None
    day_state: str | None = None
    day_context: str | None = None
    presence_household: str | None = None
    presence_personal: str | None = None

    lux: float | None = None
    sun_above_horizon: bool | None = None
    weather: str | None = None  # currently informational only

    media_context: str | None = None
    gaming_source: str | None = None  # "tv" / "pc" / None / "none"


@dataclass
class Decision:
    mode: str
    target_position: int | None
    reason: str
    blockers: list[str] = field(default_factory=list)
    manual_override_cleared: bool = False
    apply_allowed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "target_position": self.target_position,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "manual_override_cleared": self.manual_override_cleared,
            "apply_allowed": self.apply_allowed,
        }


# Source keys that, when configured but reading None, count as "degraded".
DEGRADED_SOURCES_REQUIRED = ("window_open",)  # window state is critical


def _profile_value(profile: dict[str, int], mode: str, fallback: int) -> int:
    try:
        v = int(profile.get(mode, fallback))
    except (TypeError, ValueError):
        return fallback
    return max(0, min(100, v))


def _is_daytime(ctx: Context) -> bool:
    if ctx.day_state and ctx.day_state in DAY_DAYTIME:
        return True
    if ctx.sun_above_horizon is True:
        return True
    return False


def _is_night_like(ctx: Context) -> bool:
    return bool(ctx.day_state and ctx.day_state in DAY_NIGHT_LIKE)


def decide(
    ctx: Context,
    profile: dict[str, int],
    *,
    startup_ready: bool,
    apply_enabled: bool,
    manual_override_active: bool,
    require_window: bool = True,
    glare_lux_threshold: float = 5000.0,
) -> Decision:
    """Decide the desired cover mode + position.

    Order (highest priority first):
      1. window_open  — absolute, may clear a manual override.
      2. manual_override
      3. heat_protect
      4. glare_pc  (gaming_source=pc takes priority over TV glare)
      5. glare_tv
      6. sleep
      7. wake
      8. privacy
      9. open (default)

    Always-blockers (do not prevent computing a mode/target, but mark
    apply_allowed=False):
      - apply_enabled=False
      - startup_ready=False
      - any required source is unknown
    """
    blockers: list[str] = []
    apply_allowed = True

    if not apply_enabled:
        blockers.append("apply_disabled")
        apply_allowed = False
    if not startup_ready:
        blockers.append("startup_block")
        apply_allowed = False

    # Required sources: window state is critical when configured.
    if require_window and ctx.window_open is None:
        blockers.append("source_unknown:window")
        apply_allowed = False

    # 1) window_open ALWAYS wins. May clear an active manual override.
    if ctx.window_open is True:
        return Decision(
            mode=MODE_WINDOW_OPEN,
            target_position=_profile_value(profile, MODE_WINDOW_OPEN, 70),
            reason="window_open: absolute override",
            blockers=blockers,
            manual_override_cleared=manual_override_active,
            apply_allowed=apply_allowed,
        )

    # 2) manual override blocks normal apply.
    if manual_override_active:
        blockers.append("manual_override")
        return Decision(
            mode=MODE_MANUAL,
            target_position=None,
            reason="manual override active",
            blockers=blockers,
            apply_allowed=False,
        )

    # 3) heat_protect: explicit signal from a thermostat / sun-protection script.
    if ctx.heat_protect_active is True:
        return Decision(
            mode=MODE_HEAT_PROTECT,
            target_position=_profile_value(profile, MODE_HEAT_PROTECT, 0),
            reason="heat protection active",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    daytime = _is_daytime(ctx)
    bright = ctx.lux is not None and ctx.lux >= glare_lux_threshold

    # 4) glare_pc — gaming on PC during daytime+bright.
    if ctx.gaming_source == "pc" and daytime and (bright or ctx.lux is None):
        return Decision(
            mode=MODE_GLARE_PC,
            target_position=_profile_value(profile, MODE_GLARE_PC, 40),
            reason="glare_pc: gaming on PC during daytime",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    # 5) glare_tv — media on TV during daytime+bright (only if not PC gaming).
    if (
        daytime
        and (bright or ctx.lux is None)
        and ctx.gaming_source in (None, "none", "tv")
        and ctx.media_context in TV_MEDIA_CONTEXTS
    ):
        return Decision(
            mode=MODE_GLARE_TV,
            target_position=_profile_value(profile, MODE_GLARE_TV, 20),
            reason="glare_tv: media playing on TV during daytime",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    # 6) sleep — bio=sleep or night-like and presence is home-equivalent.
    if ctx.bio_state == BIO_SLEEP or _is_night_like(ctx):
        return Decision(
            mode=MODE_SLEEP,
            target_position=_profile_value(profile, MODE_SLEEP, 0),
            reason=f"sleep: bio={ctx.bio_state!r}, day_state={ctx.day_state!r}",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    # 7) wake — bio=waking.
    if ctx.bio_state == BIO_WAKING:
        return Decision(
            mode=MODE_WAKE,
            target_position=_profile_value(profile, MODE_WAKE, 70),
            reason="wake: bio=waking",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    # 8) privacy — household empty while presence is away (NOT bei_eltern).
    if (
        ctx.presence_personal == PRESENCE_AWAY
        and ctx.presence_household == HOUSEHOLD_EMPTY
    ):
        return Decision(
            mode=MODE_PRIVACY,
            target_position=_profile_value(profile, MODE_PRIVACY, 30),
            reason="privacy: presence=abwesend + household empty",
            blockers=blockers,
            apply_allowed=apply_allowed,
        )

    # 9) default
    return Decision(
        mode=MODE_OPEN,
        target_position=_profile_value(profile, MODE_OPEN, 100),
        reason="default: open",
        blockers=blockers,
        apply_allowed=apply_allowed,
    )
