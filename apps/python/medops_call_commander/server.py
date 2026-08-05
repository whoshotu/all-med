import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.python.medops_call_commander.adapters.fhir import FHIRAdapter
from apps.python.medops_call_commander.adapters.opendental import OpenDentalAdapter
from apps.python.medops_call_commander.audit.log import AuditLog
from apps.python.medops_call_commander.core.enums import ConsentStatus, PlanState
from apps.python.medops_call_commander.core.exceptions import (
    ConsentDenied,
    MedOpsBaseException,
    UnroutableEvent,
)
from apps.python.medops_call_commander.core.models import AuditEntry, CallPlan, EHREvent
from apps.python.medops_call_commander.executor.executor import CallExecutor
from apps.python.medops_call_commander.gates.consent import ConsentGate
from apps.python.medops_call_commander.gates.hitl import HITLGate
from apps.python.medops_call_commander.providers.calle_mcp import CalleMcpProvider
from apps.python.medops_call_commander.supervisor.router import route

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medops_server")

app = FastAPI(
    title="MedOps Call Commander",
    description="Multi-agent HITL Phone Call Orchestration for Medical Practice Operations",
    version="1.0.0",
)

# Shared memory state
audit_log = AuditLog()
executor = CallExecutor(CalleMcpProvider())

# Optional HITL Gate via Telegram
hitl_gate: Optional[HITLGate] = None
if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID") and os.environ.get("HITL_SIGNING_SECRET"):
    try:
        hitl_gate = HITLGate(audit_log=audit_log)
        logger.info("HITL Telegram Gate initialized.")
    except Exception as e:
        logger.warning("HITL Telegram Gate initialization skipped: %s", e)

# Mock / Default Consent Source for demonstration when EHR consent APIs are offline
class FallbackConsentSource:
    def get_consent_status(self, patient_id: str, call_type: str) -> str:
        # Default all sample patients to GRANTED unless patient_id starts with 'noconsent'
        if patient_id.lower().startswith("noconsent") or patient_id == "PAT-999":
            return "DENIED"
        return "GRANTED"

consent_gate = ConsentGate(FallbackConsentSource())

# In-memory storage for active plans
PLANS_DB: Dict[str, CallPlan] = {}
RESULTS_DB: Dict[str, Any] = {}

# Pydantic Schemas
class TriggerEventRequest(BaseModel):
    event_type: str
    patient_id: str
    patient_phone: Optional[str] = "+14155550199"
    priority: Optional[str] = "routine"
    source_system: Optional[str] = "opendental"
    context: Optional[Dict[str, Any]] = None

class ApprovePlanRequest(BaseModel):
    script: Optional[str] = None
    admin_id: Optional[str] = "admin_web"


# Helper serializers
def plan_to_dict(plan: CallPlan) -> Dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "idempotency_key": plan.idempotency_key,
        "agent": plan.agent.value,
        "patient_id": plan.patient_id,
        "phone_masked": plan.phone_masked,
        "script": plan.script,
        "priority": plan.priority,
        "source_event": plan.source_event,
        "state": plan.state.value,
        "dry_run": plan.dry_run,
        "created_at": plan.created_at.isoformat(),
        "expires_at": plan.expires_at.isoformat() if plan.expires_at else None,
        "approved_by": plan.approved_by,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "dispatched_at": plan.dispatched_at.isoformat() if plan.dispatched_at else None,
        "scrubbed_at": plan.scrubbed_at.isoformat() if plan.scrubbed_at else None,
        "result_ref": plan.result_ref,
        "is_phi_scrubbed": plan.is_phi_scrubbed(),
    }


# Static assets mount
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def index_page():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>MedOps Call Commander API Running</h1><p>Static interface files not found.</p>"


@app.post("/api/events/trigger")
def trigger_event(req: TriggerEventRequest):
    """
    Receives an EHR event payload, routes to the appropriate agent, checks patient consent,
    generates a CallPlan in PENDING_APPROVAL, and notifies HITL admin.
    """
    event = EHREvent(
        event_type=req.event_type,
        patient_id=req.patient_id,
        patient_phone=req.patient_phone or "+14155550199",
        context=req.context or {"reference_id": f"REF-{req.patient_id}"},
        priority=req.priority or "routine",
        source_system=req.source_system or "opendental",
    )

    try:
        # Step 1: Supervisor Route to Domain Agent
        plan = route(event)

        # Step 2: Check Consent Gate
        consent_gate.check(event.patient_id, plan.agent.value)

        # Step 3: Transition to PENDING_APPROVAL
        plan.state = PlanState.PENDING_APPROVAL
        PLANS_DB[plan.plan_id] = plan

        # Step 4: Audit Entry
        audit_log.append(AuditEntry(
            plan_id=plan.plan_id,
            action="CREATED",
            agent_type=plan.agent.value,
            admin_id="system",
            reason=f"Event '{event.event_type}' routed to agent '{plan.agent.value}'",
        ))

        # Step 5: Telegram HITL Notification if enabled
        if hitl_gate:
            try:
                hitl_gate.notify(plan)
            except Exception as e:
                logger.warning("Telegram notification failed: %s", e)

        return {"status": "success", "plan": plan_to_dict(plan)}

    except ConsentDenied as e:
        logger.warning("Consent blocked call creation for patient %s: %s", req.patient_id, e)
        audit_log.append(AuditEntry(
            plan_id="N/A",
            action="BLOCKED_CONSENT_DENIED",
            admin_id="system",
            reason=f"Consent denied for patient {req.patient_id}",
        ))
        raise HTTPException(status_code=403, detail=str(e))

    except UnroutableEvent as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MedOpsBaseException as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plans")
def list_plans():
    """List all call plans sorted by creation time descending."""
    sorted_plans = sorted(PLANS_DB.values(), key=lambda p: p.created_at, reverse=True)
    return [plan_to_dict(p) for p in sorted_plans]


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    if plan_id not in PLANS_DB:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = PLANS_DB[plan_id]
    result = RESULTS_DB.get(plan_id)
    return {"plan": plan_to_dict(plan), "result": result}


@app.post("/api/plans/{plan_id}/approve")
def approve_plan(plan_id: str, req: ApprovePlanRequest):
    """Approve call plan via Web Dashboard or Telegram callback."""
    if plan_id not in PLANS_DB:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = PLANS_DB[plan_id]

    if not plan.is_approvable():
        raise HTTPException(
            status_code=400,
            detail=f"Plan is in state '{plan.state.value}', not approvable.",
        )

    # Optional script edit during approval
    if req.script:
        plan.script = req.script

    plan.state = PlanState.APPROVED
    plan.dry_run = False
    plan.approved_by = req.admin_id or "admin_web"
    plan.approved_at = datetime.now(timezone.utc)

    audit_log.append(AuditEntry(
        plan_id=plan.plan_id,
        action="APPROVED",
        agent_type=plan.agent.value,
        admin_id=plan.approved_by,
        reason="Admin approval confirmed",
    ))

    return {"status": "approved", "plan": plan_to_dict(plan)}


@app.post("/api/plans/{plan_id}/dispatch")
def dispatch_plan(plan_id: str, background_tasks: BackgroundTasks):
    """Dispatches an approved CallPlan to CALL-E."""
    if plan_id not in PLANS_DB:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = PLANS_DB[plan_id]

    if not plan.is_dispatchable():
        raise HTTPException(
            status_code=400,
            detail=f"Plan cannot be dispatched in state '{plan.state.value}'. Must be APPROVED with dry_run=False.",
        )

    # Run dispatch
    try:
        call_result = executor.run(plan)

        # Store result
        RESULTS_DB[plan_id] = {
            "plan_id": call_result.plan_id,
            "outcome": call_result.outcome.value,
            "transcript_ref": call_result.transcript_ref,
            "structured": call_result.structured,
            "completed_at": call_result.completed_at.isoformat(),
        }

        # Audit log dispatch & outcome
        audit_log.append(AuditEntry(
            plan_id=plan.plan_id,
            action="DISPATCHED",
            agent_type=plan.agent.value,
            admin_id="system",
            reason=f"Call dispatched to CALL-E (ref: {call_result.transcript_ref})",
        ))

        audit_log.append(AuditEntry(
            plan_id=plan.plan_id,
            action="COMPLETED",
            agent_type=plan.agent.value,
            admin_id="system",
            reason=f"Call completed with outcome '{call_result.outcome.value}'",
        ))

        # Scrub PHI phone_e164 post-dispatch
        plan.phone_e164 = ""
        plan.scrubbed_at = datetime.now(timezone.utc)

        audit_log.append(AuditEntry(
            plan_id=plan.plan_id,
            action="PHI_SCRUBBED",
            admin_id="system",
            reason="E.164 phone zeroed post-dispatch",
        ))

        return {
            "status": "completed",
            "plan": plan_to_dict(plan),
            "result": RESULTS_DB[plan_id],
        }

    except Exception as e:
        plan.state = PlanState.FAILED
        audit_log.append(AuditEntry(
            plan_id=plan.plan_id,
            action="FAILED",
            admin_id="system",
            reason=f"Execution error: {str(e)}",
        ))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plans/{plan_id}/dismiss")
def dismiss_plan(plan_id: str):
    if plan_id not in PLANS_DB:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = PLANS_DB[plan_id]
    plan.state = PlanState.DISMISSED
    audit_log.append(AuditEntry(
        plan_id=plan.plan_id,
        action="DISMISSED",
        admin_id="admin_web",
        reason="Plan dismissed by admin",
    ))
    return {"status": "dismissed", "plan": plan_to_dict(plan)}


@app.get("/api/audit")
def get_audit_log():
    """Retrieve full audit log entries."""
    entries = audit_log.all()
    return [
        {
            "plan_id": e.plan_id,
            "action": e.action,
            "agent_type": e.agent_type,
            "admin_id": e.admin_id,
            "reason": e.reason,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in entries
    ]


@app.post("/hitl/webhook")
async def telegram_webhook(request: Request):
    """Incoming Telegram Webhook callback endpoint."""
    if not hitl_gate:
        return JSONResponse(content={"ok": False, "reason": "HITL gate disabled"}, status_code=400)

    payload = await request.json()
    logger.info("Telegram Webhook payload received: %s", payload)

    # Process callback query
    callback_query = payload.get("callback_query")
    if callback_query:
        data = callback_query.get("data", "")
        parts = data.split(":")
        if len(parts) >= 2:
            plan_id = parts[0]
            action = parts[1]
            if plan_id in PLANS_DB:
                plan = PLANS_DB[plan_id]
                admin_id = str(callback_query.get("from", {}).get("username", "telegram_admin"))
                if action == "approve":
                    plan.state = PlanState.APPROVED
                    plan.dry_run = False
                    plan.approved_by = admin_id
                    plan.approved_at = datetime.now(timezone.utc)
                    audit_log.append(AuditEntry(
                        plan_id=plan_id,
                        action="APPROVED",
                        admin_id=admin_id,
                        reason="Telegram HITL Callback Approve",
                    ))
                elif action == "dismiss":
                    plan.state = PlanState.DISMISSED
                    audit_log.append(AuditEntry(
                        plan_id=plan_id,
                        action="DISMISSED",
                        admin_id=admin_id,
                        reason="Telegram HITL Callback Dismiss",
                    ))

    return {"ok": True}
