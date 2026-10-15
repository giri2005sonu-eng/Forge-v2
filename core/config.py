"""Backward-compatibility shim. Implementation moved to core.common.config."""
from core.common.config import *
from core.common.config import (
    BASE_DIR,
    DATA_DIR,
    load_config,
    load_spec_defs,
    load_yaml,
)
