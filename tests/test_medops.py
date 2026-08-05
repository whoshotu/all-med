import pytest
from datetime import datetime

from apps.python.medops_call_commander.core.enums import AgentType, PlanState, ConsentStatus
from apps.python.medops_call_commander.core.exceptions import AgentBoundaryViolation, ConsentDenied, UnroutableEvent
from apps.python.medops_call_commander.core.models import EHREvent
from apps.python.medops_call_commander.supervisor.router import route
from apps.python.medops_call_commander.agents.patient import PatientAgent
from apps.python.medops_call_commander.agents.billing import BillingAgent
from apps.python.medops_call_commander.agents.lending import LendingAgent
from apps.python.medops_call_commander.gates.consent import ConsentGate
from apps.python.medops_call_commander.audit.log import AuditLog, AuditEntry


def test_supervisor_routing_patient():
    event = EHREvent(
        event_type="missed_appointment",
        patient_id="PAT-100",
        patient_phone="+14155550100",
        context={"reference_id": "REF-1"},
        priority="routine",
        source_system="opendental",
    )
    plan = route(event)
    assert plan.agent == AgentType.PATIENT
    assert plan.state == PlanState.CREATED
    assert plan.dry_run is True
    assert "missed appointment" in plan.script.lower()


def test_supervisor_routing_billing():
    event = EHREvent(
        event_type="invoice_60_days",
        patient_id="PAT-200",
        patient_phone="+14155550200",
        context={"reference_id": "REF-2"},
        priority="routine",
        source_system="fhir_r4",
    )
    plan = route(event)
    assert plan.agent == AgentType.BILLING
    assert "60 days past due" in plan.script.lower()


def test_supervisor_unroutable_event():
    event = EHREvent(
        event_type="unknown_medical_event",
        patient_id="PAT-300",
        patient_phone="+14155550300",
        context={},
        priority="routine",
        source_system="fhir_r4",
    )
    with pytest.raises(UnroutableEvent):
        route(event)


def test_agent_boundary_violation():
    agent = PatientAgent()
    event = EHREvent(
        event_type="invoice_90_days",
        patient_id="PAT-400",
        patient_phone="+14155550400",
        context={},
        priority="urgent",
        source_system="opendental",
    )
    with pytest.raises(AgentBoundaryViolation):
        agent.handle(event)


class MockConsentSource:
    def __init__(self, status: str):
        self.status = status

    def get_consent_status(self, patient_id: str, call_type: str) -> str:
        return self.status


def test_consent_gate_granted():
    gate = ConsentGate(MockConsentSource("GRANTED"))
    status = gate.check("PAT-100", "patient")
    assert status == ConsentStatus.GRANTED


def test_consent_gate_denied():
    gate = ConsentGate(MockConsentSource("DENIED"))
    with pytest.raises(ConsentDenied):
        gate.check("PAT-100", "patient")


def test_audit_log_phi_rejection():
    audit = AuditLog()
    with pytest.raises(ValueError, match="appears to contain PHI"):
        audit.append(AuditEntry(
            plan_id="p1",
            action="TEST",
            reason="User phone was +14155550100"
        ))
