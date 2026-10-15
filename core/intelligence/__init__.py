"""AI, LLM prompting, web crawling, and live sourcing services."""
from .llm import DEFAULT_MODEL, FALLBACK_MODELS, GeminiClient, LLMError, parse_json_loose
from .parser import LLMJson, heuristic_parse, parse_requirements
from .tinyfish import TinyFishClient, TinyFishError
from .live import (
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
from .sourcing import (
    FALLBACK_SEARCH,
    NON_STORE_DOMAINS,
    check_prices,
    clear_cache,
    core_name,
    find_sources,
    pick_links,
    query_variants,
)

__all__ = [
    "DEFAULT_MODEL",
    "FALLBACK_MODELS",
    "GeminiClient",
    "LLMError",
    "parse_json_loose",
    "LLMJson",
    "heuristic_parse",
    "parse_requirements",
    "TinyFishClient",
    "TinyFishError",
    "MAX_PAGE_CHARS",
    "SKIP_DOMAINS",
    "discover_parts",
    "domain_of",
    "extract_from_page",
    "import_part_from_url",
    "pick_urls",
    "quote_in_text",
    "refresh_part",
    "FALLBACK_SEARCH",
    "NON_STORE_DOMAINS",
    "check_prices",
    "clear_cache",
    "core_name",
    "find_sources",
    "pick_links",
    "query_variants",
]
