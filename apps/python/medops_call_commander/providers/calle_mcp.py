from datetime import datetime
from typing import Any, Dict

from calle import CalleClient

from apps.python.medops_call_commander.config import load_calle_config
from apps.python.medops_call_commander.core.enums import CallOutcome
from apps.python.medops_call_commander.core.models import CallPlan, CallResult
from apps.python.medops_call_commander.providers.base import CallProvider


class CalleMcpProvider(CallProvider):
    def __init__(self) -> None:
        config = load_calle_config()
        self._client = CalleClient(api_key=config.api_key)

    def dispatch(self, plan: CallPlan) -> str:
        call = self._client.calls.create_and_wait(
            task=plan.script,
        )
        return str(call["id"])

    def get_result(self, plan_id: str, external_id: str) -> CallResult:
        payload: Dict[str, Any] = self._client.calls.get(external_id)
        status = payload.get("status")

        if status == "completed":
            outcome = CallOutcome.COMPLETED
        elif status == "failed":
            outcome = CallOutcome.FAILED
        elif status == "canceled":
            outcome = CallOutcome.CANCELED
        else:
            outcome = CallOutcome.UNKNOWN

        structured = payload.get("structured_result") or {}
        completed_at_str = payload.get("completed_at")
        if completed_at_str:
            completed_at = datetime.fromisoformat(completed_at_str)
        else:
            completed_at = datetime.utcnow()

        return CallResult(
            plan_id=plan_id,
            outcome=outcome,
            transcript_ref=external_id,
            structured=structured,
            completed_at=completed_at,
        )

    def cancel(self, external_id: str) -> None:
        self._client.calls.cancel(external_id)
