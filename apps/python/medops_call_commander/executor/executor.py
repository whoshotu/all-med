import time
from datetime import datetime

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
        plan.dispatched_at = datetime.utcnow()
        plan.state = PlanState.DISPATCHED

        while True:
            result = self._provider.get_result(plan.plan_id, external_id)

            if result.outcome == CallOutcome.ANSWERED:
                plan.state = PlanState.COMPLETED
                return result

            if result.outcome == CallOutcome.FAILED:
                plan.state = PlanState.FAILED
                return result

            time.sleep(5.0)
