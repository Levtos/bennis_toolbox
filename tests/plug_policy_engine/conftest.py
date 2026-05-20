"""Load plug_policy_engine's HA-free files (const, engine) as a synthetic
package so the pure policy decisions can be unit-tested without HA."""

from __future__ import annotations

import importlib.util
import os
import sys
import types


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "plug_policy_engine"
)

pkg_name = "pp_pure_pkg"
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
engine = _load("engine", "engine.py")

sys.modules["pp_const"] = const
sys.modules["pp_engine"] = engine
