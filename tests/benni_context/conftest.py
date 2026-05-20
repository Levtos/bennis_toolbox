"""Load benni_context's HA-free files (const, models, logic) as a synthetic
package so the pure rules can be unit-tested without homeassistant.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime, timezone


def _stub_homeassistant_dt() -> None:
    """`logic.py` imports ``from datetime`` only, but models/const are clean.
    Some helpers in logic.py reference dt_util via ``from homeassistant.util
    import dt as dt_util`` only inside the coordinator — not in logic.py.
    We still stub the bare minimum in case future ports add it."""
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []  # type: ignore[attr-defined]
    ha_util = sys.modules.setdefault("homeassistant.util", types.ModuleType("homeassistant.util"))
    ha_util.__path__ = []  # type: ignore[attr-defined]
    ha_dt = sys.modules.setdefault("homeassistant.util.dt", types.ModuleType("homeassistant.util.dt"))

    def utcnow():
        return datetime.now(timezone.utc)

    ha_dt.utcnow = utcnow
    ha_dt.UTC = timezone.utc


_stub_homeassistant_dt()


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "benni_context"
)

pkg_name = "bc_pure_pkg"
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
models = _load("models", "models.py")
logic = _load("logic", "logic.py")

sys.modules["bc_const"] = const
sys.modules["bc_models"] = models
sys.modules["bc_logic"] = logic
