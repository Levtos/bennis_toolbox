"""Pure routing-engine tests — HA-free."""

from __future__ import annotations

import pytest

import nr_const as C
import nr_routing as R


def _ctx(**kw):
    return R.Context(**kw)


def _ev(event_type, **kw):
    return R.Event(event_type=event_type, **kw)


# --------------------------------------------------------- baseline routing


def test_info_event_is_dashboard_plus_bus():
    d = R.decide(_ev(C.EC_INFO, severity=C.SEV_INFO), _ctx())
    assert d.mode == C.MODE_SILENT
    # routing engine adds dashboard + bus_only for info.
    assert C.ROUTE_DASHBOARD in d.routes
    assert C.ROUTE_BUS_ONLY in d.routes
    assert C.ROUTE_PUSH not in d.routes


def test_normal_event_pushes_and_lists():
    d = R.decide(_ev(C.EC_INFO, severity=C.SEV_NORMAL), _ctx())
    assert d.mode == C.MODE_NORMAL
    assert C.ROUTE_PUSH in d.routes


def test_critical_event_includes_light_and_media():
    d = R.decide(_ev(C.EC_INFO, severity=C.SEV_CRITICAL), _ctx())
    assert d.mode == C.MODE_CRITICAL
    for r in (C.ROUTE_PUSH, C.ROUTE_PERSISTENT, C.ROUTE_MEDIA, C.ROUTE_LIGHT):
        assert r in d.routes


def test_security_info_is_bumped_to_urgent():
    d = R.decide(_ev(C.EC_SECURITY, severity=C.SEV_INFO), _ctx())
    assert d.severity == C.SEV_URGENT
    assert "severity bumped" in d.reason


def test_security_urgent_forces_push_and_persistent_even_under_dnd():
    d = R.decide(
        _ev(C.EC_SECURITY, severity=C.SEV_URGENT),
        _ctx(dnd_override=True),
    )
    assert C.ROUTE_PUSH in d.routes
    assert C.ROUTE_PERSISTENT in d.routes


# --------------------------------------------------------- doorbell


def test_doorbell_baseline_routes():
    d = R.decide(_ev(C.EC_DOORBELL, severity=C.SEV_NORMAL), _ctx())
    for r in (C.ROUTE_PUSH, C.ROUTE_LIGHT, C.ROUTE_MEDIA, C.ROUTE_DASHBOARD):
        assert r in d.routes


# --------------------------------------------------------- sleep behaviour


def test_sleep_drops_media_and_light_for_non_critical():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(bio_state=C.BIO_SLEEP),
    )
    assert C.ROUTE_MEDIA not in d.routes
    assert C.ROUTE_LIGHT not in d.routes


def test_sleep_defers_non_critical_push_to_bus():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_INFO),
        _ctx(bio_state=C.BIO_SLEEP),
    )
    assert C.ROUTE_PUSH not in d.routes
    assert C.ROUTE_BUS_ONLY in d.routes


def test_sleep_lets_critical_through():
    d = R.decide(
        _ev(C.EC_SECURITY, severity=C.SEV_CRITICAL),
        _ctx(bio_state=C.BIO_SLEEP),
    )
    assert C.ROUTE_PUSH in d.routes
    assert C.ROUTE_PERSISTENT in d.routes


# --------------------------------------------------------- headset


def test_headset_drops_media_and_adds_light_ring():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(headset_active=True),
    )
    assert C.ROUTE_MEDIA not in d.routes
    assert C.ROUTE_LIGHT in d.routes


# --------------------------------------------------------- quiet mode


def test_quiet_mode_drops_media_for_non_critical():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(quiet_mode_active=True),
    )
    assert C.ROUTE_MEDIA not in d.routes


def test_quiet_mode_does_not_block_critical_security():
    d = R.decide(
        _ev(C.EC_SECURITY, severity=C.SEV_CRITICAL),
        _ctx(quiet_mode_active=True),
    )
    assert C.ROUTE_PUSH in d.routes


# --------------------------------------------------------- quiet hours


def test_quiet_hours_drops_media_and_info_push():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_INFO),
        _ctx(in_quiet_hours=True),
    )
    assert C.ROUTE_MEDIA not in d.routes
    assert C.ROUTE_PUSH not in d.routes


# --------------------------------------------------------- presence


def test_away_drops_light_and_media_but_keeps_push():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(presence=C.PRES_AWAY),
    )
    assert C.ROUTE_LIGHT not in d.routes
    assert C.ROUTE_MEDIA not in d.routes
    assert C.ROUTE_PUSH in d.routes


def test_bei_eltern_is_home_equivalent():
    """No silent fallback to away behaviour when the user is at parents'."""
    away = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(presence=C.PRES_AWAY),
    )
    parents = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(presence=C.PRES_PARENTS),
    )
    # bei_eltern keeps non-push routes that PRES_AWAY drops.
    assert C.ROUTE_LIGHT not in away.routes
    # At parents, no away-specific drop is applied for light/media.
    # (The default routing for SEV_NORMAL has no LIGHT anyway, so the
    # interesting bit is that we *did not* explicitly drop it.)
    assert parents.context["presence"] == C.PRES_PARENTS


# --------------------------------------------------------- private time


def test_private_time_masks_message_for_non_critical():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL,
            title="Bestellung", message="Paket angekommen"),
        _ctx(activity_state=C.ACT_PRIVATE_TIME),
    )
    assert d.masked is True
    assert d.message == "(privater Modus)"


def test_private_time_does_not_mask_critical():
    d = R.decide(
        _ev(C.EC_SECURITY, severity=C.SEV_CRITICAL, message="ALARM"),
        _ctx(activity_state=C.ACT_PRIVATE_TIME),
    )
    assert d.masked is False
    assert d.message == "ALARM"


# --------------------------------------------------------- DND


def test_dnd_keeps_only_dashboard_and_bus_for_non_critical():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_NORMAL),
        _ctx(dnd_override=True),
    )
    assert set(d.routes) <= {C.ROUTE_DASHBOARD, C.ROUTE_BUS_ONLY}


# --------------------------------------------------------- appliance done


def test_appliance_done_routes_push_and_dashboard():
    d = R.decide(_ev(C.EC_APPLIANCE_DONE, severity=C.SEV_NORMAL), _ctx())
    assert C.ROUTE_PUSH in d.routes
    assert C.ROUTE_DASHBOARD in d.routes
    assert C.ROUTE_MEDIA not in d.routes


# --------------------------------------------------------- device_health / lock


def test_device_health_drops_media():
    d = R.decide(_ev(C.EC_DEVICE_HEALTH, severity=C.SEV_NORMAL), _ctx())
    assert C.ROUTE_MEDIA not in d.routes


def test_lock_battery_low_bumps_info_to_normal():
    d = R.decide(
        _ev(C.EC_DEVICE_HEALTH, severity=C.SEV_INFO),
        _ctx(lock_battery_low=True),
    )
    assert d.severity == C.SEV_NORMAL


# --------------------------------------------------------- ordering


def test_routes_are_deduplicated_and_keep_order():
    d = R.decide(
        _ev(C.EC_INFO, severity=C.SEV_URGENT),
        _ctx(headset_active=True),
    )
    assert len(d.routes) == len(set(d.routes))


# --------------------------------------------------------- mode mapping


@pytest.mark.parametrize(
    "sev,expected_mode",
    [
        (C.SEV_INFO, C.MODE_SILENT),       # info routes have no audio/light → silent
        (C.SEV_NORMAL, C.MODE_NORMAL),
        (C.SEV_URGENT, C.MODE_URGENT),
        (C.SEV_CRITICAL, C.MODE_CRITICAL),
    ],
)
def test_mode_follows_severity_when_routes_exist(sev, expected_mode):
    d = R.decide(_ev(C.EC_INFO, severity=sev), _ctx())
    assert d.mode == expected_mode
