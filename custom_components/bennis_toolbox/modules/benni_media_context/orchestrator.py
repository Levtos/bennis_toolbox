"""Pure decision logic for the HomePods-vs-Entertainment audio orchestrator.

Inputs:
  - the regular media `Snapshot` (raw device states)
  - the already-computed media `Decision` (context, denon path, etc.)
  - bio_sleep / manual_playback_active / planned_radio_active flags
  - the previous orchestrator persistent state

Outputs:
  - an `OrchestratorDecision` (stable HA-entity surface)
  - the next persistent state for the orchestrator

The module is HA-free. No service calls, no entity registry access.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from .const import (
    ACTION_NONE,
    ACTION_PAUSE,
    ACTION_RESUME,
    ACTION_START_RADIO,
    AUDIO_OWNER_GAMING,
    AUDIO_OWNER_HOMEPODS,
    AUDIO_OWNER_NONE,
    AUDIO_OWNER_PRIVATE,
    AUDIO_OWNER_TV_DENON,
    BIO_SLEEP_VALUES,
    CTX_GAMING,
    CTX_IDLE,
    CTX_PRIVATE,
    CTX_STREAMING,
    CTX_TV,
    DEV_NONE,
    GP_NONE,
    GS_NONE,
    RESUME_MODE_MANUAL,
    RESUME_MODE_RADIO,
    SUB_NONE,
    APPLETV_SYSTEM_APPS,
)
from .logic import Decision, Snapshot


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorState:
    """Persistent state carried between coordinator ticks."""

    auto_paused: bool = False
    pre_pause_mode: Optional[str] = None
    manual_stop: bool = False
    last_homepods_playing: bool = False
    last_other_stack_active: bool = False
    last_planned_radio_active: bool = False
    last_manual_playback_active: bool = False


@dataclass
class OrchestratorDecision:
    """One-shot decision surfaced to HA entities."""

    audio_owner: str = AUDIO_OWNER_NONE
    action: str = ACTION_NONE
    should_pause: bool = False
    resume_allowed: bool = False
    reason: str = "idle"
    blocked_reason: Optional[str] = None

    # echoed media-context fields (so consumers can read everything from
    # one entity surface)
    media_context: str = CTX_IDLE
    media_subcontext: str = SUB_NONE
    media_device: str = DEV_NONE
    gaming_source: str = GS_NONE
    gaming_platform: str = GP_NONE
    entertainment_active: bool = False

    # per-device state (string, stable values from HA where possible)
    tv_state: Optional[str] = None
    appletv_state: Optional[str] = None
    ps5_state: Optional[str] = None
    switch_state: Optional[str] = None
    pc_gaming_active: bool = False
    denon_state: Optional[str] = None
    denon_audio_path: bool = False
    homepods_state: Optional[str] = None

    # external flags (mirrored back out so users can verify wiring)
    manual_playback_active: bool = False
    planned_radio_active: bool = False
    bio_sleep: bool = False

    # persistent orchestrator state surfaced for debugging
    auto_paused_homepods: bool = False
    resume_candidate: Optional[str] = None

    # Detailed debug signal breakdown
    private_signal_active: bool = False
    gaming_signal_active: bool = False
    streaming_signal_active: bool = False
    tv_signal_active: bool = False
    ps5_gaming_active: bool = False
    switch_gaming_active: bool = False
    winning_stack: str = AUDIO_OWNER_NONE

    # Resolved orchestrator inputs (canonical_name → entity_id|None)
    # and the names of orchestrator-required inputs the user hasn't
    # wired up yet. Surfaced verbatim on the entity attributes.
    configured_entities: dict = field(default_factory=dict)
    missing_orchestrator_inputs: list = field(default_factory=list)
    missing_volume_inputs: list = field(default_factory=list)
    # Echoed external state (orchestrator-input mirrors) so the debug
    # view has everything in one attribute dict.
    media_stop_latch: bool = False
    opening_any_open: bool = False
    bio_state: Optional[str] = None
    day_state: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------


def _ps5_gaming(snap: Snapshot) -> bool:
    if snap.ps5_status in ("on", "playing"):
        return True
    if snap.ps5_player_state in ("on", "playing", "paused"):
        return True
    return False


def _switch_gaming(snap: Snapshot) -> bool:
    # Per lastenheft: only the docked path counts as Entertainment-Stack.
    # The handheld candidate is intentionally excluded — Switch handheld
    # routes audio internally and doesn't conflict with HomePod playback.
    return bool(snap.switch_dock)


def _pc_gaming(snap: Snapshot) -> bool:
    """PC counts as gaming only on a positive PC-gaming signal.

    Precedence:
      1. external `pc_gaming_active_entity` (when configured) — when
         it explicitly says True/False, that wins.
      2. legacy heuristic: pc_active AND title classifier flagged it
         as a game (grind/headset). Pure "PC is powered" does not
         pause HomePods.
    """
    if snap.pc_gaming_active is True:
        return True
    if snap.pc_gaming_active is False:
        return False
    if not snap.pc_active:
        return False
    return bool(snap.classifier_pc and snap.classifier_pc != 0)


def _streaming_signal(snap: Snapshot) -> bool:
    if snap.atv_state not in ("playing", "paused"):
        return False
    if snap.atv_app_id in APPLETV_SYSTEM_APPS:
        return False
    return True


def _tv_signal(snap: Snapshot) -> bool:
    if snap.tv_active:
        return True
    if snap.tv_power:
        return True
    if snap.tv_player_state in ("on", "playing", "paused"):
        return True
    return False


def _private_signal(snap: Snapshot, decision: Decision, bio_sleep: bool) -> bool:
    if decision.quiet_mode_active:
        return True
    if bio_sleep:
        return True
    if decision.context == CTX_PRIVATE:
        return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def decide_audio_orchestrator(
    snap: Snapshot,
    decision: Decision,
    *,
    bio_sleep: bool,
    manual_playback_active: bool,
    planned_radio_active: bool,
    homepods_state: Optional[str],
    state: OrchestratorState,
    configured_entities: Optional[dict] = None,
    missing_orchestrator_inputs: Optional[list] = None,
    missing_volume_inputs: Optional[list] = None,
) -> tuple[OrchestratorDecision, OrchestratorState]:
    """Compute the orchestrator decision and the next persistent state."""
    od = OrchestratorDecision()
    new_state = OrchestratorState(**asdict(state))

    configured_entities = dict(configured_entities or {})
    missing_orchestrator_inputs = list(missing_orchestrator_inputs or [])
    missing_volume_inputs = list(missing_volume_inputs or [])

    homepods_playing = homepods_state == "playing"

    # Without a configured HomePods entity the orchestrator has
    # nothing to act on. Surface a blocked decision instead of
    # guessing — YAML automations should see "no HomePods wired up"
    # explicitly rather than silently treating the world as idle.
    homepods_missing = "homepods_player_entity" in missing_orchestrator_inputs

    ps5_gaming = _ps5_gaming(snap)
    switch_gaming = _switch_gaming(snap)
    pc_gaming = _pc_gaming(snap)
    gaming_signal = ps5_gaming or switch_gaming or pc_gaming
    streaming_signal = _streaming_signal(snap)
    tv_signal = _tv_signal(snap)
    private_signal = _private_signal(snap, decision, bio_sleep)

    # ---- Winner / audio_owner -------------------------------------------
    if private_signal:
        owner = AUDIO_OWNER_PRIVATE
        winning_label = "private_time"
    elif gaming_signal:
        owner = AUDIO_OWNER_GAMING
        if ps5_gaming:
            winning_label = "gaming_ps5"
        elif switch_gaming:
            winning_label = "gaming_switch"
        else:
            winning_label = "gaming_pc"
    elif streaming_signal or tv_signal:
        owner = AUDIO_OWNER_TV_DENON
        winning_label = "streaming_appletv" if streaming_signal else "tv_broadcast"
    elif homepods_playing:
        owner = AUDIO_OWNER_HOMEPODS
        winning_label = "homepods_only"
    else:
        owner = AUDIO_OWNER_NONE
        winning_label = "idle"

    other_stack_active = owner in (
        AUDIO_OWNER_PRIVATE,
        AUDIO_OWNER_GAMING,
        AUDIO_OWNER_TV_DENON,
    )

    # ---- Persistent state transitions (based on prev tick) --------------
    if state.last_homepods_playing and not homepods_playing:
        if state.last_other_stack_active or other_stack_active:
            # Auto-pause: a higher-prio stack pulled the audio.
            new_state.auto_paused = True
            new_state.manual_stop = False
            if state.last_planned_radio_active:
                new_state.pre_pause_mode = RESUME_MODE_RADIO
            elif state.last_manual_playback_active:
                new_state.pre_pause_mode = RESUME_MODE_MANUAL
            else:
                new_state.pre_pause_mode = None
        else:
            # No competing stack → user stopped playback themselves.
            new_state.manual_stop = True
            new_state.auto_paused = False
            new_state.pre_pause_mode = None
    elif homepods_playing and not state.last_homepods_playing:
        # User (or radio automation) resumed playback. Clear the
        # auto-paused / manual-stop bookkeeping.
        new_state.auto_paused = False
        new_state.manual_stop = False
        new_state.pre_pause_mode = None

    # External media_stop_latch overrides internal manual_stop
    # bookkeeping when it is set. Off (False) explicitly clears the
    # latch even if the internal heuristic would have set it; None
    # (not configured) keeps the internal value untouched.
    if snap.media_stop_latch is True:
        new_state.manual_stop = True
    elif snap.media_stop_latch is False and not state.last_homepods_playing:
        # External latch dropped → re-enable resume eligibility, but
        # only when no recent manual-stop event is being recorded
        # (else we'd clobber a fresh internal transition).
        new_state.manual_stop = False

    # ---- Action / reason ------------------------------------------------
    reason = "idle"
    blocked: Optional[str] = None
    action = ACTION_NONE
    should_pause = False
    resume_allowed = False

    if homepods_missing:
        # No HomePods configured → orchestrator has no actor. Surface
        # blocked so YAML doesn't trigger pause/resume against a
        # phantom entity.
        blocked = "homepods_entity_missing"
        reason = "homepods_entity_missing"
    elif other_stack_active and homepods_playing:
        action = ACTION_PAUSE
        should_pause = True
        reason = f"{winning_label}_pause_homepods"
    elif other_stack_active:
        # Stack is active but HomePods aren't playing — nothing to do.
        reason = f"{winning_label}_active"
    else:
        # No competing stack right now → consider resume / radio.
        if bio_sleep:
            blocked = "bio_sleep"
            reason = "bio_sleep_blocks_resume"
        elif new_state.manual_stop:
            blocked = "manual_stop"
            reason = "manual_stop_blocks_resume"
        elif not new_state.auto_paused:
            blocked = "no_auto_pause"
            reason = "no_auto_pause"
        else:
            mode = new_state.pre_pause_mode
            if mode == RESUME_MODE_RADIO:
                action = ACTION_START_RADIO
                resume_allowed = True
                reason = "post_entertainment_start_radio"
            elif mode == RESUME_MODE_MANUAL:
                action = ACTION_RESUME
                resume_allowed = True
                reason = "post_entertainment_resume_music"
            else:
                blocked = "no_resume_candidate"
                reason = "no_resume_candidate"

    # ---- Populate the decision -----------------------------------------
    od.audio_owner = owner
    od.winning_stack = owner
    od.action = action
    od.should_pause = should_pause
    od.resume_allowed = resume_allowed
    od.reason = reason
    od.blocked_reason = blocked

    od.media_context = decision.context
    od.media_subcontext = decision.subcontext
    od.media_device = decision.device
    od.gaming_source = decision.gaming_source
    od.gaming_platform = decision.gaming_platform
    od.entertainment_active = decision.entertainment_active
    od.denon_audio_path = decision.denon_audio_path

    od.tv_state = (
        snap.tv_player_state
        or ("on" if snap.tv_active else None)
        or ("on" if snap.tv_power else None)
    )
    od.appletv_state = snap.atv_state
    od.ps5_state = snap.ps5_player_state or snap.ps5_status
    if snap.switch_dock:
        od.switch_state = "docked"
    elif snap.switch_handheld_candidate:
        od.switch_state = "handheld_candidate"
    else:
        od.switch_state = None
    od.pc_gaming_active = pc_gaming
    od.denon_state = snap.denon_player_state
    od.homepods_state = homepods_state

    od.manual_playback_active = manual_playback_active
    od.planned_radio_active = planned_radio_active
    od.bio_sleep = bio_sleep

    od.auto_paused_homepods = new_state.auto_paused
    od.resume_candidate = new_state.pre_pause_mode

    od.private_signal_active = private_signal
    od.gaming_signal_active = gaming_signal
    od.streaming_signal_active = streaming_signal
    od.tv_signal_active = tv_signal
    od.ps5_gaming_active = ps5_gaming
    od.switch_gaming_active = switch_gaming

    od.configured_entities = dict(configured_entities)
    od.missing_orchestrator_inputs = list(missing_orchestrator_inputs)
    od.missing_volume_inputs = list(missing_volume_inputs)
    od.media_stop_latch = bool(snap.media_stop_latch)
    od.opening_any_open = bool(snap.opening_any_open)
    od.bio_state = snap.bio_state
    od.day_state = snap.day_state

    # ---- Bookkeeping for the next tick ---------------------------------
    new_state.last_homepods_playing = homepods_playing
    new_state.last_other_stack_active = other_stack_active
    new_state.last_planned_radio_active = planned_radio_active
    new_state.last_manual_playback_active = manual_playback_active

    return od, new_state


__all__ = [
    "OrchestratorState",
    "OrchestratorDecision",
    "decide_audio_orchestrator",
]
