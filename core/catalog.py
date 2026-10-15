"""Backward-compatibility shim. Implementation moved to core.engineering.catalog."""
from core.engineering.catalog import *
from core.engineering.catalog import (
    CatalogError,
    load_catalog,
    load_overlay,
    load_seed,
    normalize_part,
    reset_overlay,
    save_overlay,
)
