"""HB is Home Baseline, not Away Cut.

Until 0.3.5.2 the engine treated HB and AC almost identically — both
returned `DESIRED_OFF` on truly-away + idle. That contradicts the
Einhornzentrale semantics: HB is a *baseline* policy that must never
schedule an automatic off; only AC (Away Cut) is allowed to cut.

These tests pin the corrected semantics so the regression cannot
recur silently.
"""
from __future__ import annotations

import pp_const as C
import pp_engine as E


def _cfg(**kw):
    base = dict(
        device_id="d", name="Test", switch_entity="switch.x",
        policy=C.POLICY_HB, kind=C.KIND_GENERIC,
        power_entity="sensor.p",
        active_threshold=5.0, idle_threshold=2.0,
    )
    base.update(kw)
    return E.DeviceConfig(**base)


def _state(**kw):
    return E.DeviceState(**kw)


def _ctx(**kw):
    base = dict(presence=C.PRESENCE_HOME, bio=C.BIO_AWAKE, now_ts=1000.0)
    base.update(kw)
    return E.GlobalContext(**base)


# ---------------------------------------------------------------------------
# Generic device
# ---------------------------------------------------------------------------


def test_hb_generic_idle_truly_away_keeps_not_off():
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB),
        _state(switch_state="on", power_w=0.5),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert d.reason.startswith("HB:")
    assert "no baseline action" in d.reason or "no away-cut" in d.reason


def test_ac_generic_idle_truly_away_cuts():
    d = E.evaluate(
        _cfg(policy=C.POLICY_AC),
        _state(switch_state="on", power_w=0.5),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_OFF
    assert d.reason.startswith("AC:")


def test_hb_generic_active_remains_keep_via_never_cut_when_active():
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB, never_cut_when_active=True),
        _state(switch_state="on", power_w=80.0),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "active" in d.blockers


def test_hb_unknown_power_keeps_when_assume_active():
    """unknown_behavior=assume_active makes unknown count as active —
    never_cut_when_active then protects the device under HB."""
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB, never_cut_when_active=True,
             unknown_behavior=C.UNK_ASSUME_ACTIVE),
        _state(switch_state="on", power_w="unknown"),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "active" in d.blockers


# ---------------------------------------------------------------------------
# bei_eltern is always home-equivalent for both HB and AC.
# ---------------------------------------------------------------------------


def test_hb_bei_eltern_keeps():
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB),
        _state(switch_state="on", power_w=0.5),
        _ctx(presence=C.PRESENCE_AT_PARENTS),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "bei_eltern" in d.reason


def test_ac_bei_eltern_keeps():
    d = E.evaluate(
        _cfg(policy=C.POLICY_AC),
        _state(switch_state="on", power_w=0.5),
        _ctx(presence=C.PRESENCE_AT_PARENTS),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "bei_eltern" in d.reason


# ---------------------------------------------------------------------------
# Appliance: HB keeps, AC cuts. Running / unknown always protected.
# ---------------------------------------------------------------------------


def test_hb_appliance_idle_truly_away_keeps():
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB, kind=C.KIND_APPLIANCE,
             unknown_behavior=C.UNK_ASSUME_IDLE),
        _state(switch_state="on", power_w=0.0),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "HB" in d.reason


def test_ac_appliance_idle_truly_away_cuts():
    d = E.evaluate(
        _cfg(policy=C.POLICY_AC, kind=C.KIND_APPLIANCE,
             unknown_behavior=C.UNK_ASSUME_IDLE),
        _state(switch_state="on", power_w=0.0),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_OFF


def test_hb_appliance_running_still_protected():
    d = E.evaluate(
        _cfg(policy=C.POLICY_HB, kind=C.KIND_APPLIANCE),
        _state(switch_state="on", power_w=1200.0),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "program_running" in d.blockers


def test_ac_appliance_running_still_protected():
    d = E.evaluate(
        _cfg(policy=C.POLICY_AC, kind=C.KIND_APPLIANCE),
        _state(switch_state="on", power_w=1200.0),
        _ctx(presence=C.PRESENCE_AWAY),
    )
    assert d.desired_switch_state == C.DESIRED_KEEP
    assert "program_running" in d.blockers


def test_appliance_unknown_power_protected_under_hb_and_ac():
    for policy in (C.POLICY_HB, C.POLICY_AC):
        d = E.evaluate(
            _cfg(policy=policy, kind=C.KIND_APPLIANCE,
                 unknown_behavior=C.UNK_ASSUME_ACTIVE),
            _state(switch_state="on", power_w="unknown"),
            _ctx(presence=C.PRESENCE_AWAY),
        )
        assert d.desired_switch_state == C.DESIRED_KEEP, policy
        assert "power_unknown" in d.blockers, policy
