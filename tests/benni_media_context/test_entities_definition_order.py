"""Regression for v0.3.8.1: NameError on entry setup.

0.3.8 placed `_VolumeApplyAllowed(_BaseBinary)` inside the sensor
block of entities.py — *before* `_BaseBinary` was defined a few lines
below. Python only catches that when the module is actually imported
at runtime, which happens inside `bennis_toolbox.__init__.async_setup_entry`
under HA. None of the existing tests (which AST-scan the file
statically or load only flow/services_impl) caught it.

These tests pin two properties of entities.py:

1. Every class's base-class reference (`_BaseSensor` / `_BaseBinary`)
   must be defined *earlier* in the source. AST-only, no HA needed.
2. The module body parses *and* the four orchestrator entity classes
   appear in the right base-class buckets.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path


MODULE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "custom_components" / "bennis_toolbox" / "modules" / "benni_media_context"


def _class_definitions(source: str) -> list[ast.ClassDef]:
    return [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef)]


def _base_names(node: ast.ClassDef) -> list[str]:
    out = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Subscript):
            # CoordinatorEntity[BenniMediaCoordinator]
            if isinstance(base.value, ast.Name):
                out.append(base.value.id)
    return out


def test_every_class_base_is_defined_before_it():
    """If a class subclasses a `_Foo` declared later in the same
    module, Python raises NameError at import time. Catch that
    statically by walking class definitions in source order.
    """
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    classes = _class_definitions(src)
    defined: set[str] = set()
    for node in classes:
        for base in _base_names(node):
            if base.startswith("_") and base not in defined:
                raise AssertionError(
                    f"class {node.name!r} (line {node.lineno}) subclasses "
                    f"{base!r} but {base!r} is not defined earlier in the "
                    f"module — this raises NameError at import time."
                )
        defined.add(node.name)


def test_volume_apply_allowed_inherits_from_base_binary():
    """Specific regression: _VolumeApplyAllowed must extend
    _BaseBinary (not _BaseSensor), and _BaseBinary must come first."""
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    classes = _class_definitions(src)
    by_name = {c.name: c for c in classes}
    assert "_VolumeApplyAllowed" in by_name
    assert _base_names(by_name["_VolumeApplyAllowed"]) == ["_BaseBinary"]
    assert by_name["_BaseBinary"].lineno < by_name["_VolumeApplyAllowed"].lineno


def test_volume_policy_sensor_inherits_from_base_sensor():
    src = (MODULE_DIR / "entities.py").read_text(encoding="utf-8")
    classes = _class_definitions(src)
    by_name = {c.name: c for c in classes}
    assert "_VolumePolicySensor" in by_name
    assert _base_names(by_name["_VolumePolicySensor"]) == ["_BaseSensor"]
    assert by_name["_BaseSensor"].lineno < by_name["_VolumePolicySensor"].lineno
