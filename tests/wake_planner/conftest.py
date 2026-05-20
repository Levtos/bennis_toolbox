"""Load wake_planner's HA-free files (const, rule_engine, util, holiday_source-substring helpers)
as a synthetic package, without importing homeassistant.

We can exercise the rule engine and holiday parser this way; the coordinator,
calendar source and entities require HA and are tested in HA integration tests.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "wake_planner"
)

pkg_name = "wp_pure_pkg"
pkg = types.ModuleType(pkg_name)
pkg.__path__ = [PKG_DIR]
sys.modules[pkg_name] = pkg


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.{modname}", os.path.join(PKG_DIR, filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const", "const.py")
rule_engine = _load("rule_engine", "rule_engine.py")

sys.modules["wp_const"] = const
sys.modules["wp_rule_engine"] = rule_engine
