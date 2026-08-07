"""
MedOps Call Commander — FastMCP Bridge
=======================================
Exposes the FastAPI server's REST endpoints as MCP stdio tools so that the
Google Antigravity (AGY) Supervisor agent can call them via Model Context Protocol.

Usage (standalone test):
    PYTHONPATH=. python mcp_server.py

Usage (via AGY agent):
    Configured automatically in agy_main.py via McpStdioServer.

Environment:
    MEDOPS_SERVER_URL   Base URL for the FastAPI server (default: http://localhost:8000)
"""

import json
import os
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERVER_URL = os.environ.get("MEDOPS_SERVER_URL", "http://localhost:8000").rstrip("/")

mcp = FastMCP("MedOps Call Commander")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _get(path: str) -> Any:
    """GET request to the FastAPI server."""
    resp = httpx.get(f"{SERVER_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    """POST request to the FastAPI server."""
    resp = httpx.post(f"{SERVER_URL}{path}", json=payload or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def trigger_event(
    event_type: str,
    patient_id: str,
    patient_phone: str,
    priority: str = "routine",
    source_system: str = "opendental",
    context: str = "{}",
) -> str:
    """
    Ingest an EHR event and create a CallPlan in PENDING_APPROVAL state.

    Args:
        event_type: The type of event (e.g. appointment_reminder, billing_reminder,
                    appointment_reschedule, payment_overdue, lending_offer, loan_followup).
        patient_id: The patient's internal ID (e.g. PAT-001).
        patient_phone: Patient phone number in E.164 format (e.g. +12125550100 — use real patient number in production).
        priority: Call priority — 'routine' or 'urgent'.
        source_system: Source EHR system — 'opendental' or 'fhir_r4'.
        context: JSON string with optional context fields (e.g. reference_id,
                 appointment_date, appointment_time, provider_name).
    """
    try:
        ctx = json.loads(context)
    except json.JSONDecodeError:
        ctx = {"raw": context}

    payload = {
        "event_type": event_type,
        "patient_id": patient_id,
        "patient_phone": patient_phone,
        "priority": priority,
        "source_system": source_system,
        "context": ctx,
    }
    result = _post("/api/events/trigger", payload)
    plan = result.get("plan", {})
    return (
        f"✅ CallPlan created.\n"
        f"  plan_id   : {plan.get('plan_id')}\n"
        f"  agent     : {plan.get('agent')}\n"
        f"  state     : {plan.get('state')}\n"
        f"  patient   : {plan.get('patient_id')} ({plan.get('phone_masked')})\n"
        f"  script    : {plan.get('script')}\n"
        f"  expires_at: {plan.get('expires_at')}\n"
        f"\nWaiting for HITL approval. Use approve_plan(plan_id) to proceed."
    )


@mcp.tool()
def list_plans() -> str:
    """
    List all current CallPlans sorted by creation time (newest first).
    Shows plan ID, state, agent type, patient ID, and masked phone number.
    """
    plans = _get("/api/plans")
    if not plans:
        return "No CallPlans found."
    lines = ["Current CallPlans:\n"]
    for p in plans:
        lines.append(
            f"  [{p['state']:18s}] {p['plan_id'][:8]}…  "
            f"agent={p['agent']}  patient={p['patient_id']}  "
            f"phone={p['phone_masked']}  priority={p['priority']}"
        )
    return "\n".join(lines)


@mcp.tool()
def approve_plan(plan_id: str, script: str = "") -> str:
    """
    Approve a CallPlan for dispatch. Optionally edit the call script before approving.
    The plan must be in PENDING_APPROVAL state.

    Args:
        plan_id: The plan UUID to approve.
        script:  Optional updated call script. Leave empty to keep the auto-generated script.
    """
    payload: Dict[str, Any] = {"admin_id": "agy_supervisor"}
    if script:
        payload["script"] = script
    result = _post(f"/api/plans/{plan_id}/approve", payload)
    plan = result.get("plan", {})
    return (
        f"✅ Plan approved.\n"
        f"  plan_id    : {plan.get('plan_id')}\n"
        f"  state      : {plan.get('state')}\n"
        f"  approved_by: {plan.get('approved_by')}\n"
        f"  script     : {plan.get('script')}\n"
        f"\nCall dispatch_plan(plan_id) to send the call to CALL-E."
    )


@mcp.tool()
def dispatch_plan(plan_id: str) -> str:
    """
    Dispatch an approved CallPlan to CALL-E. The plan must be in APPROVED state.
    PHI (phone number) is automatically scrubbed after dispatch.

    Args:
        plan_id: The plan UUID to dispatch.
    """
    result = _post(f"/api/plans/{plan_id}/dispatch")
    plan = result.get("plan", {})
    call_result = result.get("result", {})
    return (
        f"📞 Call dispatched and completed.\n"
        f"  plan_id     : {plan.get('plan_id')}\n"
        f"  state       : {plan.get('state')}\n"
        f"  outcome     : {call_result.get('outcome')}\n"
        f"  transcript  : {call_result.get('transcript_ref')}\n"
        f"  completed_at: {call_result.get('completed_at')}\n"
        f"  phi_scrubbed: {plan.get('is_phi_scrubbed')}\n"
        f"  summary     : {call_result.get('structured', {}).get('call_summary', 'N/A')}"
    )


@mcp.tool()
def dismiss_plan(plan_id: str) -> str:
    """
    Dismiss (reject) a CallPlan. The plan will not be dispatched.

    Args:
        plan_id: The plan UUID to dismiss.
    """
    result = _post(f"/api/plans/{plan_id}/dismiss")
    plan = result.get("plan", {})
    return (
        f"🚫 Plan dismissed.\n"
        f"  plan_id: {plan.get('plan_id')}\n"
        f"  state  : {plan.get('state')}"
    )


@mcp.tool()
def get_audit_log() -> str:
    """
    Retrieve the full audit log showing every state transition, approval, and PHI scrub.
    Returns entries in chronological order.
    """
    entries = _get("/api/audit")
    if not entries:
        return "Audit log is empty."
    lines = ["Audit Log:\n"]
    for e in entries:
        lines.append(
            f"  [{e['timestamp']}] {e['action']:25s} "
            f"plan={e['plan_id'][:8]}…  admin={e.get('admin_id', 'system')}  "
            f"reason={e.get('reason', '')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
