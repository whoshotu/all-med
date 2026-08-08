# MedOps Call Commander

Multi-agent outbound phone call orchestration for medical practice operations.
Covers appointments, billing, and patient financing. Built on the CALL-E voice API.

## What it does

When a patient misses an appointment, has an outstanding balance, or submits a
financing inquiry, the system:

1. Receives a webhook from your EHR (OpenDental or any FHIR R4 system)
2. Checks patient consent on file before doing anything
3. Routes the event to the appropriate domain agent (Appointments, Billing, or Lending)
4. Generates a compliant call script
5. Holds the plan for administrator review
6. Dispatches the call via CALL-E only after a human approves it
7. Scrubs the phone number from the plan record after dispatch
8. Logs every action to a persistent, HIPAA-compliant SQLite audit trail

## Requirements

- Python 3.12 or later
- A CALL-E API key (heycall-e.com)
- An EHR connection: OpenDental API or any FHIR R4 endpoint
- A publicly reachable HTTPS URL for CALL-E webhooks (ngrok works for local dev)

## Setup

```bash
git clone https://github.com/whoshotu/all-med
cd all-med
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

See `.env.example` for documentation on every variable.

Run the server:

```bash
PYTHONPATH=. uvicorn apps.python.medops_call_commander.server:app --reload --port 8000
```

Open `http://localhost:8000` to reach the dashboard.

## Environment Variables

All configuration is through environment variables. The full reference is in `.env.example`.

### Required

| Variable | Description |
|---|---|
| `CALLE_API_KEY` | CALL-E API key for outbound call dispatch |
| `OPENDENTAL_API_URL` | OpenDental REST API base URL |
| `OPENDENTAL_DEVELOPER_KEY` | Your developer key, issued by Open Dental |

### Required for a real practice (optional for demo office)

| Variable | Description |
|---|---|
| `OPENDENTAL_CUSTOMER_KEY` | Per-practice key generated in the Open Dental Developer Portal |

### FHIR alternative to OpenDental

| Variable | Description |
|---|---|
| `FHIR_BASE_URL` | FHIR R4 server base URL |
| `FHIR_BEARER_TOKEN` | OAuth2 bearer token for the FHIR server |

### Optional

| Variable | Description |
|---|---|
| `CALLE_API_BASE_URL` | Override the default CALL-E API endpoint |
| `CALLE_WEBHOOK_URL` | Public HTTPS URL for CALL-E to POST call status updates |
| `GEMINI_API_KEY` | Required only for the AGY agent CLI (agy_main.py) |
| `TELEGRAM_BOT_TOKEN` | Enables the Telegram HITL approval gate |
| `TELEGRAM_ADMIN_CHAT_ID` | Telegram chat ID to receive approval requests |
| `HITL_SIGNING_SECRET` | HMAC secret for verifying Telegram callback authenticity |
| `MEDOPS_TEST_PHONE` | Your phone number for end-to-end testing (E.164 format) |
| `MEDOPS_CONSENT_BYPASS` | Set to `1` to skip consent check during demo testing only |
| `OPENDENTAL_CONSENT_FIELD` | Name of the PatField storing TCPA consent (default: MEDOPS_CALL_CONSENT) |

## OpenDental API Setup

The Open Dental API uses a two-key authentication scheme.

To get your developer key, email `vendor.relations@opendental.com` with:
- Your company name
- The API resources you need: Patients GET and PatFields GET (Read All, free tier)
- A description of your integration

To generate a customer key for a practice:
1. Log into the Open Dental Developer Portal
2. Click Add to generate a key
3. In Open Dental at the practice, go to Setup, Advanced Setup, API, Add Key and paste it

To enable consent checking in a real practice:
1. In Open Dental, go to Setup, Patient Field Defs, Add
2. Name the field `MEDOPS_CALL_CONSENT`
3. Set the value to `Y` on each patient who has given written TCPA consent

## API Reference

| Method | Path | Description |
|---|---|---|
| POST | `/api/events/trigger` | Receive an EHR event and create a call plan |
| GET | `/api/plans` | List all call plans |
| GET | `/api/plans/{id}` | Get a single plan and its result |
| POST | `/api/plans/{id}/approve` | Approve a plan, optionally editing the script |
| POST | `/api/plans/{id}/dispatch` | Dispatch an approved plan to CALL-E |
| POST | `/api/plans/{id}/dismiss` | Reject and close a plan |
| GET | `/api/audit` | Full audit log |
| GET | `/api/config` | Dashboard configuration (test phone, adapter in use) |
| POST | `/hitl/webhook` | Telegram bot webhook receiver |

Interactive docs are available at `http://localhost:8000/docs` when the server is running.

## Running Tests

```bash
PYTHONPATH=. pytest tests/ -v
```

Tests run without any credentials. Set `MEDOPS_TEST_MODE=1` or let `conftest.py`
handle it automatically.

## Project Structure

```
apps/python/medops_call_commander/
    server.py           FastAPI application and route handlers
    config.py           Environment validation
    core/               Data models, enums, and exceptions
    supervisor/         Event routing logic
    agents/             Appointments, Billing, and Lending domain agents
    gates/              Consent gate and Telegram HITL gate
    executor/           CALL-E polling and dispatch logic
    providers/          CALL-E MCP provider and client
    adapters/           OpenDental and FHIR EHR adapters
    audit/              Persistent SQLite-backed audit log (HIPAA compliant)
    static/             Web dashboard (HTML, CSS, JS)

skills/
    appointments/       AGY skill definition for appointment events
    billing/            AGY skill definition for billing events
    lending/            AGY skill definition for financing events

agy_main.py             AGY agent CLI entry point
mcp_server.py           MCP bridge exposing the FastAPI server as tools
```

## Security Notes

- Patient phone numbers are stored only for the duration between plan creation
  and dispatch. They are zeroed from the plan record after CALL-E confirms receipt.
- The consent gate blocks plan creation for any patient without a confirmed
  consent record in the EHR.
- Every state change is written to a persistent, file-system protected SQLite audit log with a timestamp and actor ID (45 CFR § 164.312(1)(b) compliant).
- No patient data is written back to OpenDental. Call outcomes are stored in the
  MedOps audit log only.
- The CALL-E API key and EHR credentials must be set via environment variables.
  They are never logged or included in API responses.

## License

MIT
