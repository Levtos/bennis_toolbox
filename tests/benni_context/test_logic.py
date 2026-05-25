"""Unit tests for the Benni Context pure logic — HA-free."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import bc_const as C
import bc_logic as L
import bc_models as M


NOW = datetime(2026, 1, 12, 9, 0, tzinfo=timezone.utc)  # Monday 09:00 UTC
FRESH = NOW - timedelta(seconds=30)
STALE = NOW - timedelta(hours=2)


# ---------------------------------------------------------- presence_personal


def test_wlan_benni_home_wins():
    assert L.compute_presence_personal(
        wlan_benni="home", wlan_benni_ts=FRESH,
        wlan_eltern_1=None, wlan_eltern_2=None,
        gps_primary="away", gps_primary_ts=FRESH,
        gps_secondary=None, gps_secondary_ts=None,
        now=NOW, freshness_s=600,
    ) == C.PERS_HOME


def test_parents_wlan_without_freshness_marks_bei_eltern():
    assert L.compute_presence_personal(
        wlan_benni=None, wlan_benni_ts=None,
        wlan_eltern_1="home", wlan_eltern_2=None,
        gps_primary=None, gps_primary_ts=None,
        gps_secondary=None, gps_secondary_ts=None,
        now=NOW, freshness_s=600,
    ) == C.PERS_PARENTS


def test_stale_wlan_benni_with_no_gps_keeps_home():
    """A sleeping phone with stale WLAN but no contradicting GPS must not
    flip to abwesend — that's how false 'left home' events used to fire.
    """
    assert L.compute_presence_personal(
        wlan_benni="home", wlan_benni_ts=STALE,
        wlan_eltern_1=None, wlan_eltern_2=None,
        gps_primary=None, gps_primary_ts=None,
        gps_secondary=None, gps_secondary_ts=None,
        now=NOW, freshness_s=600,
    ) == C.PERS_HOME


def test_stale_wlan_with_fresh_away_gps_yields_abwesend():
    assert L.compute_presence_personal(
        wlan_benni="home", wlan_benni_ts=STALE,
        wlan_eltern_1=None, wlan_eltern_2=None,
        gps_primary="away", gps_primary_ts=FRESH,
        gps_secondary=None, gps_secondary_ts=None,
        now=NOW, freshness_s=600,
    ) == C.PERS_AWAY


def test_gps_secondary_fallback_when_primary_stale():
    assert L.compute_presence_personal(
        wlan_benni=None, wlan_benni_ts=None,
        wlan_eltern_1=None, wlan_eltern_2=None,
        gps_primary="away", gps_primary_ts=STALE,
        gps_secondary="home", gps_secondary_ts=FRESH,
        now=NOW, freshness_s=600,
    ) == C.PERS_HOME


# ----------------------------------------------------------------- household


def test_household_occupied_via_personal_home():
    assert L.compute_presence_household(C.PERS_HOME, False) == C.HH_OCCUPIED


def test_household_occupied_via_external_only():
    assert L.compute_presence_household(C.PERS_AWAY, True) == C.HH_OCCUPIED


def test_household_empty_when_personal_away_and_no_external():
    assert L.compute_presence_household(C.PERS_AWAY, False) == C.HH_EMPTY


# ---------------------------------------------------------------- band


def test_band_collapses_to_home_when_personal_home():
    assert L.compute_presence_band(
        distance_m=5000, presence_personal=C.PERS_HOME,
        home_r=100, preheat_r=800, near_r=3000, hysteresis_m=50,
        prev_band=C.BAND_FAR,
    ) == C.BAND_HOME


def test_band_fresh_buckets():
    args = dict(home_r=100, preheat_r=800, near_r=3000, hysteresis_m=50, prev_band=None,
                presence_personal=C.PERS_AWAY)
    assert L.compute_presence_band(distance_m=50, **args) == C.BAND_HOME
    assert L.compute_presence_band(distance_m=500, **args) == C.BAND_PREHEAT
    assert L.compute_presence_band(distance_m=2500, **args) == C.BAND_NEAR
    assert L.compute_presence_band(distance_m=5000, **args) == C.BAND_FAR


def test_band_hysteresis_keeps_inner_when_slightly_over_threshold():
    # In band_home with hysteresis, 140m (>home_r=100, <home_r+50) stays home.
    assert L.compute_presence_band(
        distance_m=140, presence_personal=C.PERS_AWAY,
        home_r=100, preheat_r=800, near_r=3000, hysteresis_m=50,
        prev_band=C.BAND_HOME,
    ) == C.BAND_HOME
    # 200m clearly breaks it.
    assert L.compute_presence_band(
        distance_m=200, presence_personal=C.PERS_AWAY,
        home_r=100, preheat_r=800, near_r=3000, hysteresis_m=50,
        prev_band=C.BAND_HOME,
    ) == C.BAND_PREHEAT


# ----------------------------------------------------------- transitions


def test_transition_coming_home_requires_prior_abwesend():
    state, started = L.compute_transition(
        prev_band=C.BAND_NEAR, new_band=C.BAND_HOME,
        prev_personal=C.PERS_AWAY, new_personal=C.PERS_HOME,
        direction="towards", prev_transition=C.TRANS_NONE,
        prev_started=None, now=NOW, hold_s=120,
    )
    assert state == C.TRANS_COMING_HOME
    assert started == NOW


def test_transition_coming_home_suppressed_when_coming_from_parents():
    state, _ = L.compute_transition(
        prev_band=C.BAND_NEAR, new_band=C.BAND_HOME,
        prev_personal=C.PERS_PARENTS, new_personal=C.PERS_HOME,
        direction="towards", prev_transition=C.TRANS_NONE,
        prev_started=None, now=NOW, hold_s=120,
    )
    assert state == C.TRANS_NONE


def test_transition_leaving_home():
    state, _ = L.compute_transition(
        prev_band=C.BAND_HOME, new_band=C.BAND_PREHEAT,
        prev_personal=C.PERS_HOME, new_personal=C.PERS_AWAY,
        direction=None, prev_transition=C.TRANS_NONE,
        prev_started=None, now=NOW, hold_s=120,
    )
    assert state == C.TRANS_LEAVING_HOME


def test_transition_passing_through():
    state, _ = L.compute_transition(
        prev_band=C.BAND_NEAR, new_band=C.BAND_FAR,
        prev_personal=C.PERS_AWAY, new_personal=C.PERS_AWAY,
        direction="away", prev_transition=C.TRANS_NONE,
        prev_started=None, now=NOW, hold_s=120,
    )
    assert state == C.TRANS_PASSING


def test_transition_hold_keeps_previous_state():
    started = NOW - timedelta(seconds=10)
    state, kept_started = L.compute_transition(
        prev_band=C.BAND_HOME, new_band=C.BAND_HOME,
        prev_personal=C.PERS_HOME, new_personal=C.PERS_HOME,
        direction=None, prev_transition=C.TRANS_COMING_HOME,
        prev_started=started, now=NOW, hold_s=120,
    )
    assert state == C.TRANS_COMING_HOME
    assert kept_started == started


# --------------------------------------------------------------- preheat


def test_preheat_arms_on_approaching_preheat_band():
    active, source, started = L.compute_preheat(
        band=C.BAND_PREHEAT, direction="towards",
        presence_personal=C.PERS_AWAY,
        prev_active=False, prev_started=None,
        now=NOW, max_duration_s=900,
    )
    assert active is True
    assert source == "approach"
    assert started == NOW


def test_preheat_disarmed_when_at_home():
    active, _, _ = L.compute_preheat(
        band=C.BAND_HOME, direction=None,
        presence_personal=C.PERS_HOME,
        prev_active=True, prev_started=NOW - timedelta(seconds=200),
        now=NOW, max_duration_s=900,
    )
    assert active is False


def test_preheat_caps_after_max_duration():
    started_long_ago = NOW - timedelta(seconds=1000)
    active, source, _ = L.compute_preheat(
        band=C.BAND_PREHEAT, direction="towards",
        presence_personal=C.PERS_AWAY,
        prev_active=True, prev_started=started_long_ago,
        now=NOW, max_duration_s=900,
    )
    assert active is False
    assert source == "expired"


# -------------------------------------------------------------- bio_state


def test_bio_sleep_to_waking_via_wake_needed():
    state, _, _ = L.compute_bio_state(
        prev_state=C.BIO_SLEEP, wake_needed=True, indicators={},
        presence_personal=C.PERS_HOME, day_state=C.DAY_LATE_MORNING, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_WAKING


def test_bio_sleep_to_awake_via_strong_indicator_in_daytime():
    state, _, awake_start = L.compute_bio_state(
        prev_state=C.BIO_SLEEP, wake_needed=False,
        indicators={"coffee": True},
        presence_personal=C.PERS_HOME, day_state=C.DAY_LATE_MORNING, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_AWAKE
    assert awake_start == NOW


def test_bio_waking_to_awake_via_strong_indicator_in_daytime():
    state, _, awake_start = L.compute_bio_state(
        prev_state=C.BIO_WAKING, wake_needed=False,
        indicators={"coffee": True},
        presence_personal=C.PERS_HOME, day_state=C.DAY_LATE_MORNING, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_AWAKE
    assert awake_start == NOW


def test_bio_soft_indicator_wakes_directly_in_daytime():
    state, _, _ = L.compute_bio_state(
        prev_state=C.BIO_SLEEP, wake_needed=False,
        indicators={"pc": True},
        presence_personal=C.PERS_HOME, day_state=C.DAY_LATE_MORNING, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_AWAKE


def test_bio_homeoffice_indicator_does_not_wake():
    state, _, awake_start = L.compute_bio_state(
        prev_state=C.BIO_SLEEP, wake_needed=False,
        indicators={"homeoffice": True},
        presence_personal=C.PERS_HOME, day_state=C.DAY_LATE_MORNING, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_SLEEP
    assert awake_start is None


def test_bio_activity_wake_indicators_are_blocked_at_night():
    for day_state in (C.DAY_EARLY_NIGHT, C.DAY_LATE_NIGHT, None):
        state, _, awake_start = L.compute_bio_state(
            prev_state=C.BIO_SLEEP, wake_needed=False,
            indicators={"coffee": True, "pc": True, "ps5": True, "door": True},
            presence_personal=C.PERS_HOME, day_state=day_state, now=NOW,
            prev_sleep_start=None, prev_awake_start=None,
        )
        assert state == C.BIO_SLEEP
        assert awake_start is None


def test_bio_forced_awake_when_leaving_while_not_awake():
    state, _, awake_start = L.compute_bio_state(
        prev_state=C.BIO_SLEEP, wake_needed=False, indicators={},
        presence_personal=C.PERS_AWAY, day_state=C.DAY_LATE_NIGHT, now=NOW,
        prev_sleep_start=None, prev_awake_start=None,
    )
    assert state == C.BIO_AWAKE
    assert awake_start == NOW


# ----------------------------------------------------------- day_state


def test_day_state_buckets():
    cases = [
        (6, C.DAY_EARLY_MORNING),
        (9, C.DAY_LATE_MORNING),
        (11, C.DAY_FORENOON),
        (15, C.DAY_AFTERNOON),
        (18, C.DAY_EARLY_EVENING),
        (20, C.DAY_LATE_EVENING),
        (23, C.DAY_EARLY_NIGHT),
        (3, C.DAY_LATE_NIGHT),
    ]
    for hour, expected in cases:
        local = NOW.replace(hour=hour)
        assert L.compute_day_state(local) == expected, hour


def test_day_context_holiday_beats_weekday():
    assert L.compute_day_context(NOW, holiday=True) == C.DC_FREI


def test_day_context_weekday_vs_weekend():
    # NOW is Monday → werktag
    assert L.compute_day_context(NOW, holiday=False) == C.DC_WERKTAG
    sat = NOW + timedelta(days=5)
    assert L.compute_day_context(sat, holiday=False) == C.DC_WOCHENENDE


# ------------------------------------------------------------- activity


def test_activity_idle_when_sleeping():
    assert L.compute_activity(
        bio=C.BIO_SLEEP, presence_personal=C.PERS_HOME,
        day_context=C.DC_WERKTAG, day_state=C.DAY_AFTERNOON,
        homeoffice=True, private_active=False,
        household_active=False, media_context="tv",
    ) == C.ACT_SLEEP


def test_activity_waking_is_explicit_state():
    assert L.compute_activity(
        bio=C.BIO_WAKING, presence_personal=C.PERS_HOME,
        day_context=C.DC_WERKTAG, day_state=C.DAY_AFTERNOON,
        homeoffice=True, private_active=True,
        household_active=True, media_context="tv",
    ) == C.ACT_WAKING


def test_activity_private_beats_work_home():
    assert L.compute_activity(
        bio=C.BIO_AWAKE, presence_personal=C.PERS_HOME,
        day_context=C.DC_WERKTAG, day_state=C.DAY_AFTERNOON,
        homeoffice=True, private_active=True,
        household_active=False, media_context=None,
    ) == C.ACT_PRIVATE


def test_activity_work_home_when_private_inactive():
    assert L.compute_activity(
        bio=C.BIO_AWAKE, presence_personal=C.PERS_HOME,
        day_context=C.DC_WERKTAG, day_state=C.DAY_AFTERNOON,
        homeoffice=True, private_active=False,
        household_active=False, media_context=None,
    ) == C.ACT_WORK_HOME


def test_activity_does_not_infer_work_away_from_presence_alone():
    assert L.compute_activity(
        bio=C.BIO_AWAKE, presence_personal=C.PERS_AWAY,
        day_context=C.DC_WERKTAG, day_state=C.DAY_AFTERNOON,
        homeoffice=False, private_active=False,
        household_active=False, media_context=None,
    ) == C.ACT_IDLE


def test_activity_free_time_via_media_context():
    assert L.compute_activity(
        bio=C.BIO_AWAKE, presence_personal=C.PERS_HOME,
        day_context=C.DC_WOCHENENDE, day_state=C.DAY_EARLY_EVENING,
        homeoffice=False, private_active=False,
        household_active=False, media_context="tv",
    ) == C.ACT_FREE_TIME


def test_activity_private_beats_household_and_free_time():
    assert L.compute_activity(
        bio=C.BIO_AWAKE, presence_personal=C.PERS_HOME,
        day_context=C.DC_FREI, day_state=C.DAY_LATE_EVENING,
        homeoffice=False, private_active=True,
        household_active=True, media_context="tv",
    ) == C.ACT_PRIVATE


# ------------------------------------------------------------- models


def test_persistent_state_round_trip():
    raw = M.PersistentState(
        bio_state=C.BIO_AWAKE,
        last_awake_start="2026-01-12T09:00:00+00:00",
        preheat_active=True,
        preheat_source="approach",
        preheat_started="2026-01-12T08:45:00+00:00",
    ).to_dict()
    rebuilt = M.PersistentState.from_dict(raw)
    assert rebuilt.bio_state == C.BIO_AWAKE
    assert rebuilt.preheat_active is True
    assert rebuilt.preheat_source == "approach"


def test_persistent_state_from_empty_uses_defaults():
    s = M.PersistentState.from_dict(None)
    assert s.bio_state == C.BIO_SLEEP
    assert s.preheat_active is False
