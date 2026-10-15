"""Backward-compatibility shim. Implementation moved to core.intelligence.llm."""
from core.intelligence.llm import *
from core.intelligence.llm import (
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    GeminiClient,
    LLMError,
    parse_json_loose,
)
