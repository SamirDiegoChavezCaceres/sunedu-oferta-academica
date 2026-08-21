"""Public SUNEDU/SIU data: a quota-aware API client and a polars star model."""

from .api_client import (
    PAGE_SIZE_MAX,
    Page,
    QuotaExceeded,
    SuneduClient,
    estimate_requests,
)
from .build_model import ValidationError, build_model, validate

__all__ = [
    "SuneduClient",
    "Page",
    "QuotaExceeded",
    "estimate_requests",
    "PAGE_SIZE_MAX",
    "build_model",
    "validate",
    "ValidationError",
]
