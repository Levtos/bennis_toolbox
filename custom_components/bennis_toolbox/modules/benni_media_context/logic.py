"""Pure decision logic for benni_media_context.

This module deliberately has no Home Assistant imports so it can be unit
tested in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from .const import (
    CTX_IDLE, CTX_TV, CTX_STREAMING, CTX_GAMING, CTX_PRIVATE,
    SUB_NONE, SUB_TV_DEFAULT, SUB_STR_DEFAULT, SUB_STR_APPLETV,
    SUB_GAME_DEFAULT, SUB_GAME_GRIND, SUB_GAME_HEADSET,
    DEV_NONE, DEV_TV, DEV_APPLETV, DEV_PS5, DEV_SWITCH, DEV_PC,
    DEV_HOMEPODS, DEV_DENON,
    GS_NONE, GS_TV, GS_PC,
    GP_NONE, GP_PS5, GP_SWITCH, GP_PC,
    CLASSIFIER_GAME_DEFAULT, CLASSIFIER_GAME_GRIND, CLASSIFIER_GAME_HEADSET,
    CLASSIFIER_MEDIA_NORMAL, CLASSIFIER_MEDIA_BOOST, CLASSIFIER_MEDIA_MUTE,
    TV_SOURCE_MAP, APPLETV_SYSTEM_APPS,
)


@dataclass
class Snapshot:
    """All raw inputs at one moment in time."""
    # TV
    tv_active: bool = False
    tv_source: Optional[str] = None
    tv_power: Optional[bool] = None
    # Apple TV
    atv_state: Optional[str] = None        # playing/paused/idle/off/standby
    atv_app_id: Optional[str] = None
    atv_title: Optional[str] = None
    # PS5
    ps5_status: Optional[str] = None       # on/standby/off/playing
    ps5_title: Optional[str] = None
    # Switch
    switch_dock: bool = False
    # `switch_dock` is the plug-based "docked & active" signal. ping_on +
    # dock_off marks a likely handheld session; coordinator computes this
    # so logic stays HA-free.
    switch_ping_on: Optional[bool] = None
    switch_power_w: Optional[float] = None
    switch_handheld_candidate: bool = False
    # PC
    pc_active: bool = False
    pc_power_w: Optional[float] = None
    # Denon
    denon_active: bool = False
    denon_source: Optional[str] = None  # raw `source` attr of the Denon media_player (e.g. "TV Audio")
    denon_player_state: Optional[str] = None  # e.g. "on", "playing", "off"
    denon_power_w: Optional[float] = None
    # HomePods
    homepods_playing: bool = False
    homepods_volume_level: Optional[float] = None
    # Per-device diagnostic raw inputs (player_state + power_w + …);
    # the coordinator populates these so the entity attributes can
    # surface a stable per-device view without re-reading hass.states.
    device_diagnostics: dict = field(default_factory=dict)
    # TV / PS5 / homepods enrichments via media_player attributes.
    tv_player_state: Optional[str] = None
    tv_power_w: Optional[float] = None
    ps5_player_state: Optional[str] = None
    ps5_power_w: Optional[float] = None
    ps5_network_state: Optional[str] = None
    # Title Classifier enums
    classifier_ps5: int = 0
    classifier_pc: int = 0
    classifier_homepods: int = 0
    classifier_media: int = 0
    # Quiet
    door_open: bool = False
    call_active: bool = False
    # Phases
    day_state: Optional[str] = None
    activity_state: Optional[str] = None
    window_open: bool = False
    # Manual nudge override (subcontext)
    manual_nudge: Optional[str] = None


@dataclass
class Decision:
    context: str = CTX_IDLE
    subcontext: str = SUB_NONE
    device: str = DEV_NONE
    gaming_source: str = GS_NONE
    gaming_platform: str = GP_NONE
    headset_active: bool = False
    entertainment_active: bool = False
    quiet_mode_active: bool = False
    quiet_mode_reason: Optional[str] = None
    volume_target_homepods: float = 0.0
    volume_target_denon: float = 0.0
    subwoofer_allowed: bool = True
    # Diagnostics for the subwoofer decision so the entity attributes can
    # surface why subwoofer_allowed went on/off.
    subwoofer_block_reason: Optional[str] = None
    denon_audio_path: bool = False
    active_reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------
def evaluate_quiet(snap: Snapshot) -> tuple[bool, Optional[str]]:
    if snap.call_active:
        return True, "call_active"
    if snap.door_open:
        return True, "door_open"
    if snap.classifier_media == CLASSIFIER_MEDIA_MUTE:
        return True, "classifier_media_mute"
    if snap.activity_state in ("sleep", "asleep", "quiet"):
        return True, f"activity_{snap.activity_state}"
    return False, None


# ---------------------------------------------------------------------------
# Device priority (highest wins for primary "device")
# Order: ATV > TV > PS5 > Switch > PC > Denon > HomePods
# ---------------------------------------------------------------------------
def detect_devices(snap: Snapshot) -> list[str]:
    devs = []
    if snap.atv_state in ("playing", "paused"):
        devs.append(DEV_APPLETV)
    if snap.tv_active or snap.tv_power:
        devs.append(DEV_TV)
    if snap.ps5_status in ("on", "playing"):
        devs.append(DEV_PS5)
    if snap.switch_dock:
        devs.append(DEV_SWITCH)
    if snap.pc_active:
        devs.append(DEV_PC)
    if snap.denon_active:
        devs.append(DEV_DENON)
    if snap.homepods_playing:
        devs.append(DEV_HOMEPODS)
    return devs


# ---------------------------------------------------------------------------
# Gaming
# ---------------------------------------------------------------------------
def _game_sub_from_enum(enum_val: int) -> str:
    if enum_val == CLASSIFIER_GAME_GRIND:
        return SUB_GAME_GRIND
    if enum_val == CLASSIFIER_GAME_HEADSET:
        return SUB_GAME_HEADSET
    return SUB_GAME_DEFAULT


def detect_gaming(snap: Snapshot) -> Optional[tuple[str, str, str, bool]]:
    """Return (subcontext, gaming_source, gaming_platform, headset_active) or None."""
    # PS5 takes priority on TV
    if snap.ps5_status in ("on", "playing"):
        sub = _game_sub_from_enum(snap.classifier_ps5)
        headset = snap.classifier_ps5 == CLASSIFIER_GAME_HEADSET
        return sub, GS_TV, GP_PS5, headset
    if snap.switch_dock:
        # Switch: no title signal, force default regardless of enum
        return SUB_GAME_DEFAULT, GS_TV, GP_SWITCH, False
    if snap.pc_active:
        sub = _game_sub_from_enum(snap.classifier_pc)
        headset = snap.classifier_pc == CLASSIFIER_GAME_HEADSET
        return sub, GS_PC, GP_PC, headset
    return None


# ---------------------------------------------------------------------------
# Streaming via Apple TV
# ---------------------------------------------------------------------------
def detect_streaming(snap: Snapshot, app_map: dict[str, str]) -> Optional[str]:
    if snap.atv_state not in ("playing", "paused"):
        return None
    app = snap.atv_app_id
    if app is None:
        return SUB_STR_DEFAULT
    if app in APPLETV_SYSTEM_APPS:
        return None  # signals rollback to pre-ATV scenario
    return app_map.get(app, SUB_STR_DEFAULT)


# ---------------------------------------------------------------------------
# TV (broadcast)
# ---------------------------------------------------------------------------
def detect_tv(snap: Snapshot) -> Optional[str]:
    if not (snap.tv_active or snap.tv_power):
        return None
    if snap.tv_source and snap.tv_source in TV_SOURCE_MAP:
        return TV_SOURCE_MAP[snap.tv_source]
    return SUB_TV_DEFAULT


# ---------------------------------------------------------------------------
# Volume targets
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Subwoofer policy
#
# The subwoofer lives downstream of the Denon AVR. Whenever the Denon
# audio path is active (PC gaming via TV Audio, music streaming via
# Denon, ATV via Denon, …) we want the sub to be available even if a
# window is open — the room is already in "audio listening" mode and
# the window penalty for the volume targets is the correct knob there.
# Explicit blockers still win: quiet mode, headset, and a window-open
# scenario where there is NO Denon path at all (then the sub has no
# legitimate route and should stay off).
# ---------------------------------------------------------------------------


def _denon_audio_path(snap: "Snapshot", device: str) -> bool:
    """The user's audio is going through the Denon right now.

    True if any of:
    - the configured `denon_active` binary is on,
    - or the chosen primary device is the Denon itself,
    - or the Denon media_player reports a non-empty source attribute
      (e.g. "TV Audio") — which is the canonical Einhornzentrale
      signal that the AVR is routing for a downstream device.
    """
    if snap.denon_active:
        return True
    if device == DEV_DENON:
        return True
    if snap.denon_source and snap.denon_source.strip().lower() not in ("", "off", "standby"):
        return True
    return False


def evaluate_subwoofer(snap: "Snapshot", decision: "Decision") -> tuple[bool, Optional[str]]:
    """Return ``(allowed, block_reason)`` for the subwoofer.

    Order of precedence:
    1. quiet mode → off
    2. no entertainment activity → off
    3. headset_active (e.g. gaming_headset) → off (sub via speakers
       would defeat the point)
    4. window_open WITHOUT denon path → off (no audio route)
    5. otherwise → on
    """
    if decision.quiet_mode_active:
        return False, "quiet_mode"
    if not decision.entertainment_active:
        return False, "no_entertainment"
    if decision.headset_active:
        return False, "headset_active"
    if snap.window_open and not decision.denon_audio_path:
        return False, "window_open_no_denon_path"
    return True, None


def compute_volumes(
    snap: Snapshot,
    base_homepods: float,
    base_denon: float,
    boost_offset: float,
    window_offset: float,
    quiet_duck: float,
    quiet: bool,
) -> tuple[float, float]:
    hp = base_homepods
    dn = base_denon
    if snap.classifier_media == CLASSIFIER_MEDIA_BOOST:
        hp += boost_offset
        dn += boost_offset
    if snap.window_open:
        hp += window_offset
        dn += window_offset
    if quiet:
        hp = min(hp, quiet_duck)
        dn = min(dn, quiet_duck)
    # Clamp 0..1
    return max(0.0, min(1.0, hp)), max(0.0, min(1.0, dn))


# ---------------------------------------------------------------------------
# Master decision
# ---------------------------------------------------------------------------
def decide(
    snap: Snapshot,
    app_map: dict[str, str],
    base_homepods: float,
    base_denon: float,
    boost_offset: float,
    window_offset: float,
    quiet_duck: float,
    pre_atv_scenario: Optional[Decision] = None,
) -> Decision:
    d = Decision()
    reasons: list[str] = []

    quiet, qreason = evaluate_quiet(snap)
    d.quiet_mode_active = quiet
    d.quiet_mode_reason = qreason

    devices = detect_devices(snap)
    d.device = devices[0] if devices else DEV_NONE

    # Quiet mode forces private_time + suppresses entertainment
    if quiet:
        d.context = CTX_PRIVATE
        d.subcontext = SUB_NONE
        d.entertainment_active = False
        reasons.append(f"quiet:{qreason}")
        hp, dn = compute_volumes(
            snap, base_homepods, base_denon, boost_offset, window_offset,
            quiet_duck, quiet=True,
        )
        d.volume_target_homepods = hp
        d.volume_target_denon = dn
        d.denon_audio_path = _denon_audio_path(snap, d.device)
        allowed, block_reason = evaluate_subwoofer(snap, d)
        d.subwoofer_allowed = allowed
        d.subwoofer_block_reason = block_reason
        d.active_reasons = reasons
        return d

    # Manual nudge highest non-quiet priority
    if snap.manual_nudge:
        d.subcontext = snap.manual_nudge
        if snap.manual_nudge.startswith("tv_"):
            d.context = CTX_TV
        elif snap.manual_nudge.startswith("streaming_"):
            d.context = CTX_STREAMING
        elif snap.manual_nudge.startswith("gaming_"):
            d.context = CTX_GAMING
        reasons.append(f"manual_nudge:{snap.manual_nudge}")

    if d.context == CTX_IDLE:
        # Gaming wins over passive TV/Streaming
        g = detect_gaming(snap)
        if g is not None:
            sub, gs, gp, headset = g
            d.context = CTX_GAMING
            d.subcontext = sub
            d.gaming_source = gs
            d.gaming_platform = gp
            d.headset_active = headset
            reasons.append(f"gaming:{gp}")
        else:
            stream_sub = detect_streaming(snap, app_map)
            if stream_sub is not None:
                d.context = CTX_STREAMING
                d.subcontext = stream_sub
                reasons.append(f"streaming:{snap.atv_app_id}")
            elif snap.atv_state in ("playing", "paused") and snap.atv_app_id in APPLETV_SYSTEM_APPS:
                # System app -> rollback
                if pre_atv_scenario is not None:
                    d.context = pre_atv_scenario.context
                    d.subcontext = pre_atv_scenario.subcontext
                    reasons.append("atv_system_app_rollback")
                else:
                    d.context = CTX_IDLE
                    reasons.append("atv_system_app_no_prior")
            else:
                tv_sub = detect_tv(snap)
                if tv_sub is not None:
                    d.context = CTX_TV
                    d.subcontext = tv_sub
                    reasons.append(f"tv:{snap.tv_source}")
                elif snap.homepods_playing or snap.denon_active:
                    # Audio-only streaming/music: not "tv", treat as streaming_default
                    d.context = CTX_STREAMING
                    d.subcontext = SUB_STR_DEFAULT
                    reasons.append("audio_only")
                else:
                    d.context = CTX_IDLE
                    d.subcontext = SUB_NONE

    d.entertainment_active = d.context in (CTX_TV, CTX_STREAMING, CTX_GAMING)

    hp, dn = compute_volumes(
        snap, base_homepods, base_denon, boost_offset, window_offset,
        quiet_duck, quiet=False,
    )
    d.volume_target_homepods = hp
    d.volume_target_denon = dn
    d.denon_audio_path = _denon_audio_path(snap, d.device)
    allowed, block_reason = evaluate_subwoofer(snap, d)
    d.subwoofer_allowed = allowed
    d.subwoofer_block_reason = block_reason
    d.active_reasons = reasons
    return d
