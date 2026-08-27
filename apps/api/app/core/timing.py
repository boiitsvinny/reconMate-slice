"""Small structured timing helpers for production diagnostics."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any


# Uvicorn configures this logger at INFO in both local and Render deployments.
logger = logging.getLogger("uvicorn.error")


def elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def log_timing(event: str, **fields: Any) -> None:
    """Emit fixed, non-sensitive operational timing fields as one JSON line."""
    logger.info(json.dumps({"event": event, **fields}, separators=(",", ":"), default=str))
