"""
Server integration tests.

EHR adapter and CALL-E provider are mocked in tests/conftest.py — no real
credentials required. Phone numbers use the NANP 555-01xx reserved fictional range.
"""

import pytest
from fastapi.testclient import TestClient
from apps.python.medops_call_commander.server import app, PLANS_DB
import apps.python.medops_call_commander.server as server_module
from tests.conftest import _TestConsentSource, _TestCallProvider
from apps.python.medops_call_commander.auth import create_access_token

# Wire the test providers into the already-constructed server state
server_module.consent_gate._source = _TestConsentSource()
server_module.executor._provider = _TestCallProvider()

client = TestClient(app)

def get_auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


def test_login_success():
    response = client.post("/api/login", json={"username": "admin", "password": "medops2026"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_unauthorized_access():
    response = client.get("/api/plans")
    assert response.status_code == 401


def test_list_plans_empty():
    response = client.get("/api/plans", headers=get_auth_headers())
    assert response.status_code == 200
    assert isinstance(response.json(), list)


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

    # 3. Dispatch
    dispatch_resp = client.post(f"/api/plans/{plan_id}/dispatch", headers=get_auth_headers())
    assert dispatch_resp.status_code == 200
    data = dispatch_resp.json()
    assert data["plan"]["state"] == "COMPLETED"
    assert data["plan"]["is_phi_scrubbed"] is True
