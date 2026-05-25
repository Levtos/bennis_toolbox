"""Pure decision logic for the Volume Orchestrator.

Sibling to the audio orchestrator. The audio orchestrator decides
*who owns the audio* (HomePods / TV+Denon / Gaming / Private / none);
the volume orchestrator decides *what the speakers should be at and
whether YAML may apply that change*.

Inputs:
  - the audio orchestrator's `OrchestratorDecision` (owner, signals)
  - the bio_sleep / quiet_mode / day_state / opening_any_open signals
  - which player entities are actually configured (some HA installs
    don't wire HomePods or Denon at all)
  - a `VolumeSettings` dataclass with the tunable bases/offsets/clamps

Outputs:
  - a `VolumeDecision` with policy / per-device targets / apply_allowed

No HA imports. The coordinator does the entity-state plumbing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .const import (
    AUDIO_OWNER_GAMING,
    AUDIO_OWNER_HOMEPODS,
    AUDIO_OWNER_NONE,
    AUDIO_OWNER_PRIVATE,
    AUDIO_OWNER_TV_DENON,
    DAY_EDGE_VALUES,
    DAY_NIGHT_VALUES,
    DEFAULT_VOL_ACTIVE_MIN,
    DEFAULT_VOL_DENON_BASE,
    DEFAULT_VOL_DENON_MAX,
    DEFAULT_VOL_DUCKED_TARGET,
    DEFAULT_VOL_EDGE_DAY_OFFSET,
    DEFAULT_VOL_HOMEPODS_BASE,
    DEFAULT_VOL_HOMEPODS_MAX,
    DEFAULT_VOL_NIGHT_OFFSET,
    DEFAULT_VOL_OPENING_OFFSET,
    VOL_POLICY_BLOCKED,
    VOL_POLICY_DUCKED,
    VOL_POLICY_IDLE,
    VOL_POLICY_MEDIA,
    VOL_POLICY_MUTED,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VolumeSettings:
    """All tunable values for the volume orchestrator.

    Defaults match the spec. The coordinator hydrates this dataclass
    from `entry.options` (falling back to `entry.data`) so a fresh
    install or a partial options dict still produces a complete
    settings object.
    """

    homepods_base: float = DEFAULT_VOL_HOMEPODS_BASE
    denon_base: float = DEFAULT_VOL_DENON_BASE
    ducked_target: float = DEFAULT_VOL_DUCKED_TARGET
    homepods_max: float = DEFAULT_VOL_HOMEPODS_MAX
    denon_max: float = DEFAULT_VOL_DENON_MAX
    active_min: float = DEFAULT_VOL_ACTIVE_MIN
    night_offset: float = DEFAULT_VOL_NIGHT_OFFSET
    edge_day_offset: float = DEFAULT_VOL_EDGE_DAY_OFFSET
    opening_offset: float = DEFAULT_VOL_OPENING_OFFSET


@dataclass
class VolumeDecision:
    """Volume policy + per-device targets surfaced to HA entities."""

    policy: str = VOL_POLICY_IDLE
    homepods_target: Optional[float] = None
    denon_target: Optional[float] = None
    apply_allowed: bool = False
    reason: str = "idle"
    blocked_reason: Optional[str] = None

    # Pre-offset base targets (post owner routing, pre day/opening
    # math). Surfaced so the debug view shows the intermediate steps.
    base_homepods_target: float = 0.0
    base_denon_target: float = 0.0
    # The final, clamped values. `None` means the device is either
    # unconfigured or the policy says "stay silent" (muted/blocked).
    effective_homepods_target: Optional[float] = None
    effective_denon_target: Optional[float] = None
    # The signed offsets that fed into the effective targets.
    day_offset: float = 0.0
    opening_offset: float = 0.0

    # Echoed external state for the debug surface — the YAML side can
    # see everything the orchestrator saw without a second template.
    bio_state: Optional[str] = None
    day_state: Optional[str] = None
    opening_any_open: bool = False
    quiet_mode_active: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _day_offset(day_state: Optional[str], settings: VolumeSettings) -> float:
    if day_state in DAY_NIGHT_VALUES:
        return settings.night_offset
    if day_state in DAY_EDGE_VALUES:
        return settings.edge_day_offset
    return 0.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _final_target(
    base: float,
    *,
    day_offset: float,
    opening_offset: float,
    active_min: float,
    hard_max: float,
) -> float:
    """Apply offsets + clamps for an active device.

    Only invoked when ``base > 0`` (i.e. the owner-routing branch put
    audio on this device); the caller short-circuits to 0/None
    otherwise.
    """
    target = base + day_offset + opening_offset
    target = max(target, active_min)
    target = _clamp(target, 0.0, hard_max)
    return round(target, 3)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def decide_volume(
    *,
    audio_owner: str,
    bio_sleep: bool,
    quiet_mode_active: bool,
    bio_state: Optional[str],
    day_state: Optional[str],
    opening_any_open: bool,
    homepods_configured: bool,
    denon_configured: bool,
    settings: VolumeSettings,
) -> VolumeDecision:
    """Compute the volume policy + per-device targets.

    Precedence (highest first):
      1. **blocked** — neither HomePods nor Denon is configured →
         nothing the orchestrator can usefully do; apply blocked.
      2. **muted** — bio sleep/sleeping → keep both devices quiet,
         apply blocked so YAML doesn't push volume changes through.
      3. **ducked** — quiet mode hard win → the currently-owning
         device gets the ducked target, the other stays at 0.
      4. **media / idle** — normal owner routing: HomePods if owner
         is `homepods`, Denon if owner is tv_denon/gaming/private,
         both 0 if owner is none.
    """
    vd = VolumeDecision()
    vd.bio_state = bio_state
    vd.day_state = day_state
    vd.opening_any_open = opening_any_open
    vd.quiet_mode_active = quiet_mode_active

    # ---- 1. Blocked: no addressable speakers at all ------------------
    if not homepods_configured and not denon_configured:
        vd.policy = VOL_POLICY_BLOCKED
        vd.blocked_reason = "no_speakers_configured"
        vd.reason = "no_speakers_configured"
        vd.apply_allowed = False
        return _finalize(vd)

    # ---- 2. Muted: bio sleep --------------------------------------------
    if bio_sleep:
        vd.policy = VOL_POLICY_MUTED
        vd.blocked_reason = "bio_sleep"
        vd.reason = "bio_sleep_muted"
        vd.apply_allowed = False
        # Targets stay None (unavailable) — sleeping means "don't touch".
        return _finalize(vd)

    # ---- Base routing -------------------------------------------------
    if audio_owner == AUDIO_OWNER_HOMEPODS:
        vd.base_homepods_target = settings.homepods_base
        vd.base_denon_target = 0.0
    elif audio_owner in (
        AUDIO_OWNER_TV_DENON, AUDIO_OWNER_GAMING, AUDIO_OWNER_PRIVATE,
    ):
        vd.base_homepods_target = 0.0
        vd.base_denon_target = settings.denon_base
    else:  # AUDIO_OWNER_NONE
        vd.base_homepods_target = 0.0
        vd.base_denon_target = 0.0

    # ---- Offsets ------------------------------------------------------
    vd.day_offset = _day_offset(day_state, settings)
    vd.opening_offset = settings.opening_offset if opening_any_open else 0.0

    # ---- 3. Ducked: quiet mode --------------------------------------
    if quiet_mode_active:
        vd.policy = VOL_POLICY_DUCKED
        vd.reason = "quiet_mode_ducked"
        vd.apply_allowed = True
        # Only the active device (per owner routing) is set to the
        # ducked target; the silent side stays at None/0.
        if vd.base_homepods_target > 0 and homepods_configured:
            vd.effective_homepods_target = round(
                _clamp(settings.ducked_target, 0.0, settings.homepods_max), 3
            )
        elif homepods_configured:
            vd.effective_homepods_target = 0.0
        if vd.base_denon_target > 0 and denon_configured:
            vd.effective_denon_target = round(
                _clamp(settings.ducked_target, 0.0, settings.denon_max), 3
            )
        elif denon_configured:
            vd.effective_denon_target = 0.0
        return _finalize(vd)

    # ---- 4. Media / Idle --------------------------------------------
    if audio_owner == AUDIO_OWNER_NONE:
        vd.policy = VOL_POLICY_IDLE
        vd.reason = "idle_no_owner"
        vd.apply_allowed = True
        if homepods_configured:
            vd.effective_homepods_target = 0.0
        if denon_configured:
            vd.effective_denon_target = 0.0
        return _finalize(vd)

    vd.policy = VOL_POLICY_MEDIA
    vd.reason = f"owner_{audio_owner}"
    vd.apply_allowed = True

    if vd.base_homepods_target > 0 and homepods_configured:
        vd.effective_homepods_target = _final_target(
            vd.base_homepods_target,
            day_offset=vd.day_offset,
            opening_offset=vd.opening_offset,
            active_min=settings.active_min,
            hard_max=settings.homepods_max,
        )
    elif homepods_configured:
        vd.effective_homepods_target = 0.0

    if vd.base_denon_target > 0 and denon_configured:
        vd.effective_denon_target = _final_target(
            vd.base_denon_target,
            day_offset=vd.day_offset,
            opening_offset=vd.opening_offset,
            active_min=settings.active_min,
            hard_max=settings.denon_max,
        )
    elif denon_configured:
        vd.effective_denon_target = 0.0

    return _finalize(vd)


def _finalize(vd: VolumeDecision) -> VolumeDecision:
    """Mirror effective_* into the public *_target slots.

    HA entities read from `homepods_target` / `denon_target` (those
    are the public sensor values); `effective_*` is the debug echo
    for the attribute view. Centralizing the mirror means every
    return path stays consistent.
    """
    vd.homepods_target = vd.effective_homepods_target
    vd.denon_target = vd.effective_denon_target
    return vd


__all__ = [
    "VolumeDecision",
    "VolumeSettings",
    "decide_volume",
]
