"""Pure-engine tests for cover_policy.decide()."""
from __future__ import annotations

import pytest

import cp_const as C
import cp_policy as P


PROFILE = dict(C.DEFAULT_PROFILE)


def _ctx(**kw):
    return P.Context(**kw)


def _decide(ctx, **kwargs):
    defaults = dict(
        startup_ready=True,
        apply_enabled=True,
        manual_override_active=False,
        require_window=True,
        glare_lux_threshold=5000.0,
    )
    defaults.update(kwargs)
    return P.decide(ctx, PROFILE, **defaults)


# --------------------------------------------------------- window_open wins


def test_window_open_overrides_everything():
    ctx = _ctx(window_open=True, bio_state=C.BIO_SLEEP, heat_protect_active=True)
    d = _decide(ctx, manual_override_active=True)
    assert d.mode == C.MODE_WINDOW_OPEN
    assert d.target_position == PROFILE[C.MODE_WINDOW_OPEN]
    assert d.manual_override_cleared is True


def test_window_open_apply_allowed_respects_blockers():
    """window_open wins, but apply still blocked when startup not ready."""
    ctx = _ctx(window_open=True)
    d = _decide(ctx, startup_ready=False)
    assert d.mode == C.MODE_WINDOW_OPEN
    assert "startup_block" in d.blockers
    assert d.apply_allowed is False


# --------------------------------------------------------- manual override


def test_manual_override_blocks_normal_target():
    ctx = _ctx(window_open=False, bio_state=C.BIO_SLEEP)
    d = _decide(ctx, manual_override_active=True)
    assert d.mode == C.MODE_MANUAL
    assert d.target_position is None
    assert "manual_override" in d.blockers
    assert d.apply_allowed is False


# --------------------------------------------------------- startup block


def test_startup_block_marks_apply_disallowed_but_keeps_mode():
    ctx = _ctx(window_open=False, bio_state=C.BIO_AWAKE)
    d = _decide(ctx, startup_ready=False)
    assert d.mode == C.MODE_OPEN
    assert "startup_block" in d.blockers
    assert d.apply_allowed is False


# --------------------------------------------------------- unknown sources


def test_unknown_window_state_when_required_blocks():
    ctx = _ctx(window_open=None)
    d = _decide(ctx, require_window=True)
    assert "source_unknown:window" in d.blockers
    assert d.apply_allowed is False


def test_unknown_window_state_when_not_required_does_not_block():
    ctx = _ctx(window_open=None, bio_state=C.BIO_AWAKE)
    d = _decide(ctx, require_window=False)
    assert d.mode == C.MODE_OPEN
    assert not any(b.startswith("source_unknown") for b in d.blockers)
    assert d.apply_allowed is True


# --------------------------------------------------------- apply_enabled gate


def test_apply_disabled_keeps_mode_but_blocks_apply():
    ctx = _ctx(window_open=False, bio_state=C.BIO_AWAKE)
    d = _decide(ctx, apply_enabled=False)
    assert d.mode == C.MODE_OPEN
    assert "apply_disabled" in d.blockers
    assert d.apply_allowed is False


# --------------------------------------------------------- mode priority order


def test_heat_protect_beats_glare_and_normal_states():
    ctx = _ctx(
        window_open=False,
        heat_protect_active=True,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        media_context="movie",
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_HEAT_PROTECT


def test_glare_pc_beats_glare_tv():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        media_context="movie",
        gaming_source="pc",
        lux=8000,
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_GLARE_PC


def test_glare_tv_when_media_and_no_pc_gaming():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        media_context="movie",
        gaming_source="tv",
        lux=8000,
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_GLARE_TV


def test_glare_tv_skipped_at_night():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="early_night",
        media_context="movie",
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_SLEEP  # night-like dominates


def test_sleep_when_bio_sleep():
    ctx = _ctx(window_open=False, bio_state=C.BIO_SLEEP, day_state="afternoon")
    d = _decide(ctx)
    assert d.mode == C.MODE_SLEEP


def test_sleep_when_night_like_even_if_awake():
    ctx = _ctx(window_open=False, bio_state=C.BIO_AWAKE, day_state="late_night")
    d = _decide(ctx)
    assert d.mode == C.MODE_SLEEP


def test_wake_when_bio_waking_during_day():
    ctx = _ctx(window_open=False, bio_state=C.BIO_WAKING, day_state="late_morning")
    d = _decide(ctx)
    assert d.mode == C.MODE_WAKE


# --------------------------------------------------------- privacy


def test_privacy_only_when_household_empty_and_truly_away():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        presence_personal=C.PRESENCE_AWAY,
        presence_household=C.HOUSEHOLD_EMPTY,
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_PRIVACY


def test_bei_eltern_does_not_trigger_privacy():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        presence_personal=C.PRESENCE_PARENTS,
        presence_household=C.HOUSEHOLD_EMPTY,
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_OPEN  # default; no privacy from bei_eltern


def test_default_open_when_no_other_rule_fires():
    ctx = _ctx(
        window_open=False,
        bio_state=C.BIO_AWAKE,
        day_state="afternoon",
        presence_personal=C.PRESENCE_HOME,
    )
    d = _decide(ctx)
    assert d.mode == C.MODE_OPEN
    assert d.target_position == PROFILE[C.MODE_OPEN]


# --------------------------------------------------------- profile clamping


def test_decide_clamps_profile_values_to_0_100_range():
    bad_profile = dict(C.DEFAULT_PROFILE)
    bad_profile[C.MODE_OPEN] = 200
    bad_profile[C.MODE_SLEEP] = -50
    ctx = _ctx(window_open=False, bio_state=C.BIO_AWAKE)
    d = P.decide(ctx, bad_profile, startup_ready=True, apply_enabled=True,
                 manual_override_active=False, require_window=True)
    assert d.target_position == 100
    sleep_d = P.decide(
        _ctx(window_open=False, bio_state=C.BIO_SLEEP), bad_profile,
        startup_ready=True, apply_enabled=True, manual_override_active=False, require_window=True,
    )
    assert sleep_d.target_position == 0
