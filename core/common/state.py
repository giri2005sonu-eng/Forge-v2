"""Application runtime state and configuration management."""
from __future__ import annotations

import os
from typing import Any, Optional

from .config import DATA_DIR, load_config, load_spec_defs


class AppState:
    """Thread-safe singleton holding in-memory configuration and active build session."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = load_config(DATA_DIR)
        self.spec_defs: dict[str, Any] = load_spec_defs(DATA_DIR)
        self.runtime_keys: dict[str, str] = {
            "gemini": os.getenv("GEMINI_API_KEY", ""),
            "tinyfish": os.getenv("TINYFISH_API_KEY", ""),
            "model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        }
        self.active: dict[str, Any] = {
            "requirements": None,
            "selection": None,
            "build": None,
            "ctx": None,
        }

    def update_keys(
        self,
        gemini_key: Optional[str] = None,
        tinyfish_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        if gemini_key is not None:
            self.runtime_keys["gemini"] = gemini_key.strip()
        if tinyfish_key is not None:
            self.runtime_keys["tinyfish"] = tinyfish_key.strip()
        if model is not None:
            self.runtime_keys["model"] = model.strip() or "gemini-flash-latest"
        return self.get_settings_status()

    def get_settings_status(self) -> dict[str, Any]:
        return {
            "gemini_configured": bool(self.runtime_keys["gemini"]),
            "tinyfish_configured": bool(self.runtime_keys["tinyfish"]),
            "model": self.runtime_keys["model"],
        }

    def reset_active(self) -> None:
        self.active = {
            "requirements": None,
            "selection": None,
            "build": None,
            "ctx": None,
        }


_global_state = AppState()


def get_state() -> AppState:
    """Returns the shared application state singleton."""
    return _global_state
