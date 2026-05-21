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
    "cover_policy",
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
    init_src = init.read_text(encoding="utf-8")
    spec_file = MODULES_DIR / module_id / "_spec.py"
    # SPEC darf entweder im __init__.py oder in _spec.py deklariert sein.
    spec_src = spec_file.read_text(encoding="utf-8") if spec_file.exists() else ""
    has_spec = "SPEC = ModuleSpec(" in init_src or "SPEC: Final[ModuleSpec] = ModuleSpec(" in spec_src or "SPEC = ModuleSpec(" in spec_src
    assert has_spec, f"{module_id} does not declare SPEC"
    combined = init_src + spec_src
    assert f'module_id="{module_id}"' in combined, f"{module_id} SPEC has wrong id"


@pytest.mark.parametrize("module_id", sorted(EXPECTED_MODULE_IDS))
def test_module_spec_loadable_without_homeassistant(module_id: str) -> None:
    """SPEC of every module must be loadable without homeassistant.

    READY modules ship `_spec.py` (HA-free), PENDING/STUB modules can keep
    their SPEC in `__init__.py` since those don't import HA. This test
    loads the SPEC the same way the registry does and verifies the id.
    """
    module_dir = MODULES_DIR / module_id
    spec_file = module_dir / "_spec.py"
    init_file = module_dir / "__init__.py"
    target = spec_file if spec_file.exists() else init_file

    pkg_name = f"bt_modules_test_{module_id}"
    pkg = ModuleType(pkg_name)
    pkg.__path__ = [str(MODULES_DIR)]
    sys.modules[pkg_name] = pkg

    base_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.base", MODULES_DIR / "base.py"
    )
    mod_base = importlib.util.module_from_spec(base_spec)
    sys.modules[f"{pkg_name}.base"] = mod_base
    base_spec.loader.exec_module(mod_base)

    # Sub-package shell so `from ..base import …` resolves.
    sub_pkg_name = f"{pkg_name}.{module_id}"
    sub_pkg = ModuleType(sub_pkg_name)
    sub_pkg.__path__ = [str(module_dir)]
    sys.modules[sub_pkg_name] = sub_pkg

    full_name = f"{sub_pkg_name}._spec" if target is spec_file else sub_pkg_name
    spec = importlib.util.spec_from_file_location(full_name, target)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
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


LEGACY_WS_PATTERNS: tuple[str, ...] = (
    # Pro Modul-ID das Bare-Prefix verbieten. Jeder dieser Strings darf im
    # produktiven Frontend nur noch als `bennis_toolbox/<module>/...`
    # auftauchen — die Bare-Form ist die alte HA-Domain-Schreibweise.
    '"wake_planner/',
    "'wake_planner/",
    '"title_classifier/',
    "'title_classifier/",
    '"benni_context/',
    "'benni_context/",
    '"benni_media_context/',
    "'benni_media_context/",
    '"notification_router/',
    "'notification_router/",
    '"plug_policy_engine/',
    "'plug_policy_engine/",
    '"maw/',
    "'maw/",
    '"stash_ha/',
    "'stash_ha/",
)


def test_no_bare_module_id_websocket_types_in_frontend() -> None:
    """Frontend-Dateien dürfen WS-Type-Strings nur unter dem Toolbox-Präfix
    senden: `bennis_toolbox/<module_id>/<command>`. Eine nackte
    `<module_id>/<command>`-Form (z.B. `"wake_planner/get_state"`) gehört
    zum alten HA-Domain-Schema und ist verboten.

    Wir scannen `.js`/`.ts`-Dateien unter jedem `modules/<id>/frontend/`.
    Treffer in `bennis_toolbox/<module>/...` werden automatisch
    ignoriert, weil das Präfix vor dem Modulnamen sitzt.
    """
    offenders: list[str] = []
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        frontend_dir = module_dir / "frontend"
        if not frontend_dir.exists():
            continue
        for js in frontend_dir.rglob("*"):
            if not js.is_file() or js.suffix not in {".js", ".ts", ".mjs"}:
                continue
            try:
                src = js.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for needle in LEGACY_WS_PATTERNS:
                idx = 0
                while True:
                    idx = src.find(needle, idx)
                    if idx == -1:
                        break
                    # Erlaubt: `"bennis_toolbox/wake_planner/...` → check the
                    # 17 chars before the match.
                    head = src[max(0, idx - 17):idx]
                    if not head.endswith("bennis_toolbox/"):
                        line = src.count("\n", 0, idx) + 1
                        offenders.append(
                            f"{js.relative_to(REPO)}:{line}: bare WS prefix {needle[1:]}"
                        )
                    idx += len(needle)
    assert not offenders, "Legacy bare WS commands in frontend:\n" + "\n".join(offenders)


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
