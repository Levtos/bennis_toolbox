"""Pure computation rules for Benni Context.

This module contains no Home Assistant imports beyond ``dt_util`` and is fully
unit-testable. Every function is a pure projection from raw inputs to a
state value (plus, where needed, accompanying timestamps that the caller has
to persist).

Why pure functions? The presence / bio / activity rules are the trickiest part
of this integration — and the most exposed to user complaints when "the
heating started even though I was at my parents". Keeping the rules separate
from HA wiring lets us pin them down with a small test suite.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .const import (
    ACT_FREE_TIME,
    ACT_HOUSEHOLD,
    ACT_IDLE,
    ACT_PRIVATE,
    ACT_WORK_AWAY,
    ACT_WORK_HOME,
    BAND_FAR,
    BAND_HOME,
    BAND_NEAR,
    BAND_PREHEAT,
    BIO_AWAKE,
    BIO_SLEEP,
    BIO_WAKING,
    DAY_AFTERNOON,
    DAY_EARLY_EVENING,
    DAY_EARLY_MORNING,
    DAY_EARLY_NIGHT,
    DAY_FORENOON,
    DAY_LATE_EVENING,
    DAY_LATE_MORNING,
    DAY_LATE_NIGHT,
    DC_FREI,
    DC_WERKTAG,
    DC_WOCHENENDE,
    HH_EMPTY,
    HH_OCCUPIED,
    PERS_AWAY,
    PERS_HOME,
    PERS_PARENTS,
    TRANS_COMING_HOME,
    TRANS_LEAVING_HOME,
    TRANS_NONE,
    TRANS_PASSING,
)

# ---------------------------------------------------------------- helpers


def _is_home(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).lower() in ("home", "on", "true", "1", "yes")


def _is_fresh(ts: datetime | None, now: datetime, freshness_s: int) -> bool:
    if ts is None:
        return False
    return (now - ts) <= timedelta(seconds=freshness_s)


# --------------------------------------------------------- presence_personal


def compute_presence_personal(
    *,
    wlan_benni: str | None,
    wlan_benni_ts: datetime | None,
    wlan_eltern_1: str | None,
    wlan_eltern_2: str | None,
    gps_primary: str | None,
    gps_primary_ts: datetime | None,
    gps_secondary: str | None,
    gps_secondary_ts: datetime | None,
    now: datetime,
    freshness_s: int,
) -> str:
    """Decide ``zuhause`` / ``bei_eltern`` / ``abwesend``.

    Priority:

    1. Benni's WLAN tracker says ``home`` and is fresh → ``zuhause``.
    2. Either parents-WLAN tracker says ``home`` → ``bei_eltern``.
       (No freshness check: parents' router state is the ground truth, and a
       stale "home" reading there is still a strong signal that no automatic
       away-mode should fire.)
    3. Fresh GPS in home zone → ``zuhause``.
    4. Otherwise → ``abwesend``.

    Stale primary GPS falls back to secondary GPS, then to last-known WLAN
    state. We never silently degrade to ``abwesend`` on a single stale reading
    if a fresher source contradicts it.
    """
    # 1) WLAN benni
    if _is_home(wlan_benni) and _is_fresh(wlan_benni_ts, now, freshness_s):
        return PERS_HOME

    # 2) Parents WLAN — home equivalent. No freshness gate: a router seen as
    # "home" on the parents network is durable evidence that Benni is there.
    if _is_home(wlan_eltern_1) or _is_home(wlan_eltern_2):
        return PERS_PARENTS

    # 3) GPS with fallback
    fresh_primary = _is_fresh(gps_primary_ts, now, freshness_s)
    fresh_secondary = _is_fresh(gps_secondary_ts, now, freshness_s)

    if fresh_primary and _is_home(gps_primary):
        return PERS_HOME
    if fresh_secondary and _is_home(gps_secondary):
        return PERS_HOME

    # If WLAN benni was home but went stale, and GPS does not contradict,
    # keep zuhause to avoid a false-leaving event from a sleeping phone.
    if _is_home(wlan_benni) and not (fresh_primary or fresh_secondary):
        return PERS_HOME

    return PERS_AWAY


# --------------------------------------------------------- household


def compute_presence_household(personal: str, external_occupied: bool) -> str:
    if personal == PERS_HOME or external_occupied:
        return HH_OCCUPIED
    return HH_EMPTY


# --------------------------------------------------------- band


def compute_presence_band(
    *,
    distance_m: float | None,
    presence_personal: str,
    home_r: float,
    preheat_r: float,
    near_r: float,
    hysteresis_m: float,
    prev_band: str | None,
) -> str:
    """Bucket distance into home / preheat / near / far.

    Hysteresis is applied symmetrically: when leaving a band, the threshold is
    extended by ``hysteresis_m`` so a noisy GPS doesn't flap. When the
    personal state is ``zuhause``, the band is always ``home`` (the band must
    not be "far" while we are clearly inside, e.g. when GPS is stale but WLAN
    confirms home).
    """
    if presence_personal == PERS_HOME:
        return BAND_HOME
    if distance_m is None:
        # No proximity data: collapse to "far" unless we already had a more
        # specific band, in which case keep it (no spurious flips).
        return prev_band or BAND_FAR

    h = hysteresis_m if prev_band else 0.0

    def _hi(threshold: float) -> float:
        # extend threshold outward when leaving the inner band
        return threshold + h

    if prev_band == BAND_HOME:
        if distance_m <= _hi(home_r):
            return BAND_HOME
    if prev_band == BAND_PREHEAT:
        if distance_m <= _hi(preheat_r):
            return BAND_HOME if distance_m <= home_r else BAND_PREHEAT
    if prev_band == BAND_NEAR:
        if distance_m <= _hi(near_r):
            if distance_m <= home_r:
                return BAND_HOME
            if distance_m <= preheat_r:
                return BAND_PREHEAT
            return BAND_NEAR

    # Fresh classification
    if distance_m <= home_r:
        return BAND_HOME
    if distance_m <= preheat_r:
        return BAND_PREHEAT
    if distance_m <= near_r:
        return BAND_NEAR
    return BAND_FAR


# --------------------------------------------------------- transition


_BAND_ORDER = {BAND_FAR: 0, BAND_NEAR: 1, BAND_PREHEAT: 2, BAND_HOME: 3}


def compute_transition(
    *,
    prev_band: str | None,
    new_band: str,
    prev_personal: str | None,
    new_personal: str,
    direction: str | None,
    prev_transition: str,
    prev_started: datetime | None,
    now: datetime,
    hold_s: int,
) -> tuple[str, datetime | None]:
    """Compute the transition enum.

    ``coming_home`` only fires when the **previous real presence** was
    ``abwesend``. Coming back from ``bei_eltern`` is intentionally suppressed:
    we don't want heimkehr-radio when leaving the parents' Wi-Fi network and
    walking past the home zone on the way somewhere else.
    """
    # Hold-down: keep the previous transition for hold_s after it started.
    if (
        prev_transition != TRANS_NONE
        and prev_started is not None
        and (now - prev_started) < timedelta(seconds=hold_s)
    ):
        return prev_transition, prev_started

    if prev_band is None:
        return TRANS_NONE, None

    prev_idx = _BAND_ORDER.get(prev_band, 0)
    new_idx = _BAND_ORDER.get(new_band, 0)

    # coming_home: moving toward home AND the user genuinely was away.
    if new_idx > prev_idx and prev_personal == PERS_AWAY:
        if new_personal == PERS_HOME or new_band == BAND_HOME:
            return TRANS_COMING_HOME, now
        if direction and direction.lower() in ("towards", "approaching"):
            return TRANS_COMING_HOME, now

    # leaving_home: moving away from home AND we were just home.
    if new_idx < prev_idx and prev_personal == PERS_HOME:
        return TRANS_LEAVING_HOME, now

    # passing_through: was near/preheat but never reached home, now moving out.
    if (
        prev_band in (BAND_NEAR, BAND_PREHEAT)
        and new_band == BAND_FAR
        and prev_personal != PERS_HOME
    ):
        return TRANS_PASSING, now

    return TRANS_NONE, None


# --------------------------------------------------------- preheat


def compute_preheat(
    *,
    band: str,
    direction: str | None,
    presence_personal: str,
    prev_active: bool,
    prev_started: datetime | None,
    now: datetime,
    max_duration_s: int,
) -> tuple[bool, str | None, datetime | None]:
    """Preheat is on when band == preheat, user was away, and moving toward home.

    Preheat is auto-disarmed after ``max_duration_s`` so a parked car in the
    preheat ring doesn't keep the heating on indefinitely. It also disarms
    immediately when the user reaches home or goes back to far/parents.
    """
    # Disarm conditions
    if presence_personal == PERS_HOME or band == BAND_HOME:
        return False, None, None
    if presence_personal == PERS_PARENTS:
        return False, None, None
    if band in (BAND_FAR, BAND_NEAR) and prev_active is False:
        return False, None, None

    # Max-duration cap
    if prev_active and prev_started is not None:
        if (now - prev_started) >= timedelta(seconds=max_duration_s):
            return False, "expired", prev_started

    # Activation
    if band == BAND_PREHEAT:
        approaching = direction is None or direction.lower() in (
            "towards",
            "approaching",
        )
        if approaching:
            if prev_active and prev_started is not None:
                return True, "approach", prev_started
            return True, "approach", now

    # Sustain through far/near if already active and not capped
    if prev_active:
        return True, "sustain", prev_started

    return False, None, None


# --------------------------------------------------------- bio_state


_STRONG_INDICATORS = ("coffee", "door")
_SOFT_INDICATORS = ("pc", "ps5", "homeoffice")


def compute_bio_state(
    *,
    prev_state: str,
    wake_needed: bool,
    indicators: dict[str, bool],
    presence_personal: str,
    now: datetime,
    prev_sleep_start: datetime | None,
    prev_awake_start: datetime | None,
) -> tuple[str, datetime | None, datetime | None]:
    """Bio is the single source of truth for sleep/waking/awake.

    Rules:

    * ``sleep`` → ``waking`` when either the Wake Planner says ``wake_needed``
      or any soft/strong indicator fires.
    * ``waking`` → ``awake`` only on **strong** evidence: a strong indicator
      (coffee, door open) OR two soft indicators simultaneously. The Wake
      Planner alone never confirms awake — by design.
    * Leaving home while not asleep → awake (you can't physically leave while
      sleeping; this catches a missed transition).
    * Manual transitions (services.py) flow through this function by passing
      ``prev_state`` already set to the desired target.
    """
    sleep_start = prev_sleep_start
    awake_start = prev_awake_start

    strong = any(indicators.get(k) for k in _STRONG_INDICATORS)
    soft_count = sum(1 for k in _SOFT_INDICATORS if indicators.get(k))

    # Genuine departure forces awake — you can't be sleeping while walking out.
    if presence_personal == PERS_AWAY and prev_state != BIO_AWAKE:
        return BIO_AWAKE, sleep_start, now

    if prev_state == BIO_SLEEP:
        if wake_needed or strong or soft_count >= 1:
            return BIO_WAKING, sleep_start, awake_start
        return BIO_SLEEP, sleep_start, awake_start

    if prev_state == BIO_WAKING:
        if strong or soft_count >= 2:
            return BIO_AWAKE, sleep_start, now
        return BIO_WAKING, sleep_start, awake_start

    # prev_state == awake — only an explicit sleep service moves us back,
    # which is handled by the caller setting prev_state to BIO_SLEEP.
    return BIO_AWAKE, sleep_start, awake_start or now


# --------------------------------------------------------- day_state / context


def compute_day_state(local_now: datetime) -> str:
    h = local_now.hour
    if 5 <= h < 8:
        return DAY_EARLY_MORNING
    if 8 <= h < 10:
        return DAY_LATE_MORNING
    if 10 <= h < 12:
        return DAY_FORENOON
    if 12 <= h < 17:
        return DAY_AFTERNOON
    if 17 <= h < 19:
        return DAY_EARLY_EVENING
    if 19 <= h < 22:
        return DAY_LATE_EVENING
    if h >= 22 or h < 1:
        return DAY_EARLY_NIGHT
    return DAY_LATE_NIGHT  # 1 <= h < 5


def compute_day_context(local_now: datetime, holiday: bool) -> str:
    if holiday:
        return DC_FREI
    # weekday(): Monday=0 .. Sunday=6
    if local_now.weekday() >= 5:
        return DC_WOCHENENDE
    return DC_WERKTAG


# --------------------------------------------------------- activity


def compute_activity(
    *,
    bio: str,
    presence_personal: str,
    day_context: str,
    day_state: str,
    homeoffice: bool,
    private_active: bool,
    household_active: bool,
    media_context: str | None,
) -> str:
    """Pick the single dominant activity bucket.

    Order matters: work > private > household > free_time > idle.
    TV / gaming / cinema etc. live in ``media_context`` (attribute), not here.
    """
    if bio != BIO_AWAKE:
        return ACT_IDLE

    if homeoffice and presence_personal == PERS_HOME and day_context == DC_WERKTAG:
        return ACT_WORK_HOME
    if (
        presence_personal == PERS_AWAY
        and day_context == DC_WERKTAG
        and day_state in (DAY_LATE_MORNING, DAY_FORENOON, DAY_AFTERNOON)
    ):
        return ACT_WORK_AWAY

    if private_active:
        return ACT_PRIVATE
    if household_active:
        return ACT_HOUSEHOLD
    if media_context and media_context not in ("idle", "none", "off"):
        return ACT_FREE_TIME

    return ACT_IDLE
