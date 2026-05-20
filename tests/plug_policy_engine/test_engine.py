"""Unit tests for the Plug Policy decision engine — HA-free."""

from __future__ import annotations

import pytest

import pp_const as C
import pp_engine as E


# --------------------------------------------------------------- builders


def _ctx(**kw):
    return E.GlobalContext(**kw)


def _cfg(**overrides):
    base = dict(
        device_id="dev1",
        name="Test Device",
        switch_entity="switch.test",
        policy=C.POLICY_HB,
        kind=C.KIND_GENERIC,
    )
    base.update(overrides)
    return E.DeviceConfig(**base)


def _state(**overrides):
    s = E.DeviceState()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# --------------------------------------------------------------- AO / CS


def test_ao_keeps_on_when_already_on():
    d = E.evaluate(_cfg(policy=C.POLICY_AO), _state(switch_state="on"), _ctx())
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "already on" in d.reason


def test_ao_turns_on_when_off():
    d = E.evaluate(_cfg(policy=C.POLICY_AO), _state(switch_state="off"), _ctx())
    assert d.desired_switch_state == C.DESIRED_ON


def test_cs_behaves_like_ao_for_charging_safe():
    d = E.evaluate(_cfg(policy=C.POLICY_CS), _state(switch_state="off"), _ctx())
    assert d.desired_switch_state == C.DESIRED_ON
    assert "CS" in d.reason


# --------------------------------------------------------------- HB / AC


def test_hb_protects_active_device_even_when_away():
    cfg = _cfg(policy=C.POLICY_HB, power_entity="sensor.p", active_threshold=5.0)
    st = _state(switch_state="on", power_w=80.0)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "active" in d.blockers


def test_hb_cuts_when_idle_and_truly_away():
    cfg = _cfg(policy=C.POLICY_HB, power_entity="sensor.p", idle_threshold=2.0)
    st = _state(switch_state="on", power_w=0.5)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_OFF


def test_hb_does_not_cut_when_at_parents():
    """bei_eltern is home-equivalent — never trigger an away cut."""
    cfg = _cfg(policy=C.POLICY_HB, power_entity="sensor.p", idle_threshold=2.0)
    st = _state(switch_state="on", power_w=0.5)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AT_PARENTS))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "bei_eltern" in d.blockers[0]


def test_ac_cuts_when_truly_away_idle():
    cfg = _cfg(policy=C.POLICY_AC, power_entity="sensor.p", idle_threshold=2.0)
    st = _state(switch_state="on", power_w=0.0)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_OFF


# --------------------------------------------------------------- SC


def test_sc_turns_on_when_home_awake_and_allowed_phase():
    cfg = _cfg(policy=C.POLICY_SC, allowed_contexts=[C.DAY_DAY, C.DAY_EVENING])
    d = E.evaluate(
        cfg, _state(switch_state="off"),
        _ctx(presence=C.PRESENCE_HOME, bio=C.BIO_AWAKE, day_phase=C.DAY_DAY),
    )
    assert d.desired_switch_state == C.DESIRED_ON


def test_sc_cuts_when_phase_not_allowed():
    cfg = _cfg(policy=C.POLICY_SC, allowed_contexts=[C.DAY_EVENING])
    d = E.evaluate(
        cfg, _state(switch_state="on"),
        _ctx(presence=C.PRESENCE_HOME, bio=C.BIO_AWAKE, day_phase=C.DAY_MORNING),
    )
    assert d.desired_switch_state == C.DESIRED_OFF
    assert "day_phase" in d.reason


def test_sc_cuts_when_user_is_sleeping():
    cfg = _cfg(policy=C.POLICY_SC, allowed_contexts=[C.DAY_DAY])
    d = E.evaluate(
        cfg, _state(switch_state="on"),
        _ctx(presence=C.PRESENCE_HOME, bio=C.BIO_SLEEP, day_phase=C.DAY_DAY),
    )
    assert d.desired_switch_state == C.DESIRED_OFF


# --------------------------------------------------------------- PC kind


def test_pc_protected_when_active():
    cfg = _cfg(kind=C.KIND_PC, policy=C.POLICY_HB, power_entity="sensor.p")
    st = _state(switch_state="on", power_w=120)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY, bio=C.BIO_SLEEP))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "pc_active" in d.blockers


def test_pc_cut_when_sleeping_and_idle():
    cfg = _cfg(kind=C.KIND_PC, policy=C.POLICY_HB,
               power_entity="sensor.p", idle_threshold=2.0)
    st = _state(switch_state="on", power_w=0.0)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_HOME, bio=C.BIO_SLEEP))
    assert d.desired_switch_state == C.DESIRED_OFF


def test_pc_manual_cooldown_blocks_cut():
    cfg = _cfg(kind=C.KIND_PC, policy=C.POLICY_HB,
               power_entity="sensor.p", idle_threshold=2.0,
               manual_on_cooldown_seconds=900)
    st = _state(switch_state="on", power_w=0.0, manual_on_until_ts=2000.0)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_HOME, bio=C.BIO_SLEEP, now_ts=1500.0))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "manual_on_cooldown" in d.blockers


# --------------------------------------------------------------- appliance


def test_appliance_never_interrupted_while_active():
    cfg = _cfg(kind=C.KIND_APPLIANCE, policy=C.POLICY_HB,
               power_entity="sensor.p", active_threshold=5.0)
    st = _state(switch_state="on", power_w=1200)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "program_running" in d.blockers


def test_appliance_unknown_power_protected():
    cfg = _cfg(kind=C.KIND_APPLIANCE, policy=C.POLICY_HB,
               power_entity="sensor.p",
               unknown_behavior=C.UNK_ASSUME_ACTIVE)
    st = _state(switch_state="on", power_w="unknown")
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_KEEP


def test_appliance_idle_and_away_cuts():
    cfg = _cfg(kind=C.KIND_APPLIANCE, policy=C.POLICY_HB,
               power_entity="sensor.p", idle_threshold=2.0,
               unknown_behavior=C.UNK_ASSUME_IDLE)
    st = _state(switch_state="on", power_w=0.0)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_OFF


# --------------------------------------------------------------- bias light


def test_bias_light_on_when_entertainment_active():
    cfg = _cfg(kind=C.KIND_BIAS_LIGHT, policy=C.POLICY_HB)
    d = E.evaluate(cfg, _state(switch_state="off"),
                   _ctx(entertainment_active=True))
    assert d.desired_switch_state == C.DESIRED_ON


def test_bias_light_on_via_media_context_movie():
    cfg = _cfg(kind=C.KIND_BIAS_LIGHT, policy=C.POLICY_HB)
    d = E.evaluate(cfg, _state(switch_state="off"),
                   _ctx(media_context="movie"))
    assert d.desired_switch_state == C.DESIRED_ON


def test_bias_light_off_when_idle_media():
    cfg = _cfg(kind=C.KIND_BIAS_LIGHT, policy=C.POLICY_HB)
    d = E.evaluate(cfg, _state(switch_state="on"),
                   _ctx(media_context="idle", entertainment_active=False))
    assert d.desired_switch_state == C.DESIRED_OFF


# --------------------------------------------------------------- diffuser


def test_diffuser_stops_on_sleep():
    cfg = _cfg(kind=C.KIND_DIFFUSER, policy=C.POLICY_HB)
    d = E.evaluate(cfg, _state(switch_state="on"),
                   _ctx(bio=C.BIO_SLEEP, presence=C.PRESENCE_HOME))
    assert d.desired_switch_state == C.DESIRED_OFF
    assert "bio=sleep" in d.blockers


def test_diffuser_stops_at_night_phase():
    cfg = _cfg(kind=C.KIND_DIFFUSER, policy=C.POLICY_HB)
    d = E.evaluate(cfg, _state(switch_state="on"),
                   _ctx(bio=C.BIO_AWAKE, presence=C.PRESENCE_HOME, day_phase=C.DAY_NIGHT))
    assert d.desired_switch_state == C.DESIRED_OFF


def test_diffuser_cycles_on_then_off():
    cfg = _cfg(kind=C.KIND_DIFFUSER, policy=C.POLICY_HB,
               diffuser_on_minutes=15, diffuser_off_minutes=15)
    on_phase = _state(switch_state="on", diffuser_phase="on", diffuser_phase_since_ts=0.0)
    # 16 minutes into on-phase → switch to off cycle
    d = E.evaluate(cfg, on_phase,
                   _ctx(bio=C.BIO_AWAKE, presence=C.PRESENCE_HOME,
                        day_phase=C.DAY_DAY, now_ts=16 * 60))
    assert d.desired_switch_state == C.DESIRED_OFF
    assert "on-phase elapsed" in d.reason


# --------------------------------------------------------------- tablet


def test_tablet_deep_discharge_guard_charges_under_20pct():
    cfg = _cfg(kind=C.KIND_TABLET, policy=C.POLICY_HB,
               tablet_low=40, tablet_high=80,
               battery_entity="sensor.batt")
    d = E.evaluate(cfg, _state(switch_state="off", battery_pct=15),
                   _ctx())
    assert d.desired_switch_state == C.DESIRED_ON
    assert "deep_discharge_guard" in d.blockers


def test_tablet_charges_below_low_threshold():
    cfg = _cfg(kind=C.KIND_TABLET, tablet_low=40, tablet_high=80,
               battery_entity="sensor.batt")
    d = E.evaluate(cfg, _state(switch_state="off", battery_pct=35), _ctx())
    assert d.desired_switch_state == C.DESIRED_ON


def test_tablet_stops_charging_at_high_threshold():
    cfg = _cfg(kind=C.KIND_TABLET, tablet_low=40, tablet_high=80,
               battery_entity="sensor.batt")
    d = E.evaluate(cfg, _state(switch_state="on", battery_pct=82), _ctx())
    assert d.desired_switch_state == C.DESIRED_OFF


def test_tablet_holds_in_hysteresis_zone():
    cfg = _cfg(kind=C.KIND_TABLET, tablet_low=40, tablet_high=80,
               battery_entity="sensor.batt")
    d = E.evaluate(cfg, _state(switch_state="on", battery_pct=60), _ctx())
    assert d.desired_switch_state == C.DESIRED_KEEP


# --------------------------------------------------------------- suspended


def test_suspended_device_is_never_acted_on():
    cfg = _cfg(policy=C.POLICY_HB, power_entity="sensor.p", idle_threshold=2.0)
    st = _state(switch_state="on", power_w=0.0, suspended=True)
    d = E.evaluate(cfg, st, _ctx(presence=C.PRESENCE_AWAY))
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "policy_suspended" in d.blockers


# --------------------------------------------------------------- coffee


def test_coffee_maker_is_wake_signal_only():
    cfg = _cfg(kind=C.KIND_COFFEE, policy=C.POLICY_AO)
    d = E.evaluate(cfg, _state(switch_state="off"), _ctx(),
                   ha_just_started=True)
    assert d.desired_switch_state == C.DESIRED_ON
    assert "wake indicator" in d.reason
