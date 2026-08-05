import pytest
from fastapi.testclient import TestClient
from apps.python.medops_call_commander.server import app

client = TestClient(app)

def test_list_plans_empty():
    response = client.get("/api/plans")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_trigger_event_success():
    payload = {
        "event_type": "missed_appointment",
        "patient_id": "PAT-TEST-1",
        "patient_phone": "+14155550199",
        "source_system": "opendental"
    }
    response = client.post("/api/events/trigger", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    plan = data["plan"]
    assert plan["patient_id"] == "PAT-TEST-1"
    assert plan["agent"] == "patient"
    assert plan["state"] == "PENDING_APPROVAL"

def test_trigger_event_consent_denied():
    payload = {
        "event_type": "invoice_60_days",
        "patient_id": "noconsent_patient",
        "patient_phone": "+14155550199",
        "source_system": "fhir_r4"
    }
    response = client.post("/api/events/trigger", json=payload)
    assert response.status_code == 403
    assert "Consent" in response.json()["detail"]

def test_full_pipeline_approval_and_dispatch():
    # 1. Trigger
    trigger_resp = client.post("/api/events/trigger", json={
        "event_type": "loan_inquiry_submitted",
        "patient_id": "PAT-LOAN-99",
        "patient_phone": "+14155550888",
        "source_system": "fhir_r4"
    })
    assert trigger_resp.status_code == 200
    plan_id = trigger_resp.json()["plan"]["plan_id"]

    # 2. Approve
    approve_resp = client.post(f"/api/plans/{plan_id}/approve", json={
        "admin_id": "test_admin",
        "script": "Custom loan script test"
    })
    assert approve_resp.status_code == 200
    assert approve_resp.json()["plan"]["state"] == "APPROVED"
    assert approve_resp.json()["plan"]["script"] == "Custom loan script test"

    # 3. Dispatch
    dispatch_resp = client.post(f"/api/plans/{plan_id}/dispatch")
    assert dispatch_resp.status_code == 200
    data = dispatch_resp.json()
    assert data["status"] == "completed"
    assert data["plan"]["state"] == "COMPLETED"
    assert data["plan"]["is_phi_scrubbed"] is True
