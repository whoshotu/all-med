from typing import Any, Dict, List

from calle import CalleClient

from apps.python.medops_call_commander.config import load_calle_config, CalleConfig
from apps.python.medops_call_commander.core.models import CallPlan, CallResult
from apps.python.medops_call_commander.providers.base import CallProvider


class CalleMcpProvider(CallProvider):
    def __init__(self) -> None:
        config: CalleConfig = load_calle_config()
        self._client = CalleClient(api_key=config.api_key)
        self._webhook_url = config.webhook_url

    def dispatch(self, plan: CallPlan) -> str:
        recipients: List[Dict[str, Any]] = [
            {
                "phones": [plan.recipient_phone],
                "region": plan.region,
                "locale": plan.locale,
            }
        ]

        call = self._client.calls.create_and_wait(
            task=plan.task,
            recipients=recipients,
            webhook_url=self._webhook_url,
            metadata={"call_plan_id": plan.id},
        )

        return call["id"]

    def get_result(self, external_id: str) -> CallResult:
        call = self._client.calls.get(external_id)
        return CallResult.from_calle_payload(call)

    def cancel(self, external_id: str) -> None:
        self._client.calls.cancel(external_id)
