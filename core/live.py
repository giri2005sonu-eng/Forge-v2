"""Backward-compatibility shim. Implementation moved to core.intelligence.live."""
from core.intelligence.live import *
from core.intelligence.live import (
    Extraction,
    MAX_PAGE_CHARS,
    SKIP_DOMAINS,
    discover_parts,
    domain_of,
    extract_from_page,
    import_part_from_url,
    pick_urls,
    quote_in_text,
    refresh_part,
    verify_extraction,
)
