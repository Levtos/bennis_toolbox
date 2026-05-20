"""Load logic.py and const.py as a synthetic package without triggering the
real __init__.py (which imports homeassistant)."""
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "benni_media_context"
)

# Create a synthetic package so relative imports inside logic.py resolve.
pkg_name = "bmc_logic_pkg"
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
logic = _load("logic", "logic.py")

# Expose as top-level names for tests
sys.modules["bmc_const"] = const
sys.modules["bmc_logic"] = logic
