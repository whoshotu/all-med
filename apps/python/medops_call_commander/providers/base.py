from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core.models import CallPlan


@dataclass(frozen=True)
class ProviderSubmission:
    """Minimal provider acceptance record; contains no transcript or phone."""

    provider_call_id: str
    status: str


class CallProvider(Protocol):
    """Narrow provider boundary. Implementations may not mutate CallPlan state."""

    def create_call(self, plan: CallPlan, result_schema: dict) -> ProviderSubmission:
        ...

    def get_call(self, provider_call_id: str) -> dict:
        """Return a provider response for reconciliation; caller must minimize it."""
        ...
