"""Unit-Tests für benni_core_day_state.logic.

Deckt die Akzeptanzkriterien aus Lastenheft v1.1 §15 ab. Nummerierung
unten verweist auf AK-N aus dem LH. Reine Python-Tests, kein HA nötig.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

import bcds_const as C
import bcds_logic as L


# CEST (Sommer) und CET (Winter) — wir testen feste Offsets, nicht
# Umstellung selbst, weil DST orthogonal zu Phasenlogik ist.
TZ_SUMMER = timezone(timedelta(hours=2))
TZ_WINTER = timezone(timedelta(hours=1))


# Solar-Noon-Werte, die wir als realistisch annehmen.
def sn(year: int, month: int, day: int, hour: int, minute: int, *, tz=TZ_SUMMER):
    return datetime(year, month, day, hour, minute, tzinfo=tz)


# ─────────────────────────────────────────────────────────────────────────────
# Saisonaler Versatz (AK-5..7, AK-17, AK-18)
# ─────────────────────────────────────────────────────────────────────────────


def test_seasonal_factor_summer_peak_is_one():
    assert L.seasonal_factor(172) == pytest.approx(1.0)  # 21. Juni


def test_seasonal_factor_winter_trough_is_minus_one():
    # 21. Dezember ist DOY 355 — perfekt 183 Tage vom Peak entfernt
    # mit Rollover wird das zu dist=-182 → factor = 1 - 182/91.5 ≈ -0.989
    # exakter Tal-Wert liegt bei DOY 355 - rollover-Effekt: dist=-183, springt
    # auf dist=182 → factor = 1 - 182/91.5 ≈ -0.989. Beide Seiten symmetrisch.
    sf = L.seasonal_factor(355)
    assert sf < -0.95


def test_seasonal_factor_clamped_at_minus_one_at_perfect_trough():
    # Tag, der exakt 6 Monate vom Peak entfernt ist (172 - 183 = -11 mit
    # Rollover-Fix → factor wäre 1 - 183/91.5 = -1.0)
    # Praktisch decken DOY zwischen 354 und 356 das ab.
    factors = [L.seasonal_factor(d) for d in (354, 355, 356, 357)]
    assert min(factors) == pytest.approx(-1.0)


def test_seasonal_factor_rollover_handles_year_boundary():
    # AK-17/18 indirekt: kurz nach Neujahr noch im Winter-Bereich.
    assert L.seasonal_factor(1) < -0.5
    assert L.seasonal_factor(15) < -0.5


def test_seasonal_factor_equinox_near_zero():
    # 21. März ist DOY 80 (Frühlings-Tag-Nacht-Gleiche). Dreieckskurve
    # gibt hier eine Zwischenwert, nicht zwingend exakt 0 — wir checken
    # nur dass es nicht in den Extremen liegt.
    sf = L.seasonal_factor(80)
    assert -0.5 < sf < 0.5


def test_seasonal_offset_at_summer_peak_is_full_amplitude():
    # AK-7: maximal ±15 Minuten
    assert L.seasonal_offset_seconds(172) == 15 * 60


def test_seasonal_amplitude_never_exceeds_15_minutes():
    # AK-7
    for doy in range(1, 367):
        assert abs(L.seasonal_offset_seconds(doy)) <= 15 * 60 + 1


# ─────────────────────────────────────────────────────────────────────────────
# Anker (AK-5, AK-6, AK-10, AK-11, AK-17, AK-18)
# ─────────────────────────────────────────────────────────────────────────────


def test_morning_fix_summer_is_earlier():
    # AK-17: Sommer → morning_fix früher als 04:13
    now = datetime(2026, 6, 21, 12, 0, tzinfo=TZ_SUMMER)
    mf = L.morning_fix_for(now)
    assert mf.time() == time(3, 58)


def test_night_fix_summer_is_later():
    now = datetime(2026, 6, 21, 12, 0, tzinfo=TZ_SUMMER)
    nf = L.night_fix_for(now)
    assert nf.time() == time(23, 33)


def test_morning_fix_winter_is_later():
    # AK-18: Winter → morning_fix später als 04:13
    now = datetime(2026, 12, 21, 12, 0, tzinfo=TZ_WINTER)
    mf = L.morning_fix_for(now)
    assert mf.time() == time(4, 28)


def test_night_fix_winter_is_earlier():
    now = datetime(2026, 12, 21, 12, 0, tzinfo=TZ_WINTER)
    nf = L.night_fix_for(now)
    assert nf.time() == time(23, 3)


def test_midday_start_is_3h_before_solar_noon():
    # AK-10
    noon = sn(2026, 6, 21, 13, 22)
    assert L.midday_start_for(noon) == noon - timedelta(hours=3)


def test_evening_start_is_4h_after_solar_noon():
    # AK-11
    noon = sn(2026, 6, 21, 13, 22)
    assert L.evening_start_for(noon) == noon + timedelta(hours=4)


def test_late_night_start_uses_45_percent_split():
    # AK-13
    night_fix = datetime(2026, 6, 21, 23, 33, tzinfo=TZ_SUMMER)
    next_day_morning_fix = datetime(2026, 6, 22, 3, 58, tzinfo=TZ_SUMMER)
    lns = L.late_night_start_for(night_fix, next_day_morning_fix)
    span_seconds = (next_day_morning_fix - night_fix).total_seconds()
    expected_offset = span_seconds * 0.45
    actual_offset = (lns - night_fix).total_seconds()
    assert actual_offset == pytest.approx(expected_offset)


def test_monthly_splits_from_lh_tables():
    # AK-12: monatliche Faktoren aus LH §6 verbindlich
    assert C.MORNING_SPLIT_BY_MONTH[6] == 0.30  # Juni minimal
    assert C.MORNING_SPLIT_BY_MONTH[12] == 0.55  # Dezember maximal
    assert C.EVENING_SPLIT_BY_MONTH[6] == 0.60  # Juni maximal
    assert C.EVENING_SPLIT_BY_MONTH[12] == 0.30  # Dezember minimal


# ─────────────────────────────────────────────────────────────────────────────
# compute_day_state — Phasen-Resolution (AK-1..4, 19, 20)
# ─────────────────────────────────────────────────────────────────────────────


def test_summer_afternoon_resolves_to_afternoon():
    # AK-1, AK-2, AK-3, AK-4
    now = datetime(2026, 6, 21, 14, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.detail_phase == C.DetailPhase.AFTERNOON
    assert r.detail_phase.slug == "afternoon"
    assert r.master_phase == C.MasterPhase.MIDDAY
    assert r.detail_phase.value == 4
    assert r.master_phase.value == 3


def test_after_midnight_resolves_to_late_night():
    # AK-19: 00:00 – morning_fix liefert late_night
    now = datetime(2026, 6, 21, 2, 0, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.detail_phase == C.DetailPhase.LATE_NIGHT
    assert r.master_phase == C.MasterPhase.NIGHT


def test_just_before_midnight_resolves_to_early_night():
    # In [night_fix, midnight): noch early_night, weil late_night_start am
    # Folgetag liegt.
    now = datetime(2026, 6, 21, 23, 50, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.detail_phase == C.DetailPhase.EARLY_NIGHT


def test_started_at_in_early_post_midnight_window_falls_to_midnight():
    # Edge case: 00:30 ist late_night per LH, aber yesterday's
    # late_night_start liegt noch in der Zukunft (~01:32). Started_at darf
    # nicht in der Zukunft sein → fallback auf Mitternacht heute.
    now = datetime(2026, 6, 21, 0, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.current_phase_started_at <= now
    assert r.current_phase_started_at.time() == time(0, 0)


def test_started_at_after_yesterday_late_night_start_uses_option_i():
    # 02:00 ist nach yesterday's late_night_start (~01:32) — Option (i) greift.
    now = datetime(2026, 6, 21, 2, 0, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.current_phase_started_at <= now
    # ~01:32 today
    assert r.current_phase_started_at.hour == 1
    assert r.current_phase_started_at.day == 21


def test_day_state_signature_excludes_day_type_inputs():
    # AK-20: Day State darf keine Day-Context-Abhängigkeit haben. Das wird
    # bereits durch die Funktionssignatur garantiert — `compute_day_state`
    # akzeptiert nur `now` und `solar_noon`, keinen Wochentags-/Tagestyp-
    # Parameter. Dieser Test ist Sentinel, falls jemand die Signatur ändert.
    import inspect

    sig = inspect.signature(L.compute_day_state)
    assert set(sig.parameters.keys()) == {"now", "solar_noon"}


# ─────────────────────────────────────────────────────────────────────────────
# Attribute (AK-16)
# ─────────────────────────────────────────────────────────────────────────────


def test_all_required_attributes_present():
    # AK-16: alle Pflichtattribute vorhanden
    now = datetime(2026, 6, 21, 14, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)

    # Pflicht (LH §13.1)
    assert r.detail_phase is not None
    assert r.master_phase is not None
    assert len(r.phase_starts) == 8
    assert len(r.master_phase_starts) == 4
    assert r.current_phase_started_at is not None
    assert r.next_phase is not None
    assert r.next_phase_at is not None
    assert isinstance(r.minutes_until_next_phase, int)
    assert r.solar_noon_at is not None
    assert isinstance(r.solar_noon_fallback_active, bool)
    assert -1.0 <= r.seasonal_factor <= 1.0
    assert isinstance(r.seasonal_offset_minutes, float)


def test_master_phase_transition_attributes():
    # Wenn nächste Detail-Phase Master wechselt: next_master_phase gesetzt.
    # late_morning → forenoon: morning → midday.
    noon = sn(2026, 6, 21, 13, 22)
    # Wähle Zeitpunkt der definitiv in late_morning liegt: kurz vor midday_start
    midday_start = L.midday_start_for(noon)
    now = midday_start - timedelta(minutes=5)
    r = L.compute_day_state(now, noon)
    assert r.detail_phase == C.DetailPhase.LATE_MORNING
    assert r.next_phase == C.DetailPhase.FORENOON
    assert r.next_master_phase == C.MasterPhase.MIDDAY
    assert r.next_master_phase_at == midday_start


def test_master_phase_no_transition_within_same_master():
    # early_morning → late_morning: gleicher Master morning.
    now = datetime(2026, 6, 21, 4, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.detail_phase == C.DetailPhase.EARLY_MORNING
    assert r.next_phase == C.DetailPhase.LATE_MORNING
    assert r.next_master_phase is None
    assert r.next_master_phase_at is None


def test_phase_starts_are_hhmmss_strings():
    now = datetime(2026, 6, 21, 14, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    for slug, ts_str in r.phase_starts.items():
        assert isinstance(ts_str, str)
        assert len(ts_str.split(":")) == 3  # HH:MM:SS


# ─────────────────────────────────────────────────────────────────────────────
# Solar-Noon-Fallback (AK-9)
# ─────────────────────────────────────────────────────────────────────────────


def test_solar_noon_fallback_when_input_none():
    # AK-9
    now = datetime(2026, 6, 21, 14, 30, tzinfo=TZ_SUMMER)
    r = L.compute_day_state(now, None)
    assert r.solar_noon_fallback_active is True
    assert r.solar_noon_at.time() == time(12, 46)


def test_solar_noon_fallback_inactive_when_input_provided():
    now = datetime(2026, 6, 21, 14, 30, tzinfo=TZ_SUMMER)
    noon = sn(2026, 6, 21, 13, 22)
    r = L.compute_day_state(now, noon)
    assert r.solar_noon_fallback_active is False
    assert r.solar_noon_at == noon


def test_solar_noon_utc_input_is_converted_to_now_timezone():
    """Regression: sun.sun.next_noon kommt als UTC. Wenn der Input in einer
    anderen TZ kommt als now, müssen alle daraus abgeleiteten Anker in
    now's TZ landen — sonst zeigt `phase_starts` Mischformate (CEST für
    morning_fix, UTC für forenoon/afternoon/evening).
    """
    now = datetime(2026, 5, 25, 22, 0, tzinfo=TZ_SUMMER)
    # Solar Noon kommt als UTC (so wie sun.sun.next_noon es liefert).
    utc_noon = datetime(2026, 5, 25, 11, 28, tzinfo=timezone.utc)
    r = L.compute_day_state(now, utc_noon)

    # Alle abgeleiteten Anker müssen in CEST (now.tzinfo) sein.
    assert r.solar_noon_at.utcoffset() == TZ_SUMMER.utcoffset(None)
    assert r.midday_start_at.utcoffset() == TZ_SUMMER.utcoffset(None)
    assert r.evening_start_at.utcoffset() == TZ_SUMMER.utcoffset(None)
    assert r.late_evening_start_at.utcoffset() == TZ_SUMMER.utcoffset(None)

    # phase_starts in Lokalzeit, nicht UTC.
    # solar_noon 11:28 UTC = 13:28 CEST → afternoon startet 13:28.
    assert r.phase_starts["afternoon"] == "13:28:00"


# ─────────────────────────────────────────────────────────────────────────────
# Vollständigkeits-Test: alle 8 Phasen erreichbar
# ─────────────────────────────────────────────────────────────────────────────


def test_all_eight_phases_reachable_during_a_summer_day():
    # AK-2: alle Detailphasen exakt definiert + erreichbar.
    # 15-Minuten-Step nötig, weil early_night im Sommer nur ~27 Minuten lang
    # ist (23:33 bis Mitternacht, danach kippt LH-Regel auf late_night).
    noon = sn(2026, 6, 21, 13, 22)
    seen = set()
    base = datetime(2026, 6, 21, 0, 0, tzinfo=TZ_SUMMER)
    for minutes in range(0, 24 * 60, 15):
        now = base + timedelta(minutes=minutes)
        r = L.compute_day_state(now, noon)
        seen.add(r.detail_phase)
    assert seen == set(C.DetailPhase), f"missing phases: {set(C.DetailPhase) - seen}"
