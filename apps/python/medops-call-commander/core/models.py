from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import AgentType, CallOutcome, ConsentStatus, PlanState

# ---------------------------------------------------------------------------
# EHR Adapter output — normalized event from any EHR source
# ---------------------------------------------------------------------------

@dataclass
class EHREvent:
    event_type: str          # e.g. "missed_appointment", "invoice_30_days"
    patient_id: str          # internal EHR identifier — not a name
    patient_phone: str       # E.164 — encrypted immediately on receipt, zeroed after use
    context: dict            # minimum necessary domain payload only
    priority: str            # "routine" | "urgent"
    source_system: str       # "opendental" | "fhir_r4"
    received_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Core plan — produced by domain agents, consumed by HITL gate + executor
# ---------------------------------------------------------------------------

@dataclass
class CallPlan:
    plan_id: str                         # uuid4
    idempotency_key: str                 # sha256 of patient_id+event_type+agent+reference_id
    agent: AgentType
    patient_id: str                      # EHR internal ID only
    phone_masked: str                    # e.g. "+1... ... 8435" — shown to admin
    phone_e164: str                      # real number — encrypted at rest, zeroed post-dispatch
    script: str                          # editable by admin before approval
    priority: str
    source_event: str                    # EHREvent.event_type that triggered this
    state: PlanState = PlanState.CREATED
    dry_run: bool = True                 # remains True until admin explicitly approves
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    approved_by: Optional[str] = None   # admin user ID — required before dispatch
    approved_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    scrubbed_at: Optional[datetime] = None
    result_ref: Optional[str] = None    # opaque CALL-E result ID — no transcript content

    def is_phi_scrubbed(self) -> bool:
        return self.scrubbed_at is not None

    def is_approvable(self) -> bool:
        return self.state == PlanState.PENDING_APPROVAL

    def is_dispatchable(self) -> bool:
        return (
            self.state == PlanState.APPROVED
            and not self.dry_run
            and self.approved_by is not None
            and self.approved_at is not None
        )


# ---------------------------------------------------------------------------
# Result returned by the executor after CALL-E completes the call
# ---------------------------------------------------------------------------

@dataclass
class CallResult:
    plan_id: str
    outcome: CallOutcome
    transcript_ref: str              # opaque CALL-E ID only — no content stored locally
    structured: dict                 # e.g. {"rescheduled": True, "promise_date": "2026-08-10"}
    completed_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Immutable audit entry — never contains PHI
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    plan_id: str
    action: str                      # e.g. "CREATED", "APPROVED", "PHI_SCRUBBED"
    agent_type: Optional[str] = None
    admin_id: Optional[str] = None
    reason: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    # NOTE: never add phone numbers, patient names, balances, or transcript content here


# ---------------------------------------------------------------------------
# Idempotency key builder — deterministic, content-bound
# ---------------------------------------------------------------------------

def make_idempotency_key(patient_id: str, event_type: str, agent: AgentType, reference_id: str) -> str:
    payload = f"{patient_id}:{event_type}:{agent.value}:{reference_id}"
    return hashlib.sha256(payload.encode()).hexdigest()
