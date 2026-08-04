import time
from typing import Optional

from apps.python.medops_call_commander.core.models import CallPlan, CallResult
from apps.python.medops_call_commander.providers.calle_mcp import CalleMcpProvider


class CallExecutor:
    def __init__(self, provider: Optional[CalleMcpProvider] = None) -> None:
        self._provider = provider or CalleMcpProvider()

    def run(self, plan: CallPlan) -> CallResult:
        external_id = self._provider.dispatch(plan)

        while True:
            result = self._provider.get_result(external_id)
            if result.status in ("completed", "failed", "canceled"):
                return result
            time.sleep(5.0)
