"""Shared pytest fixtures.

These tests exercise the pure data-extraction helpers against a real device
snapshot, so they add the ``custom_components`` directory to the import path and
avoid importing Home Assistant.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_PKG_DIR = _ROOT / "custom_components" / "felicity_battery"

# Register `felicity_battery` as a bare namespace package pointing at the real
# source dir, WITHOUT executing its __init__.py (which imports Home Assistant).
# This lets the pure submodules (const, helpers) and their relative imports load
# for testing without pulling in HA.
if "felicity_battery" not in sys.modules:
    _pkg = types.ModuleType("felicity_battery")
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["felicity_battery"] = _pkg

_FIXTURE = Path(__file__).parent / "fixtures" / "snapshot_fla48300.json"


@pytest.fixture
def snapshot() -> dict:
    """A real FLA48300 snapshot (discharging at ~483 W, SOC 89%)."""
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))
