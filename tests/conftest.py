"""
conftest.py — pytest session-level fixtures.

Sets MEDOPS_TEST_MODE=1 before server.py is imported so production startup
guards (EHR adapter, CALL-E) don't fire during tests.

Provides test-only EHR consent and CALL-E provider classes that tests wire
directly into the server module state.

All test phone numbers use the NANP 555-01xx reserved fictional range.
"""

import os

# Must be set before server.py is imported by any test module
os.environ.setdefault("MEDOPS_TEST_MODE", "1")


# ---------------------------------------------------------------------------
# Test-only EHR consent source (no network calls)
# ---------------------------------------------------------------------------
class _TestConsentSource:
    """Grants consent to all patients except IDs starting with 'noconsent'."""

    def get_consent_status(self, patient_id: str, call_type: str) -> str:
        if patient_id.lower().startswith("noconsent"):
            return "DENIED"
        return "GRANTED"


# ---------------------------------------------------------------------------
# Test-only CALL-E provider (no network calls, deterministic output)
# ---------------------------------------------------------------------------
class _TestCallProvider:
    def dispatch(self, plan):
        return f"test-call-{plan.plan_id[:8]}"

    def get_result(self, plan_id, external_id):
        from apps.python.medops_call_commander.core.enums import CallOutcome
        from apps.python.medops_call_commander.core.models import CallResult
        return CallResult(
            plan_id=plan_id,
            outcome=CallOutcome.ANSWERED,
            transcript_ref=external_id,
            structured={"call_summary": "Test call completed."},
        )

    def cancel(self, external_id):
        pass
