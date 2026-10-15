"""Backward-compatibility shim. Implementation moved to core.common.schemas."""
from core.common.schemas import *
from core.common.schemas import (
    CheckResult,
    Evidence,
    EvidenceRef,
    Part,
    Requirements,
    Spec,
    now_iso,
    BuildRequest,
    ParseRequest,
    SettingsRequest,
    LiveRefreshRequest,
    DiscoverRequest,
    ImportUrlRequest,
    PriceCheckRequest,
    SwapRequest,
)
