import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)


class CalleClient:
    """
    Python client for the CALL-E Developer API.
    Interfaces with https://api.heycall-e.com.

    Set CALLE_MOCK_MODE=1 for offline testing — no HTTP requests are made and
    a deterministic mock response is returned immediately.  Never set this in
    production or staging environments.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.heycall-e.com").rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MedOpsCallCommander/1.0",
        }
        # In-memory registry for call status tracking during simulation
        self._mock_calls: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _is_mock_mode() -> bool:
        return os.environ.get("CALLE_MOCK_MODE", "").lower() in ("1", "true", "yes", "on")

    def calls_create(self, task: str, phone: Optional[str] = None, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates an outbound call or returns a simulated call in mock mode."""
        # ------------------------------------------------------------------
        # Mock mode: branch BEFORE any network I/O.
        # CALLE_MOCK_MODE=1 guarantees zero HTTP requests are attempted.
        # ------------------------------------------------------------------
        if self._is_mock_mode():
            call_id = f"call_e_mock_{uuid.uuid4().hex[:10]}"
            mock_data = {
                "id": call_id,
                "status": "completed",
                "task_completed": True,
                "task": task,
                # Raw phone is intentionally omitted — never echoed back.
                "structured_result": {
                    "reschedule_confirmed": True,
                    "promise_date": "2026-08-12",
                    "call_summary": "[MOCK] Patient confirmed appointment reschedule.",
                },
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self._mock_calls[call_id] = mock_data
            logger.info("CALL-E mock mode: returning simulated call %s (no HTTP request made).", call_id)
            return mock_data

        # ------------------------------------------------------------------
        # Live mode: make the real API call.
        # ------------------------------------------------------------------
        url = f"{self.base_url}/v1/calls"
        payload = {
            "task": task,
            "recipients": [{"phones": [phone or "+14155550100"], "region": "US"}] if phone else [],
            "metadata": {"plan_id": plan_id} if plan_id else {},
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=60)
            if resp.status_code in (200, 201):
                return resp.json()
            logger.error(
                "CALL-E API creation error HTTP %s (phone: <masked>).",
                resp.status_code,
            )
            return {
                "id": f"call_failed_{uuid.uuid4().hex[:8]}",
                "status": "failed",
                "task_completed": False,
                "error": f"API returned status {resp.status_code}",
                "structured_result": {},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("CALL-E API request exception (phone: <masked>): %s", exc)
            return {
                "id": f"call_failed_{uuid.uuid4().hex[:8]}",
                "status": "failed",
                "task_completed": False,
                "error": str(exc),
                "structured_result": {},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

    def calls_get(self, call_id: str) -> Dict[str, Any]:
        """Fetch call status and result."""
        if call_id in self._mock_calls:
            return self._mock_calls[call_id]

        url = f"{self.base_url}/v1/calls/{call_id}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("CALL-E get status error HTTP %s for call %s", resp.status_code, call_id)
            return {
                "id": call_id,
                "status": "failed",
                "task_completed": False,
                "error": f"HTTP {resp.status_code}",
                "structured_result": {},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("Error fetching CALL-E call %s: %s", call_id, exc)
            return {
                "id": call_id,
                "status": "failed",
                "task_completed": False,
                "error": str(exc),
                "structured_result": {},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

    def calls_cancel(self, call_id: str) -> None:
        """Cancel an in-flight call (best effort)."""
        if call_id in self._mock_calls:
            self._mock_calls[call_id]["status"] = "canceled"
            return
        url = f"{self.base_url}/v1/calls/{call_id}/cancel"
        try:
            requests.post(url, headers=self.headers, timeout=5)
        except Exception as exc:
            logger.warning("Best-effort error canceling CALL-E call %s: %s", call_id, exc)
