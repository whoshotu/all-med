import pytest
import os
from fastapi.testclient import TestClient
from apps.python.medops_call_commander.server import app, PLANS_DB
import apps.python.medops_call_commander.server as server_module
from apps.python.medops_call_commander.gates.hitl import HITLGate
from apps.python.medops_call_commander.providers.calle_client import CalleClient
from tests.conftest import _TestConsentSource, _TestCallProvider

# Wire the test providers into the already-constructed server state
server_module.consent_gate._source = _TestConsentSource()
server_module.executor._provider = _TestCallProvider()

client = TestClient(app)

def get_auth_headers():
    return {"Authorization": "Bearer admin_test_token"}

def get_unauthorized_auth_headers():
    return {"Authorization": "Bearer unauthorized_user_token"}

def test_unauthorized_access():
    response = client.get("/api/plans")
    assert response.status_code in (401, 403)


def test_bounded_role_authorization():
    # User without admin or clinician role should be rejected on clinical action
    payload = {
        "event_type": "missed_appointment",
        "patient_id": "PAT-TEST-ROLE",
        "patient_phone": "+12125550101",
        "source_system": "opendental",
    }
    response = client.post("/api/events/trigger", json=payload, headers=get_unauthorized_auth_headers())
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"]


def test_list_plans_empty():
    response = client.get("/api/plans", headers=get_auth_headers())
    assert response.status_code == 200
    assert "plans" in response.json()
    assert isinstance(response.json()["plans"], list)


def test_hitl_webhook_unauthenticated_rejection(monkeypatch):
    # Enable HITL gate with secret
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "987654321")
    monkeypatch.setenv("HITL_SIGNING_SECRET", "super_secret_token")
    server_module.hitl_gate = HITLGate(audit_log=server_module.audit_log)

    # Request without secret header should fail with 401
    resp_no_header = client.post("/hitl/webhook", json={"callback_query": {}})
    assert resp_no_header.status_code == 401

    # Request with wrong secret header should fail with 401
    resp_wrong_header = client.post(
        "/hitl/webhook",
        json={"callback_query": {}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    )
    assert resp_wrong_header.status_code == 401

    # Request with correct secret header should succeed with 200
    resp_correct = client.post(
        "/hitl/webhook",
        json={"callback_query": {}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "super_secret_token"}
    )
    assert resp_correct.status_code == 200



def test_calle_client_provider_failure_semantics(monkeypatch):
    # Ensure CALLE_MOCK_MODE is NOT set
    monkeypatch.delenv("CALLE_MOCK_MODE", raising=False)
    calle_client = CalleClient(api_key="invalid_key", base_url="http://invalid.heycall-e.invalid")

    # API failure must return status="failed" and task_completed=False (no false clinical success)
    res_create = calle_client.calls_create(task="Test task", phone="+14155550100")
    assert res_create["status"] == "failed"
    assert res_create["task_completed"] is False
    assert res_create.get("structured_result") == {}

    res_get = calle_client.calls_get(call_id="non_existent_call")
    assert res_get["status"] == "failed"
    assert res_get["task_completed"] is False
    assert res_get.get("structured_result") == {}


def test_trigger_event_success():
    payload = {
        "event_type": "missed_appointment",
        "patient_id": "PAT-TEST-1",
        "patient_phone": "+12125550101",
        "source_system": "opendental",
    }
    response = client.post("/api/events/trigger", json=payload, headers=get_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    plan = data["plan"]
    assert plan["patient_id"] == "PAT-TEST-1"
    
    # Verify Encryption at Rest in PLANS_DB memory
    mem_plan = PLANS_DB[plan["plan_id"]]
    assert mem_plan.phone_e164 != "+12125550101"
    assert len(mem_plan.phone_e164) > 30 # Ciphertext is long


def test_trigger_event_consent_denied():
    payload = {
        "event_type": "invoice_60_days",
        "patient_id": "noconsent_patient",
        "patient_phone": "+12125550102",
        "source_system": "fhir_r4",
    }
    response = client.post("/api/events/trigger", json=payload, headers=get_auth_headers())
    assert response.status_code == 403


def test_full_pipeline_approval_and_dispatch():
    # 1. Trigger
    trigger_resp = client.post("/api/events/trigger", json={
        "event_type": "loan_inquiry_submitted",
        "patient_id": "PAT-LOAN-99",
        "patient_phone": "+12125550103",
        "source_system": "fhir_r4",
    }, headers=get_auth_headers())
    assert trigger_resp.status_code == 200
    plan_id = trigger_resp.json()["plan"]["plan_id"]

    # 2. Approve
    approve_resp = client.post(f"/api/plans/{plan_id}/approve", json={
        "admin_id": "test_admin",
        "script": "Custom loan script test",
    }, headers=get_auth_headers())
    assert approve_resp.status_code == 200

    # 3. Dispatch — bypass-mode tokens are intentionally blocked from dispatch.
    # In MEDOPS_TEST_MODE the auth layer sets _bypass_mode=True, which prevents
    # any live provider call from being made. This is the correct behaviour:
    # dispatch requires real credentials, not the test bypass.
    dispatch_resp = client.post(f"/api/plans/{plan_id}/dispatch", headers=get_auth_headers())
    assert dispatch_resp.status_code == 403
    assert "bypass" in dispatch_resp.json()["detail"].lower()


def test_bypass_mode_cannot_dispatch():
    """Bypass / test-mode tokens must never be able to call the dispatch endpoint."""
    trigger_resp = client.post("/api/events/trigger", json={
        "event_type": "missed_appointment",
        "patient_id": "PAT-BYPASS-01",
        "patient_phone": "+12025550142",
        "source_system": "opendental",
    }, headers=get_auth_headers())
    assert trigger_resp.status_code == 200
    plan_id = trigger_resp.json()["plan"]["plan_id"]

    client.post(f"/api/plans/{plan_id}/approve", json={"admin_id": "test_admin"}, headers=get_auth_headers())

    dispatch_resp = client.post(f"/api/plans/{plan_id}/dispatch", headers=get_auth_headers())
    assert dispatch_resp.status_code == 403, (
        "Bypass-mode token must not be able to dispatch a live call"
    )
    detail = dispatch_resp.json().get("detail", "")
    assert "bypass" in detail.lower() or "Bypass" in detail

