"""Smoke tests for the umbrella architecture.

bennis_toolbox is one integration, one HA domain. Inside it, modules live
under custom_components/bennis_toolbox/modules/<module_id>/ and each
exposes a ModuleSpec.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
CC = REPO / "custom_components"
INTEGRATION_DIR = CC / "bennis_toolbox"
MODULES_DIR = INTEGRATION_DIR / "modules"

EXPECTED_MODULE_IDS: set[str] = {
    "benni_context",
    "benni_media_context",
    "notification_router",
    "plug_policy_engine",
    "title_classifier",
    "wake_planner",
    "maw",
    "stash_ha",
}

LEGACY_TOP_LEVEL_DOMAINS: set[str] = {
    "etm",
    "stash_player",
    "media_art_wrapper",
    "benni_notification_router",
    "benni_plug_policy",
    "wake_planner",
    "title_classifier",
    "benni_context",
    "benni_media_context",
    "notification_router",
    "plug_policy_engine",
    "stash_ha",
    "maw",
}


# ----------------------------------------------------------------------- shape


def test_only_one_top_level_integration() -> None:
    integrations = sorted(p.name for p in CC.iterdir() if p.is_dir())
    assert integrations == ["bennis_toolbox"], (
        f"only bennis_toolbox may live under custom_components/, got: {integrations}"
    )


def test_no_legacy_top_level_integration_folders() -> None:
    actual = {p.name for p in CC.iterdir() if p.is_dir()}
    leftover = LEGACY_TOP_LEVEL_DOMAINS & actual
    # The umbrella itself is fine.
    leftover.discard("bennis_toolbox")
    assert not leftover, f"legacy top-level integration folders: {leftover}"


def test_manifest_domain_matches() -> None:
    manifest = json.loads((INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "bennis_toolbox"
    assert manifest.get("config_flow") is True


# --------------------------------------------------------------------- modules


def test_all_expected_modules_present() -> None:
    actual = {
        p.name for p in MODULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_") and p.name != "__pycache__"
    }
    missing = EXPECTED_MODULE_IDS - actual
    extra = actual - EXPECTED_MODULE_IDS
    assert not missing, f"missing modules: {missing}"
    assert not extra, f"unexpected modules: {extra}"


@pytest.mark.parametrize("module_id", sorted(EXPECTED_MODULE_IDS))
def test_module_has_init_and_spec(module_id: str) -> None:
    init = MODULES_DIR / module_id / "__init__.py"
    assert init.exists(), f"{module_id}/__init__.py missing"
    src = init.read_text(encoding="utf-8")
    assert "SPEC = ModuleSpec(" in src, f"{module_id} does not declare SPEC"
    assert f'module_id="{module_id}"' in src, f"{module_id} SPEC has wrong id"


@pytest.mark.parametrize("module_id", sorted(EXPECTED_MODULE_IDS))
def test_module_is_importable_without_homeassistant(module_id: str) -> None:
    """SPEC of every module should be loadable in plain Python.

    Modules may import homeassistant for their runtime logic, but the
    top-level `__init__.py` must keep the SPEC declaration importable so
    the registry can enumerate modules.
    """
    # Build a minimal package context (modules → base) so `from ..base import …`
    # works.
    base = MODULES_DIR / module_id / "__init__.py"
    base_module = MODULES_DIR / "base.py"

    pkg_name = "bt_modules_test"
    pkg = ModuleType(pkg_name)
    pkg.__path__ = [str(MODULES_DIR)]
    sys.modules[pkg_name] = pkg

    spec_base = importlib.util.spec_from_file_location(
        f"{pkg_name}.base", base_module
    )
    mod_base = importlib.util.module_from_spec(spec_base)
    sys.modules[f"{pkg_name}.base"] = mod_base
    spec_base.loader.exec_module(mod_base)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.{module_id}", base, submodule_search_locations=[str(base.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.{module_id}"] = mod
    spec.loader.exec_module(mod)

    assert hasattr(mod, "SPEC")
    assert mod.SPEC.module_id == module_id


# ------------------------------------------------------------------ legacy ban


LEGACY_TOKENS = ("ETM", "Etm", "stash_player", "media_art_wrapper",
                 "benni_notification_router", "benni_plug_policy")


def test_no_legacy_tokens_in_production_code() -> None:
    """Production code under custom_components/ must not contain legacy
    integration-domain tokens. Lowercase 'etm' is intentionally not
    blocked here because it is a substring of harmless words.
    """
    offenders: list[str] = []
    for file in INTEGRATION_DIR.rglob("*"):
        if not file.is_file() or "__pycache__" in file.parts:
            continue
        if file.suffix not in {".py", ".json", ".yaml", ".js", ".md"}:
            continue
        try:
            src = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in LEGACY_TOKENS:
            if token in src:
                offenders.append(f"{file.relative_to(REPO)}: contains {token}")
    assert not offenders, "legacy tokens in production code:\n" + "\n".join(offenders)


def test_no_toolbox_domain_prefix() -> None:
    """No module folder name may use a toolbox_ prefix — organisational
    membership lives in the monorepo, not in the module id.
    """
    bad = [m for m in EXPECTED_MODULE_IDS if m.startswith("toolbox_")]
    assert not bad, f"toolbox_-prefixed modules: {bad}"


# --------------------------------------------------------- structural sanity


def test_platform_dispatchers_exist() -> None:
    expected = [
        "sensor.py", "binary_sensor.py", "number.py", "select.py",
        "switch.py", "button.py", "calendar.py", "image.py", "media_player.py",
    ]
    for name in expected:
        path = INTEGRATION_DIR / name
        assert path.exists(), f"missing platform dispatcher {name}"
        src = path.read_text(encoding="utf-8")
        assert "async_setup_platform_for" in src, f"{name} does not delegate"


def test_no_cross_module_imports() -> None:
    """Modules must not import each other directly."""
    offenders: list[str] = []
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        own = module_dir.name
        for py in module_dir.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                elif isinstance(node, ast.Import):
                    mods = [n.name for n in node.names]
                for m in mods:
                    parts = m.split(".")
                    # Detect import patterns like `..benni_context` or
                    # `custom_components.bennis_toolbox.modules.benni_context`.
                    for other in EXPECTED_MODULE_IDS:
                        if other == own:
                            continue
                        if other in parts:
                            offenders.append(f"{py.relative_to(REPO)} -> {m}")
    assert not offenders, "cross-module imports:\n" + "\n".join(offenders)
