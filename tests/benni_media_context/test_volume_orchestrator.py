"""Tests for the pure volume orchestrator decision logic.

The volume orchestrator owns the *speaker numbers* — given the audio
owner from the audio orchestrator plus a handful of external signals
(bio sleep, quiet mode, day phase, opening_any_open), it decides:

  * the volume policy (idle / media / ducked / muted / blocked)
  * per-device targets (HomePods, Denon) with clamps + offsets
  * whether YAML may apply (apply_allowed)

These tests pin the lastenheft rules.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import bmc_const as C  # via conftest


PKG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "custom_components", "bennis_toolbox", "modules", "benni_media_context",
)
_spec = importlib.util.spec_from_file_location(
    "bmc_logic_pkg.volume_orchestrator",
    os.path.join(PKG_DIR, "volume_orchestrator.py"),
)
vol_mod = importlib.util.module_from_spec(_spec)
sys.modules["bmc_logic_pkg.volume_orchestrator"] = vol_mod
_spec.loader.exec_module(vol_mod)
sys.modules["bmc_vol_orch"] = vol_mod
V = vol_mod


def _settings(**overrides) -> "V.VolumeSettings":
    s = V.VolumeSettings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _decide(
    *,
    audio_owner=C.AUDIO_OWNER_NONE,
    bio_sleep=False,
    quiet_mode_active=False,
    bio_state=None,
    day_state=None,
    opening_any_open=False,
    homepods_configured=True,
    denon_configured=True,
    settings=None,
) -> "V.VolumeDecision":
    return V.decide_volume(
        audio_owner=audio_owner,
        bio_sleep=bio_sleep,
        quiet_mode_active=quiet_mode_active,
        bio_state=bio_state,
        day_state=day_state,
        opening_any_open=opening_any_open,
        homepods_configured=homepods_configured,
        denon_configured=denon_configured,
        settings=settings or V.VolumeSettings(),
    )


# ---------------------------------------------------------------------------
# Policy precedence
# ---------------------------------------------------------------------------


def test_idle_owner_none_zeros_both():
    vd = _decide()
    assert vd.policy == C.VOL_POLICY_IDLE
    assert vd.homepods_target == 0.0
    assert vd.denon_target == 0.0
    assert vd.apply_allowed is True


def test_blocked_when_no_speakers_configured():
    vd = _decide(homepods_configured=False, denon_configured=False)
    assert vd.policy == C.VOL_POLICY_BLOCKED
    assert vd.apply_allowed is False
    assert vd.homepods_target is None
    assert vd.denon_target is None
    assert vd.blocked_reason == "no_speakers_configured"


def test_muted_when_bio_sleep():
    vd = _decide(bio_sleep=True, audio_owner=C.AUDIO_OWNER_HOMEPODS)
    assert vd.policy == C.VOL_POLICY_MUTED
    assert vd.apply_allowed is False
    assert vd.homepods_target is None
    assert vd.denon_target is None
    assert vd.blocked_reason == "bio_sleep"


def test_ducked_when_quiet_mode_on_homepods_owner():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, quiet_mode_active=True)
    assert vd.policy == C.VOL_POLICY_DUCKED
    assert vd.apply_allowed is True
    assert vd.homepods_target == C.DEFAULT_VOL_DUCKED_TARGET
    assert vd.denon_target == 0.0


def test_ducked_when_quiet_mode_on_denon_owner():
    vd = _decide(audio_owner=C.AUDIO_OWNER_GAMING, quiet_mode_active=True)
    assert vd.policy == C.VOL_POLICY_DUCKED
    assert vd.denon_target == C.DEFAULT_VOL_DUCKED_TARGET
    assert vd.homepods_target == 0.0


def test_quiet_mode_wins_over_owner_routing():
    vd = _decide(audio_owner=C.AUDIO_OWNER_TV_DENON, quiet_mode_active=True)
    assert vd.policy == C.VOL_POLICY_DUCKED


# ---------------------------------------------------------------------------
# Owner routing for media policy
# ---------------------------------------------------------------------------


def test_owner_homepods_routes_volume_to_homepods():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS)
    assert vd.policy == C.VOL_POLICY_MEDIA
    assert vd.homepods_target == C.DEFAULT_VOL_HOMEPODS_BASE
    assert vd.denon_target == 0.0


def test_owner_tv_denon_routes_to_denon():
    vd = _decide(audio_owner=C.AUDIO_OWNER_TV_DENON)
    assert vd.policy == C.VOL_POLICY_MEDIA
    assert vd.homepods_target == 0.0
    assert vd.denon_target == C.DEFAULT_VOL_DENON_BASE


def test_owner_gaming_routes_to_denon():
    vd = _decide(audio_owner=C.AUDIO_OWNER_GAMING)
    assert vd.denon_target == C.DEFAULT_VOL_DENON_BASE
    assert vd.homepods_target == 0.0


def test_owner_private_routes_to_denon():
    vd = _decide(audio_owner=C.AUDIO_OWNER_PRIVATE)
    assert vd.denon_target == C.DEFAULT_VOL_DENON_BASE
    assert vd.homepods_target == 0.0


# ---------------------------------------------------------------------------
# Offsets and clamps
# ---------------------------------------------------------------------------


def test_night_day_state_applies_night_offset():
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        day_state="night",
    )
    assert vd.day_offset == C.DEFAULT_VOL_NIGHT_OFFSET
    # base 0.35 + (-0.10) = 0.25
    assert vd.homepods_target == 0.25


def test_late_night_day_state_applies_night_offset():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, day_state="late_night")
    assert vd.day_offset == C.DEFAULT_VOL_NIGHT_OFFSET


def test_edge_day_state_applies_edge_offset():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, day_state="late_evening")
    assert vd.day_offset == C.DEFAULT_VOL_EDGE_DAY_OFFSET
    # base 0.35 + (-0.05) = 0.30
    assert vd.homepods_target == 0.30


def test_unknown_day_state_no_offset():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, day_state="forenoon")
    assert vd.day_offset == 0.0
    assert vd.homepods_target == C.DEFAULT_VOL_HOMEPODS_BASE


def test_opening_any_open_applies_offset():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, opening_any_open=True)
    assert vd.opening_offset == C.DEFAULT_VOL_OPENING_OFFSET
    assert vd.homepods_target == 0.30


def test_offsets_stack_night_plus_opening():
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        day_state="night",
        opening_any_open=True,
    )
    # 0.35 + (-0.10) + (-0.05) = 0.20
    assert vd.homepods_target == 0.20


def test_active_min_clamps_target_floor():
    """Aggressive negative offsets must not push an active target
    below the configured floor."""
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        day_state="night",
        opening_any_open=True,
        settings=_settings(homepods_base=0.10, active_min=0.08),
    )
    # 0.10 - 0.10 - 0.05 = -0.05 → would clip to active_min=0.08
    assert vd.homepods_target == 0.08


def test_max_caps_above_settings_max():
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        settings=_settings(homepods_base=0.90, homepods_max=0.65),
    )
    assert vd.homepods_target == 0.65


def test_denon_max_caps():
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_TV_DENON,
        settings=_settings(denon_base=0.95, denon_max=0.70),
    )
    assert vd.denon_target == 0.70


def test_inactive_side_stays_zero_with_offsets():
    """Day/opening offsets must not bump the silent device above 0."""
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        day_state="late_evening",
        opening_any_open=True,
    )
    assert vd.denon_target == 0.0


# ---------------------------------------------------------------------------
# Configured surface
# ---------------------------------------------------------------------------


def test_missing_homepods_routes_volume_to_denon_only():
    vd = _decide(audio_owner=C.AUDIO_OWNER_HOMEPODS, homepods_configured=False)
    # No HomePods to address — target stays None.
    assert vd.homepods_target is None
    assert vd.denon_target == 0.0  # owner says homepods, denon idle


def test_missing_denon_owner_tv_denon_no_target():
    vd = _decide(audio_owner=C.AUDIO_OWNER_TV_DENON, denon_configured=False)
    assert vd.denon_target is None
    assert vd.homepods_target == 0.0


def test_idle_with_partial_speakers_only_sets_configured():
    vd = _decide(homepods_configured=True, denon_configured=False)
    assert vd.policy == C.VOL_POLICY_IDLE
    assert vd.homepods_target == 0.0
    assert vd.denon_target is None


# ---------------------------------------------------------------------------
# Echoed debug state
# ---------------------------------------------------------------------------


def test_decision_echoes_inputs_for_debug():
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        bio_state="awake", day_state="night",
        opening_any_open=True, quiet_mode_active=False,
    )
    assert vd.bio_state == "awake"
    assert vd.day_state == "night"
    assert vd.opening_any_open is True
    assert vd.quiet_mode_active is False
    assert vd.base_homepods_target == C.DEFAULT_VOL_HOMEPODS_BASE
    assert vd.effective_homepods_target == 0.20


def test_quiet_mode_does_not_offset_with_day_state():
    """Ducked target ignores day/opening offsets — it's a fixed value."""
    vd = _decide(
        audio_owner=C.AUDIO_OWNER_HOMEPODS,
        quiet_mode_active=True,
        day_state="night",
        opening_any_open=True,
    )
    assert vd.homepods_target == C.DEFAULT_VOL_DUCKED_TARGET
