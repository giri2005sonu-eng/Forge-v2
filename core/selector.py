"""Backward-compatibility shim. Implementation moved to core.engineering.selector."""
from core.engineering.selector import *
from core.engineering.selector import (
    Build,
    Candidate,
    Selection,
    _make_build,
    qty_for,
    select_build,
    shipping_breakdown,
)
