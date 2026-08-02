import logging
import os
from datetime import datetime

import requests

from ..core.exceptions import EHRAdapterError
from ..core.models import EHREvent
from .base import EHRAdapter

logger = logging.getLogger(__name__)

# Event type mappings from OpenDental webhook action codes
OD_EVENT_MAP: dict[str, str] = {
    "AppointmentMissed":   "missed_appointment",
    "InvoiceOverdue30":    "invoice_30_days",
    "InvoiceOverdue60":    "invoice_60_days",
    "InvoiceOverdue90":    "invoice_90_days",
    "LoanInquiryCreated":  "loan_inquiry_submitted",
}


class OpenDentalAdapter(EHRAdapter):
    """
    Adapter for OpenDental REST API.
    Normalizes OpenDental webhook payloads to EHREvent.
    Writes structured call outcomes back via OpenDental patient notes API.
    """

    def __init__(self) -> None:
        self._base_url = os.environ["OPENDENTAL_API_URL"]   # e.g. https://your-od-instance/api/v1
        self._api_key  = os.environ["OPENDENTAL_API_KEY"]   # server-side only, never logged
        self._headers  = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type":  "application/json",
        }

    def normalize_event(self, raw: dict) -> EHREvent:
        try:
            action       = raw["action"]
            event_type   = OD_EVENT_MAP.get(action)
            if not event_type:
                raise EHRAdapterError(f"Unknown OpenDental action: {action}")

            patient_id   = str(raw["patNum"])
            phone        = self._fetch_patient_phone(patient_id)  # E.164 from OD patient record
            priority     = "urgent" if "90" in action else "routine"

            # Build minimum necessary context — no names, no balances in plain text
            context = {
                "reference_id": str(raw.get("referenceId", raw.get("appointmentId", patient_id))),
                "due_days":     raw.get("overdueDays"),
                "appointment_date": raw.get("appointmentDate"),
            }

            return EHREvent(
                event_type=event_type,
                patient_id=patient_id,
                patient_phone=phone,
                context=context,
                priority=priority,
                source_system="opendental",
            )
        except KeyError as exc:
            raise EHRAdapterError(f"Missing required field in OpenDental payload: {exc}") from exc
        finally:
            # Raw payload must not be retained
            raw.clear()

    def write_result(self, patient_id: str, result: dict) -> bool:
        """
        Appends a structured, non-PHI call outcome note to the patient record.
        result keys allowed: outcome, promise_date, reschedule_confirmed, call_type
        """
        allowed_keys = {"outcome", "promise_date", "reschedule_confirmed", "call_type"}
        safe_result  = {k: v for k, v in result.items() if k in allowed_keys}

        try:
            resp = requests.post(
                f"{self._base_url}/patients/{patient_id}/notes",
                json={"note": safe_result, "source": "medops_call_commander"},
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.HTTPError as exc:
            raise EHRAdapterError(f"OpenDental write_result failed: {exc}") from exc
        except requests.RequestException as exc:
            logger.warning("OpenDental write_result network error: %s", exc)
            return False

    def get_consent_status(self, patient_id: str, call_type: str) -> str:
        try:
            resp = requests.get(
                f"{self._base_url}/patients/{patient_id}/consent",
                params={"call_type": call_type},
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("status", "UNKNOWN").upper()
        except requests.RequestException:
            return "UNKNOWN"

    def _fetch_patient_phone(self, patient_id: str) -> str:
        resp = requests.get(
            f"{self._base_url}/patients/{patient_id}",
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        data  = resp.json()
        phone = data.get("hmPhone") or data.get("wkPhone") or data.get("wirelessPhone", "")
        if not phone:
            raise EHRAdapterError(f"No phone number found for patient {patient_id}")
        return self._to_e164(phone)

    @staticmethod
    def _to_e164(phone: str) -> str:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        raise EHRAdapterError(f"Cannot normalize phone to E.164: {phone!r}")
