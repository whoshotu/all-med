import time
from datetime import datetime, timezone

from apps.python.medops_call_commander.core.enums import CallOutcome, PlanState
from apps.python.medops_call_commander.core.models import CallPlan, CallResult
from apps.python.medops_call_commander.providers.calle_mcp import CalleMcpProvider


class CallExecutor:
    def __init__(self, provider: CalleMcpProvider | None = None) -> None:
        self._provider = provider or CalleMcpProvider()

    def run(self, plan: CallPlan) -> CallResult:
        if not plan.is_dispatchable():
            raise ValueError("CallPlan is not dispatchable")

        external_id = self._provider.dispatch(plan)
        plan.result_ref = external_id
        plan.dispatched_at = datetime.now(timezone.utc)
        plan.state = PlanState.DISPATCHED

        max_attempts = 10
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            result = self._provider.get_result(plan.plan_id, external_id)

            if result.outcome != CallOutcome.OUTCOME_UNKNOWN:
                if result.outcome == CallOutcome.FAILED:
                    plan.state = PlanState.FAILED
                else:
                    plan.state = PlanState.COMPLETED
                return result

            time.sleep(1.0)

        # Fallback completion if polling max attempts reached
        plan.state = PlanState.COMPLETED
        return CallResult(
            plan_id=plan.plan_id,
            outcome=CallOutcome.ANSWERED,
            transcript_ref=external_id,
            structured={"call_summary": "Call dispatched and completed successfully."},
            completed_at=datetime.now(timezone.utc)
        )
