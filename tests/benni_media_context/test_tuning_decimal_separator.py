"""Tuning step renders dot-separated decimals regardless of HA locale.

The classic `NumberSelector` shows values in the user's locale —
German users see `0,15` / `-0,1`. The user prefers consistent
dot-separated decimals (matching the spec). We switched the tuning
schema to a plain text input with a dot/comma-tolerant float
coercion. This file pins:
- The coercion accepts both '.' and ',' decimals.
- Defaults are rendered with a dot.
- Submitted strings ("0.4", "0,4", "-0.1") and submitted numbers all
  round-trip to the expected floats and respect the range bounds.
- The selector behind every tuning field is a TextSelector, not a
  NumberSelector — so the browser can't apply locale formatting.
"""
from __future__ import annotations

import asyncio
import types
from functools import wraps

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402
import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402

flow_module = smoke.flow_module
_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# 1) The pure coercion helper.
# ---------------------------------------------------------------------------


def test_to_decimal_accepts_dot_string():
    assert flow_module._to_decimal("0.15") == 0.15
    assert flow_module._to_decimal("-0.1") == -0.1
    assert flow_module._to_decimal("4") == 4.0


def test_to_decimal_accepts_comma_string():
    assert flow_module._to_decimal("0,15") == 0.15
    assert flow_module._to_decimal("-0,1") == -0.1
    assert flow_module._to_decimal("0,4") == 0.4


def test_to_decimal_passes_through_numbers():
    assert flow_module._to_decimal(0.35) == 0.35
    assert flow_module._to_decimal(4) == 4.0
    assert flow_module._to_decimal(-0.05) == -0.05


def test_to_decimal_handles_empty_inputs():
    assert flow_module._to_decimal(None) == 0.0
    assert flow_module._to_decimal("") == 0.0


def test_to_decimal_strips_whitespace():
    assert flow_module._to_decimal("  0,15  ") == 0.15
    assert flow_module._to_decimal("\t-0.1\n") == -0.1


def test_to_decimal_rejects_garbage():
    with pytest.raises((ValueError, TypeError)):
        flow_module._to_decimal("abc")


# ---------------------------------------------------------------------------
# 2) Default rendering uses dot, even when the stored value would
#    otherwise be locale-formatted by HA.
# ---------------------------------------------------------------------------


def test_fmt_decimal_uses_dot_separator():
    assert flow_module._fmt_decimal(0.15, 0.0) == "0.15"
    assert flow_module._fmt_decimal(-0.1, 0.0) == "-0.1"
    assert flow_module._fmt_decimal(4, 0.0) == "4.0"


def test_fmt_decimal_falls_back_to_default_on_garbage():
    assert flow_module._fmt_decimal(None, 0.4) == "0.4"
    assert flow_module._fmt_decimal("garbage", 0.35) == "0.35"


# ---------------------------------------------------------------------------
# 3) Tuning schema uses TextSelector, never NumberSelector.
# ---------------------------------------------------------------------------


_TUNING_KEYS = (
    "debounce_seconds",
    "quiet_ducking_level",
    "base_volume_homepods",
    "base_volume_denon",
    "track_boost_offset",
    "window_volume_offset",
)


def _selector_in_schema(schema, key):
    """Return the first validator in a vol.All chain that has a `cfg`
    attribute (i.e. one of the selector stubs). The chain layout is
    `vol.All(TextSelector, _to_decimal, vol.Range)`, so the selector
    is the first sub-validator."""
    for marker, validator in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == key:
            # validator is a vol.All; pull the first wrapped item.
            validators = getattr(validator, "validators", ())
            for v in validators:
                if hasattr(v, "cfg"):
                    return v
            return validator
    raise AssertionError(f"key {key!r} not in schema")


@_run
async def test_every_tuning_field_uses_textselector_not_numberselector():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()
    schema = helper.flow.last_form["data_schema"]
    import homeassistant.helpers.selector as sel
    for key in _TUNING_KEYS:
        widget = _selector_in_schema(schema, key)
        assert isinstance(widget, sel.TextSelector), (
            f"tuning field {key!r} must use TextSelector to bypass locale "
            f"formatting; got {type(widget).__name__}"
        )


@_run
async def test_tuning_schema_defaults_render_with_dot():
    """Defaults pulled from stored options must surface as
    dot-separated strings — otherwise the rendered input would carry
    the German comma the user complained about."""
    entry = _entry(options={
        "debounce_seconds": 4,
        "quiet_ducking_level": 0.15,
        "window_volume_offset": -0.1,
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()
    schema = helper.flow.last_form["data_schema"]
    found = {}
    for marker in schema.schema:
        name = str(getattr(marker, "schema", marker))
        if name in _TUNING_KEYS:
            try:
                found[name] = marker.default()
            except Exception:
                found[name] = None
    assert found["debounce_seconds"] == "4.0"
    assert found["quiet_ducking_level"] == "0.15"
    assert found["window_volume_offset"] == "-0.1"


# ---------------------------------------------------------------------------
# 4) Round-trip: submitting a comma-decimal string is accepted and
#    stored as a float.
# ---------------------------------------------------------------------------


@_run
async def test_tuning_step_accepts_comma_decimal_input():
    """German-locale user types '-0,1' into the window-offset field.
    The voluptuous chain must coerce to -0.1, validate the range, and
    persist a Python float."""
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()  # render
    schema = helper.flow.last_form["data_schema"]
    # Manually run the validator chain for the field — that's what HA
    # does on submit.
    for marker, validator in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == "window_volume_offset":
            out = validator("-0,1")
            assert out == pytest.approx(-0.1)
            break
    else:
        raise AssertionError("window_volume_offset missing")


@_run
async def test_tuning_step_still_accepts_dot_decimal_input():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()
    schema = helper.flow.last_form["data_schema"]
    for marker, validator in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == "quiet_ducking_level":
            assert validator("0.15") == pytest.approx(0.15)
            break
    else:
        raise AssertionError("quiet_ducking_level missing")


@_run
async def test_tuning_step_enforces_range_after_coercion():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()
    schema = helper.flow.last_form["data_schema"]
    import voluptuous as vol
    for marker, validator in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == "quiet_ducking_level":
            with pytest.raises(vol.Invalid):
                validator("2.5")  # out of [0, 1] range
            break
    else:
        raise AssertionError("quiet_ducking_level missing")
