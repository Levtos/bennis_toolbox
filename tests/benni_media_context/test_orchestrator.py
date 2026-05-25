"""Tests for the audio orchestrator decision logic.

The orchestrator decides whether HomePods should pause, resume, start a
planned radio, or do nothing — based on the media context, the raw
device signals, bio sleep, and a small persistent state carried across
ticks.

These tests pin the Fachregeln from the lastenheft:
  * higher-priority stacks pause HomePods,
  * PS5/Switch always count as gaming-stack,
  * PC only counts when a real PC-gaming title classifier is set,
  * manual stop blocks resume,
  * bio_sleep blocks resume + radio,
  * planned_radio takes precedence over manual playback when both flags
    were active before the auto-pause.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

import bmc_logic as L  # already loaded via conftest
import bmc_const as C


# Load the orchestrator into the synthetic package set up by conftest.
PKG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "custom_components", "bennis_toolbox", "modules", "benni_media_context",
)
_spec = importlib.util.spec_from_file_location(
    "bmc_logic_pkg.orchestrator", os.path.join(PKG_DIR, "orchestrator.py"),
)
orchestrator = importlib.util.module_from_spec(_spec)
sys.modules["bmc_logic_pkg.orchestrator"] = orchestrator
_spec.loader.exec_module(orchestrator)
sys.modules["bmc_orch"] = orchestrator
O = orchestrator


def _snap(**kw) -> L.Snapshot:
    s = L.Snapshot()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _decide(snap: L.Snapshot, **opts) -> L.Decision:
    return L.decide(
        snap,
        app_map=C.DEFAULT_APPLETV_APP_MAP,
        base_homepods=0.35,
        base_denon=0.40,
        boost_offset=0.10,
        window_offset=-0.05,
        quiet_duck=0.15,
        **opts,
    )


def _orch(snap, *, state=None, bio_sleep=False, manual=False, radio=False,
          homepods_state=None):
    state = state or O.OrchestratorState()
    decision = _decide(snap)
    return O.decide_audio_orchestrator(
        snap, decision,
        bio_sleep=bio_sleep,
        manual_playback_active=manual,
        planned_radio_active=radio,
        homepods_state=homepods_state,
        state=state,
    )


# ---------------------------------------------------------------------------
# Audio owner / signal priority
# ---------------------------------------------------------------------------


def test_idle_with_homepods_only_owner_is_homepods():
    snap = _snap(homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_HOMEPODS
    assert od.action == C.ACTION_NONE


def test_idle_with_nothing_owner_is_none():
    od, _ = _orch(_snap(), homepods_state="idle")
    assert od.audio_owner == C.AUDIO_OWNER_NONE


def test_ps5_gaming_pauses_homepods():
    snap = _snap(ps5_status="playing", homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_GAMING
    assert od.should_pause is True
    assert od.action == C.ACTION_PAUSE
    assert od.ps5_gaming_active is True


def test_switch_dock_is_gaming_stack():
    snap = _snap(switch_dock=True, homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_GAMING
    assert od.switch_gaming_active is True
    assert od.should_pause is True


def test_pc_alone_is_not_gaming_stack():
    """Per Fachregel: PC-Gaming gilt nur bei validem PC-Gaming-Signal."""
    snap = _snap(pc_active=True, classifier_pc=0,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    # decide() still flags context=gaming (legacy), but the orchestrator
    # must NOT promote PC-without-classifier into the entertainment stack.
    assert od.pc_gaming_active is False
    # HomePods keep ownership in the orchestrator's view.
    assert od.audio_owner != C.AUDIO_OWNER_GAMING


def test_pc_with_grind_classifier_is_gaming_stack():
    snap = _snap(pc_active=True, classifier_pc=1,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.pc_gaming_active is True
    assert od.audio_owner == C.AUDIO_OWNER_GAMING
    assert od.should_pause is True


def test_appletv_streaming_wins_over_homepods():
    snap = _snap(atv_state="playing", atv_app_id="com.netflix.Netflix",
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_TV_DENON
    assert od.streaming_signal_active is True
    assert od.should_pause is True


def test_appletv_system_app_does_not_pause():
    """System apps (Home/Settings) must not count as streaming and so
    must not pause HomePods on their own."""
    snap = _snap(atv_state="playing", atv_app_id="com.apple.TVSettings",
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.streaming_signal_active is False
    assert od.audio_owner == C.AUDIO_OWNER_HOMEPODS
    assert od.should_pause is False


def test_tv_broadcast_pauses_homepods():
    snap = _snap(tv_active=True, homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_TV_DENON
    assert od.should_pause is True


def test_private_time_outranks_gaming():
    """Quiet mode = private_time and must win against any other stack."""
    snap = _snap(ps5_status="playing", door_open=True,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.audio_owner == C.AUDIO_OWNER_PRIVATE
    assert od.should_pause is True


def test_bio_sleep_alone_acts_as_private_stack():
    snap = _snap(homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True, bio_sleep=True)
    assert od.audio_owner == C.AUDIO_OWNER_PRIVATE
    assert od.should_pause is True


# ---------------------------------------------------------------------------
# Auto-pause / resume bookkeeping
# ---------------------------------------------------------------------------


def test_auto_pause_then_resume_homepods_after_entertainment_ends():
    state = O.OrchestratorState()
    # Tick 1: HomePods playing, manual flag set, nothing else.
    snap = _snap(homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap, state=state, homepods_state="playing", manual=True)
    # Tick 2: PS5 starts → pause recommendation; YAML acts → HomePods stop
    # In the same tick we still see HomePods playing and PS5 on.
    snap2 = _snap(ps5_status="playing", homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap2, state=state, homepods_state="playing", manual=True)
    # Tick 3: HomePods now stopped (idle), PS5 still on.
    snap3 = _snap(ps5_status="playing")
    od3, state = _orch(snap3, state=state, homepods_state="idle", manual=True)
    assert state.auto_paused is True
    assert od3.auto_paused_homepods is True
    assert od3.resume_candidate == C.RESUME_MODE_MANUAL
    assert od3.action == C.ACTION_NONE  # still entertainment, no resume yet
    # Tick 4: PS5 off → no other stack, manual was the pre-pause mode.
    snap4 = _snap()
    od4, state = _orch(snap4, state=state, homepods_state="idle", manual=False)
    assert od4.action == C.ACTION_RESUME
    assert od4.resume_allowed is True
    assert od4.blocked_reason is None


def test_auto_pause_chooses_radio_over_manual_when_radio_was_active():
    state = O.OrchestratorState()
    # Tick 1: HomePods playing planned radio.
    snap = _snap(homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap, state=state, homepods_state="playing", radio=True)
    # Tick 2: PS5 active, HomePods still playing.
    snap2 = _snap(ps5_status="playing", homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap2, state=state, homepods_state="playing", radio=True)
    # Tick 3: HomePods stop while PS5 still on.
    snap3 = _snap(ps5_status="playing")
    _, state = _orch(snap3, state=state, homepods_state="idle", radio=True)
    assert state.pre_pause_mode == C.RESUME_MODE_RADIO
    # Tick 4: PS5 off.
    snap4 = _snap()
    od, _ = _orch(snap4, state=state, homepods_state="idle", radio=False)
    assert od.action == C.ACTION_START_RADIO
    assert od.resume_allowed is True


def test_manual_stop_blocks_resume():
    state = O.OrchestratorState()
    # Tick 1: HomePods playing, no entertainment.
    snap = _snap(homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap, state=state, homepods_state="playing", manual=True)
    # Tick 2: user stops manually, no entertainment.
    snap2 = _snap()
    od2, state = _orch(snap2, state=state, homepods_state="idle", manual=False)
    assert state.manual_stop is True
    assert od2.blocked_reason == "manual_stop"
    # Even if later we'd be eligible, manual_stop persists until restart.
    od3, state = _orch(_snap(), state=state, homepods_state="idle")
    assert od3.action == C.ACTION_NONE
    assert od3.blocked_reason == "manual_stop"


def test_bio_sleep_blocks_resume_and_radio():
    """Bio sleep promotes to private_stack so no resume action is emitted,
    regardless of the auto-pause/radio bookkeeping."""
    state = O.OrchestratorState(
        auto_paused=True, pre_pause_mode=C.RESUME_MODE_RADIO,
        last_homepods_playing=False, last_other_stack_active=True,
    )
    od, _ = _orch(_snap(), state=state, homepods_state="idle", bio_sleep=True)
    assert od.action == C.ACTION_NONE
    assert od.resume_allowed is False
    assert od.audio_owner == C.AUDIO_OWNER_PRIVATE


def test_bio_sleep_blocks_resume_after_entertainment_ends():
    """When entertainment ends but bio_sleep is still True, neither
    resume nor radio fires."""
    state = O.OrchestratorState(
        auto_paused=True, pre_pause_mode=C.RESUME_MODE_RADIO,
        last_homepods_playing=False, last_other_stack_active=True,
    )
    # Use activity_state="sleep" so it triggers quiet → private but
    # the bio_sleep code path also flows through. Either way the
    # orchestrator must refuse to resume during sleep.
    snap = _snap(activity_state="sleep")
    od, _ = _orch(snap, state=state, homepods_state="idle", bio_sleep=True)
    assert od.action == C.ACTION_NONE
    assert od.resume_allowed is False


def test_no_resume_when_no_auto_pause():
    od, _ = _orch(_snap(), homepods_state="idle")
    assert od.action == C.ACTION_NONE
    assert od.blocked_reason == "no_auto_pause"


def test_resume_clears_manual_stop_and_auto_pause_on_play():
    state = O.OrchestratorState(
        auto_paused=True, pre_pause_mode=C.RESUME_MODE_MANUAL,
        manual_stop=True, last_homepods_playing=False,
    )
    snap = _snap(homepods_playing=True, homepods_state="playing")
    _, state = _orch(snap, state=state, homepods_state="playing", manual=True)
    assert state.auto_paused is False
    assert state.manual_stop is False
    assert state.pre_pause_mode is None


# ---------------------------------------------------------------------------
# Debug surface
# ---------------------------------------------------------------------------


def test_debug_attributes_carry_winning_stack_and_signals():
    snap = _snap(ps5_status="playing", homepods_playing=True, homepods_state="playing")
    od, _ = _orch(snap, homepods_state="playing", manual=True)
    assert od.winning_stack == C.AUDIO_OWNER_GAMING
    assert od.gaming_signal_active is True
    assert od.tv_signal_active is False
    assert od.streaming_signal_active is False


def test_attributes_echo_external_inputs():
    snap = _snap()
    od, _ = _orch(snap, homepods_state="idle", manual=True, radio=True, bio_sleep=True)
    assert od.manual_playback_active is True
    assert od.planned_radio_active is True
    assert od.bio_sleep is True


# ---------------------------------------------------------------------------
# 0.3.8 configured-entity surface
# ---------------------------------------------------------------------------


def _orch_with_inputs(snap, *, state=None, configured=None, missing_audio=None,
                     missing_vol=None, bio_sleep=False, manual=False, radio=False,
                     homepods_state=None):
    state = state or O.OrchestratorState()
    decision = _decide(snap)
    return O.decide_audio_orchestrator(
        snap, decision,
        bio_sleep=bio_sleep,
        manual_playback_active=manual,
        planned_radio_active=radio,
        homepods_state=homepods_state,
        state=state,
        configured_entities=configured or {},
        missing_orchestrator_inputs=missing_audio or [],
        missing_volume_inputs=missing_vol or [],
    )


def test_configured_entities_surface_echoes_through():
    od, _ = _orch_with_inputs(
        _snap(),
        configured={
            "homepods_player_entity": "media_player.homepods",
            "denon_player_entity": "media_player.denon",
        },
        homepods_state="idle",
    )
    assert od.configured_entities == {
        "homepods_player_entity": "media_player.homepods",
        "denon_player_entity": "media_player.denon",
    }
    assert od.missing_orchestrator_inputs == []


def test_missing_homepods_entity_blocks_action():
    snap = _snap(homepods_playing=True, homepods_state="playing")
    od, _ = _orch_with_inputs(
        snap,
        homepods_state="playing",
        missing_audio=["homepods_player_entity"],
        manual=True,
    )
    assert od.action == C.ACTION_NONE
    assert od.blocked_reason == "homepods_entity_missing"
    assert od.should_pause is False


def test_pc_gaming_active_entity_overrides_classifier():
    """External pc_gaming_active=True forces PC into the gaming stack
    even without a classifier_pc value."""
    snap = _snap(pc_active=True, classifier_pc=0, pc_gaming_active=True,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch_with_inputs(
        snap, homepods_state="playing", manual=True,
        configured={"homepods_player_entity": "media_player.homepods"},
    )
    assert od.audio_owner == C.AUDIO_OWNER_GAMING
    assert od.pc_gaming_active is True
    assert od.should_pause is True


def test_pc_gaming_active_entity_false_overrides_classifier_true():
    """External pc_gaming_active=False blocks the classifier path."""
    snap = _snap(pc_active=True, classifier_pc=2, pc_gaming_active=False,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch_with_inputs(
        snap, homepods_state="playing", manual=True,
        configured={"homepods_player_entity": "media_player.homepods"},
    )
    # Classifier alone would have said gaming; external override wins.
    assert od.pc_gaming_active is False


def test_media_stop_latch_sets_manual_stop():
    state = O.OrchestratorState(
        auto_paused=True, pre_pause_mode=C.RESUME_MODE_MANUAL,
    )
    snap = _snap(media_stop_latch=True)
    od, new_state = _orch_with_inputs(
        snap, state=state, homepods_state="idle", manual=False,
        configured={"homepods_player_entity": "media_player.homepods"},
    )
    assert new_state.manual_stop is True
    assert od.action == C.ACTION_NONE
    assert od.blocked_reason == "manual_stop"
    assert od.media_stop_latch is True


def test_quiet_mode_external_drives_private_owner():
    """When the dedicated quiet_mode binary is on, private_stack wins."""
    snap = _snap(quiet_mode_external=True,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch_with_inputs(
        snap, homepods_state="playing", manual=True,
        configured={"homepods_player_entity": "media_player.homepods"},
    )
    assert od.audio_owner == C.AUDIO_OWNER_PRIVATE
    assert od.should_pause is True


def test_quiet_mode_external_false_overrides_internal_heuristics():
    """External quiet_mode=False blocks the door/call/activity ladder."""
    snap = _snap(quiet_mode_external=False, door_open=True,
                 homepods_playing=True, homepods_state="playing")
    od, _ = _orch_with_inputs(
        snap, homepods_state="playing", manual=True,
        configured={"homepods_player_entity": "media_player.homepods"},
    )
    # Door is open, but the external entity says NOT quiet → quiet_mode
    # should not promote to private_stack.
    assert od.audio_owner != C.AUDIO_OWNER_PRIVATE


def test_bio_state_and_day_state_echoed_for_debug():
    snap = _snap(bio_state="awake", day_state="late_evening")
    od, _ = _orch_with_inputs(snap, homepods_state="idle")
    assert od.bio_state == "awake"
    assert od.day_state == "late_evening"
