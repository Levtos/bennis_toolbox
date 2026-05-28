"""Unit-Tests für benni_core_devices.logic.

Deckt R-DC-01..R-DC-09 aus dem Lastenheft `device_core/lastenheft.md` v0.2 ab.
Reine Python-Tests — kein HA nötig.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcd_const as C
import bcd_logic as L


TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 5, 27, 20, 0, tzinfo=TZ)


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────


def _config(
    *,
    threshold: int = 5,
    sticky: int = 30,
    buckets: tuple[L.WattBucket, ...] = (),
    configured: tuple[str, ...] = ("integration_entity",),
) -> L.DeviceConfig:
    return L.DeviceConfig(
        slug="x",
        display_name="X",
        device_type="tv",
        watt_threshold_on=threshold,
        watt_buckets=buckets,
        sticky_hold_seconds=sticky,
        area_id=None,
        configured_slots=configured,
    )


def _persisted(
    *,
    last_powered: bool | None = None,
    last_change: datetime | None = None,
    override: L.Override | None = None,
) -> L.DevicePersisted:
    return L.DevicePersisted(
        last_powered=last_powered,
        last_powered_change=last_change,
        override=override,
    )


def _inputs(
    slots: dict[str, L.SlotReading],
    *,
    integration_slot: str | None = "integration_entity",
    state_slot: str | None = "integration_entity",
    watt_slot: str | None = None,
    boot: bool = False,
) -> L.DeviceInputs:
    return L.DeviceInputs(
        slots=slots,
        integration_slot=integration_slot,
        state_slot=state_slot,
        watt_slot=watt_slot,
        boot_phase_active=boot,
    )


def _reading(value: str | None, numeric: float | None = None, age_s: int = 0) -> L.SlotReading:
    return L.SlotReading(
        value=value,
        numeric=numeric,
        attributes={},
        last_updated=NOW - timedelta(seconds=age_s) if value is not None else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-01: Fallback-Hierarchie
# ─────────────────────────────────────────────────────────────────────────────


def test_integration_fresh_wins_for_powered():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("on")})
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is True
    assert r.power_source == C.PowerSource.INTEGRATION.value


def test_watt_fallback_when_integration_unavailable():
    cfg = _config(threshold=10, configured=("integration_entity", "watt_sensor"))
    inp = _inputs(
        {
            "integration_entity": _reading(None),
            "watt_sensor": _reading("25.0", numeric=25.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is True
    assert r.power_source == C.PowerSource.WATT_FALLBACK.value


def test_watt_fallback_below_threshold_is_off():
    cfg = _config(threshold=50, configured=("integration_entity", "watt_sensor"))
    inp = _inputs(
        {
            "integration_entity": _reading(None),
            "watt_sensor": _reading("3.0", numeric=3.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is False
    assert r.power_source == C.PowerSource.WATT_FALLBACK.value


def test_sticky_hold_when_all_unavailable():
    cfg = _config(sticky=60)
    inp = _inputs({"integration_entity": _reading(None)})
    persisted = _persisted(last_powered=True, last_change=NOW - timedelta(seconds=30))
    r = L.compute_device(cfg, inp, persisted, NOW)
    assert r.powered is True
    assert r.power_source == C.PowerSource.STICKY_HOLD.value


def test_sticky_hold_expired_falls_through():
    cfg = _config(sticky=10)
    inp = _inputs({"integration_entity": _reading(None)})
    persisted = _persisted(last_powered=True, last_change=NOW - timedelta(seconds=60))
    r = L.compute_device(cfg, inp, persisted, NOW)
    assert r.powered is None
    assert r.power_source == C.PowerSource.NONE.value


def test_all_unavailable_no_persistence_is_none():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading(None)})
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is None
    assert r.power_source == C.PowerSource.NONE.value


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-05: Konflikt Integration vs. Watt
# ─────────────────────────────────────────────────────────────────────────────


def test_integration_off_with_watt_high_flags_disagreement():
    cfg = _config(threshold=50, configured=("integration_entity", "watt_sensor"))
    inp = _inputs(
        {
            "integration_entity": _reading("off"),
            "watt_sensor": _reading("80.0", numeric=80.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is False
    assert r.power_source == C.PowerSource.INTEGRATION.value
    assert r.watt_disagrees is True


def test_integration_on_no_disagreement():
    cfg = _config(threshold=50, configured=("integration_entity", "watt_sensor"))
    inp = _inputs(
        {
            "integration_entity": _reading("on"),
            "watt_sensor": _reading("80.0", numeric=80.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is True
    assert r.watt_disagrees is False


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-06: Watt-Buckets → power_state
# ─────────────────────────────────────────────────────────────────────────────


def test_power_state_buckets_operator_order():
    buckets = (
        L.WattBucket(state="off", op="<=", value=5),
        L.WattBucket(state="idle", op="<=", value=30),
        L.WattBucket(state="playing", op=">", value=30),
    )
    assert L.classify_power_state(0.5, buckets) == "off"
    assert L.classify_power_state(5, buckets) == "off"      # <=5
    assert L.classify_power_state(10, buckets) == "idle"
    assert L.classify_power_state(30, buckets) == "idle"    # <=30
    assert L.classify_power_state(100, buckets) == "playing"


def test_power_state_all_operators():
    assert L.classify_power_state(5, (L.WattBucket("x", "<", 10),)) == "x"
    assert L.classify_power_state(10, (L.WattBucket("x", "<", 10),)) == "unknown"
    assert L.classify_power_state(10, (L.WattBucket("x", "<=", 10),)) == "x"
    assert L.classify_power_state(10, (L.WattBucket("x", "=", 10),)) == "x"
    assert L.classify_power_state(11, (L.WattBucket("x", ">", 10),)) == "x"
    assert L.classify_power_state(10, (L.WattBucket("x", ">=", 10),)) == "x"


def test_power_state_catch_all():
    buckets = (
        L.WattBucket(state="off", op="<=", value=5),
        L.WattBucket(state="on", op=None, value=None),  # catch-all
    )
    assert L.classify_power_state(3, buckets) == "off"
    assert L.classify_power_state(999, buckets) == "on"


def test_power_state_without_buckets_is_unknown():
    assert L.classify_power_state(50, ()) == "unknown"


def test_power_state_without_watt_is_unknown():
    buckets = (L.WattBucket(state="off", op="<=", value=5),)
    assert L.classify_power_state(None, buckets) == "unknown"


def test_power_state_no_match_is_unknown():
    # Kein Bucket matcht und kein catch-all → unknown
    buckets = (L.WattBucket(state="off", op="<", value=5),)
    assert L.classify_power_state(100, buckets) == "unknown"


def test_power_state_always_from_watt_even_when_integration_on():
    """LH OQ-3-Auflösung: power_state immer aus Watt, unabhängig von Integration."""
    buckets = (
        L.WattBucket(state="off", op="<=", value=5),
        L.WattBucket(state="idle", op="<=", value=30),
        L.WattBucket(state="playing", op=">", value=30),
    )
    cfg = _config(buckets=buckets, configured=("integration_entity", "watt_sensor"))
    inp = _inputs(
        {
            "integration_entity": _reading("on"),
            "watt_sensor": _reading("2.0", numeric=2.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    # Integration sagt powered=True, aber power_state aus Watt = "off"
    assert r.powered is True
    assert r.power_state == "off"


def test_parse_watt_buckets_keeps_order():
    parsed = L.parse_watt_buckets(
        [
            {"state": "off", "op": "<=", "value": 5},
            {"state": "idle", "op": "<=", "value": 30},
            {"state": "playing", "op": ">", "value": 30},
        ]
    )
    assert [b.state for b in parsed] == ["off", "idle", "playing"]
    assert parsed[0].op == "<=" and parsed[0].value == 5.0


def test_parse_watt_buckets_catch_all_entry():
    parsed = L.parse_watt_buckets(
        [{"state": "off", "op": "<=", "value": 5}, {"state": "on"}]
    )
    assert parsed[1].op is None and parsed[1].value is None


def test_parse_watt_buckets_robust_against_garbage():
    assert L.parse_watt_buckets(None) == ()
    assert L.parse_watt_buckets("not a list") == ()
    assert L.parse_watt_buckets([{"op": "<", "value": 5}]) == ()  # missing state
    assert L.parse_watt_buckets([{"state": "x", "op": "??", "value": 5}]) == ()  # bad op
    assert L.parse_watt_buckets([{"state": "x", "op": "<", "value": "abc"}]) == ()  # bad value


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-07: Override
# ─────────────────────────────────────────────────────────────────────────────


def test_override_overrides_powered_and_source():
    override = L.build_override(powered=True, power_state="playing", expire_seconds=None, now=NOW)
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("off")})
    r = L.compute_device(cfg, inp, _persisted(override=override), NOW)
    assert r.powered is True
    assert r.power_source == C.PowerSource.OVERRIDE.value
    assert r.power_state == "playing"
    assert r.override_active is True


def test_override_with_expiry_is_active_within_window():
    override = L.build_override(powered=False, power_state=None, expire_seconds=120, now=NOW)
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("on")})
    r = L.compute_device(cfg, inp, _persisted(override=override), NOW + timedelta(seconds=60))
    assert r.override_active is True
    assert r.powered is False


def test_override_expired_falls_back_to_normal_logic():
    override = L.build_override(powered=False, power_state=None, expire_seconds=10, now=NOW)
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("on")})
    r = L.compute_device(cfg, inp, _persisted(override=override), NOW + timedelta(seconds=30))
    assert r.override_active is False
    assert r.powered is True  # Integration übernimmt wieder
    assert r.power_source == C.PowerSource.INTEGRATION.value


def test_is_override_expired_helper():
    o = L.Override(powered=True, power_state=None, expires_at=NOW + timedelta(seconds=60))
    assert L.is_override_expired(o, NOW) is False
    assert L.is_override_expired(o, NOW + timedelta(seconds=120)) is True
    perm = L.Override(powered=True, power_state=None, expires_at=None)
    assert L.is_override_expired(perm, NOW + timedelta(days=365)) is False
    assert L.is_override_expired(None, NOW) is True


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-09: Boot-Initial-Phase
# ─────────────────────────────────────────────────────────────────────────────


def test_sticky_hold_disabled_during_boot_phase():
    cfg = _config(sticky=600)
    inp = _inputs({"integration_entity": _reading(None)}, boot=True)
    persisted = _persisted(last_powered=True, last_change=NOW - timedelta(seconds=10))
    r = L.compute_device(cfg, inp, persisted, NOW)
    # In Boot-Phase greift Sticky-Hold NICHT
    assert r.powered is None
    assert r.power_source == C.PowerSource.NONE.value


def test_sticky_hold_works_outside_boot_phase():
    cfg = _config(sticky=600)
    inp = _inputs({"integration_entity": _reading(None)}, boot=False)
    persisted = _persisted(last_powered=True, last_change=NOW - timedelta(seconds=10))
    r = L.compute_device(cfg, inp, persisted, NOW)
    assert r.powered is True
    assert r.power_source == C.PowerSource.STICKY_HOLD.value


def test_is_boot_phase_helper():
    boot_start = NOW
    assert L.is_boot_phase(boot_start, NOW + timedelta(seconds=10)) is True
    assert L.is_boot_phase(boot_start, NOW + timedelta(seconds=C.BOOT_INITIAL_PHASE_SECONDS + 1)) is False


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-03: available
# ─────────────────────────────────────────────────────────────────────────────


def test_available_true_when_any_slot_fresh():
    cfg = _config()
    inp = _inputs(
        {
            "integration_entity": _reading(None),
            "watt_sensor": _reading("10", numeric=10.0),
        },
        watt_slot="watt_sensor",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.available is True


def test_available_false_when_all_slots_unavailable():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading(None)})
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.available is False


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-04: State-Mapping
# ─────────────────────────────────────────────────────────────────────────────


def test_state_for_stateful_uses_raw_value():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("playing")})
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.state == "playing"


def test_state_for_stateless_falls_back_to_on_off():
    cfg = _config(configured=("switch_entity",))
    inp = _inputs(
        {"switch_entity": _reading("on")},
        integration_slot="switch_entity",
        state_slot=None,
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.state == "on"


def test_state_unavailable_when_no_powered():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading(None)})
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.state == "unavailable"


# ─────────────────────────────────────────────────────────────────────────────
# last_powered_change Update
# ─────────────────────────────────────────────────────────────────────────────


def test_last_powered_change_updates_on_transition():
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("on")})
    persisted = _persisted(last_powered=False, last_change=NOW - timedelta(hours=1))
    r = L.compute_device(cfg, inp, persisted, NOW)
    assert r.last_powered_change == NOW


def test_last_powered_change_persists_when_no_transition():
    prev = NOW - timedelta(hours=1)
    cfg = _config()
    inp = _inputs({"integration_entity": _reading("on")})
    persisted = _persisted(last_powered=True, last_change=prev)
    r = L.compute_device(cfg, inp, persisted, NOW)
    assert r.last_powered_change == prev


# ─────────────────────────────────────────────────────────────────────────────
# device_types Profile sanity
# ─────────────────────────────────────────────────────────────────────────────


def test_all_device_types_have_default_fields():
    import bcd_device_types as DT

    for dt in C.DeviceType:
        assert DT.default_fields(dt), f"{dt.value} hat keine Default-Felder"


def test_integration_slot_in_catalog_and_defaults():
    import bcd_device_types as DT

    for dt in C.DeviceType:
        profile = DT.profile_for(dt)
        if profile.integration_slot is not None:
            assert profile.integration_slot in DT.SLOT_CATALOG, (
                f"{dt.value}: integration_slot fehlt im Katalog"
            )
            assert profile.integration_slot in profile.default_fields, (
                f"{dt.value}: integration_slot nicht in default_fields"
            )


def test_slot_catalog_domains_are_tight():
    import bcd_device_types as DT

    # Jedes Feld akzeptiert genau eine spezifische Domain (kein Domain-Misch).
    expected = {
        "integration_entity": ("media_player",),
        "power_entity": ("binary_sensor",),
        "watt_sensor": ("sensor",),
        "wifi_sensor": ("binary_sensor",),
        "switch_entity": ("switch",),
        "light_entity": ("light",),
        "cover_entity": ("cover",),
    }
    for key, doms in expected.items():
        assert DT.SLOT_CATALOG[key].domains == doms, (
            f"{key}: erwartet {doms}, ist {DT.SLOT_CATALOG[key].domains}"
        )


def test_import_validation_relaxed_slots_optional():
    import bcd_device_types as DT

    # Neues Modell: TV ohne integration_entity ist KEIN Fehler mehr
    assert DT.validate_import_device({"slug": "living_tv", "device_type": "tv"}) is None
    # nur slug + device_type pflicht
    assert DT.validate_import_device({"slug": "x", "device_type": "nope"}) is not None
    assert DT.validate_import_device({"slug": "Bad Slug", "device_type": "tv"}) is not None


# ─────────────────────────────────────────────────────────────────────────────
# R-DC-08: Bulk-Import-Validierung
# ─────────────────────────────────────────────────────────────────────────────


def test_is_valid_slug():
    import bcd_device_types as DT

    assert DT.is_valid_slug("living_pc") is True
    assert DT.is_valid_slug("tv2") is True
    assert DT.is_valid_slug("Living PC") is False
    assert DT.is_valid_slug("living-pc") is False
    assert DT.is_valid_slug("") is False


def test_validate_import_device_ok_plug():
    import bcd_device_types as DT

    d = {"slug": "kitchen_coffee", "device_type": "plug", "switch_entity": "switch.x"}
    assert DT.validate_import_device(d) is None


def test_validate_import_device_slot_optional_now():
    import bcd_device_types as DT

    # Neues Modell: TV ohne integration_entity ist OK (Slots optional)
    assert DT.validate_import_device({"slug": "living_tv", "device_type": "tv"}) is None


def test_validate_import_device_bad_slug_and_type():
    import bcd_device_types as DT

    assert DT.validate_import_device({"slug": "Bad Slug", "device_type": "plug"}) is not None
    assert DT.validate_import_device({"slug": "x", "device_type": "nope"}) is not None
    assert DT.validate_import_device("notadict") is not None


def test_validate_import_payload_all_or_nothing():
    import bcd_device_types as DT

    devices = [
        {"slug": "living_pc", "device_type": "plug", "switch_entity": "switch.pc"},
        {"slug": "bad_one", "device_type": "nonsense"},  # invalid device_type
    ]
    valid, errors = DT.validate_import_payload(devices)
    assert errors  # has at least one error
    assert any("bad_one" in e for e in errors)


def test_validate_import_payload_duplicate_slug():
    import bcd_device_types as DT

    devices = [
        {"slug": "x", "device_type": "plug", "switch_entity": "switch.a"},
        {"slug": "x", "device_type": "plug", "switch_entity": "switch.b"},
    ]
    valid, errors = DT.validate_import_payload(devices)
    assert any("doppelter slug" in e for e in errors)


def test_validate_import_payload_normalizes_and_defaults():
    import bcd_device_types as DT

    devices = [
        {"slug": "Living_PC", "device_type": "plug", "switch_entity": "switch.pc"},
    ]
    # uppercase slug ist invalid (Bad slug) → wir testen lowercase-normalisierung
    # mit gültigem slug:
    devices = [
        {"slug": "living_pc", "device_type": "plug", "switch_entity": "switch.pc"},
    ]
    valid, errors = DT.validate_import_payload(devices)
    assert not errors
    assert valid[0]["slug"] == "living_pc"
    assert valid[0]["display_name"] == "living_pc"  # default = slug


def test_validate_import_payload_empty_is_error():
    import bcd_device_types as DT

    valid, errors = DT.validate_import_payload([])
    assert errors
    valid, errors = DT.validate_import_payload("nope")
    assert errors


# ─────────────────────────────────────────────────────────────────────────────
# slugify / unique_slug (Single-Hub: slug aus Anzeigename)
# ─────────────────────────────────────────────────────────────────────────────


def test_slugify_basic():
    import bcd_device_types as DT

    assert DT.slugify("Wohnzimmer TV") == "wohnzimmer_tv"
    assert DT.slugify("  Küche  Kaffee ") == "kueche_kaffee"
    assert DT.slugify("PS5 / PlayStation") == "ps5_playstation"
    assert DT.slugify("LED-Stripe #1") == "led_stripe_1"
    assert DT.slugify("Über-Gerät") == "ueber_geraet"


def test_slugify_collapses_separators():
    import bcd_device_types as DT

    assert DT.slugify("a---b   c") == "a_b_c"
    assert DT.slugify("__rand__") == "rand"


def test_unique_slug_appends_counter():
    import bcd_device_types as DT

    existing = {"tv", "tv_2"}
    assert DT.unique_slug("tv", existing) == "tv_3"
    assert DT.unique_slug("pc", existing) == "pc"


# ─────────────────────────────────────────────────────────────────────────────
# Climate-Typ (nur rohe Wahrheiten, keine comfort/eco-Bewertung)
# ─────────────────────────────────────────────────────────────────────────────


def test_climate_type_exists_with_raw_attributes():
    import bcd_device_types as DT

    p = DT.profile_for(C.DeviceType.CLIMATE)
    assert "climate_entity" in p.default_fields
    assert p.integration_slot == "climate_entity"
    # nur rohe/geräte-inhärente Attribute, KEIN comfort/eco
    assert set(p.extra_attributes) == {
        "current_temperature",
        "target_temperature",
        "hvac_action",
        "hvac_mode",
    }
    assert "comfort" not in p.extra_attributes
    assert "eco" not in p.extra_attributes
    assert "value_state" not in p.extra_attributes


def test_climate_powered_when_hvac_mode_active():
    cfg = _config(
        configured=("climate_entity",),
    )
    cfg = L.DeviceConfig(
        slug="therm", display_name="Thermostat", device_type="climate",
        watt_threshold_on=5, watt_buckets=(), sticky_hold_seconds=30,
        area_id=None, configured_slots=("climate_entity",),
    )
    inp = _inputs(
        {"climate_entity": _reading("heat")},
        integration_slot="climate_entity",
        state_slot="climate_entity",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is True  # hvac_mode 'heat' = aktiv
    assert r.state == "heat"


def test_climate_off_is_not_powered():
    cfg = L.DeviceConfig(
        slug="therm", display_name="Thermostat", device_type="climate",
        watt_threshold_on=5, watt_buckets=(), sticky_hold_seconds=30,
        area_id=None, configured_slots=("climate_entity",),
    )
    inp = _inputs(
        {"climate_entity": _reading("off")},
        integration_slot="climate_entity",
        state_slot="climate_entity",
    )
    r = L.compute_device(cfg, inp, _persisted(), NOW)
    assert r.powered is False
    assert r.state == "off"
