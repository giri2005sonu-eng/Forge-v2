"""Backward-compatibility shim. Implementation moved to core.intelligence.sourcing."""
from core.intelligence.sourcing import *
from core.intelligence.sourcing import (
    FALLBACK_SEARCH,
    NON_STORE_DOMAINS,
    check_prices,
    clear_cache,
    core_name,
    find_sources,
    pick_links,
    query_variants,
)
