# MedOps Call Commander

> Multi-agent HITL phone call orchestration for medical practice operations —
> appointments, billing, lending — built on **CALL-E**.

Built for the **CALL-E Hackathon**.

---

## Overview

MedOps Call Commander connects your EHR system to outbound AI phone calls via CALL-E, with a Human-in-the-Loop (HITL) gate that lets an admin **approve, edit, or dismiss** every call before it is dispatched — either from a live web dashboard or via Telegram.

```
EHR Event → Supervisor Router → Domain Agent (Appointments / Billing / Lending)
  → Consent Gate → CallPlan (PENDING_APPROVAL)
    → HITL Gate (Web Dashboard ✦ or Telegram)
      → CALL-E Dispatch → PHI Scrub → Audit Log
```

---

## Features

| Feature | Detail |
|---|---|
| **Multi-agent routing** | Supervisor auto-routes events to Appointments, Billing, or Lending agents |
| **Consent Gate** | Patient consent is checked before any plan is created |
| **HITL Web Dashboard** | In-browser approve / dismiss buttons with live status polling |
| **Telegram HITL** | Optional bot-based approve / dismiss inline keyboard |
| **CALL-E Integration** | Native MCP provider with simulation fallback for offline demo |
| **PHI Scrubbing** | E.164 phone number zeroed from plan after dispatch |
| **Full Audit Trail** | Every state transition logged with actor, reason, and timestamp |

---

## Quick Start

### 1. Clone & set up environment

```bash
git clone <repo-url>
cd all-med

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your CALL-E API key and (optionally) Telegram credentials
```

### 3. Run the server

```bash
PYTHONPATH=. uvicorn apps.python.medops_call_commander.server:app --reload --port 8000
```

Open **http://localhost:8000** — the dashboard loads automatically.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CALLE_API_KEY` | ✅ For live calls | CALL-E API key |
| `CALLE_API_BASE_URL` | Optional | Defaults to `https://api.heycall-e.com` |
| `CALLE_WEBHOOK_URL` | Optional | Your public ngrok URL for CALL-E status webhooks |
| `TELEGRAM_BOT_TOKEN` | Optional | Enable Telegram HITL gate |
| `TELEGRAM_ADMIN_CHAT_ID` | Optional | Telegram chat ID for admin notifications |
| `HITL_SIGNING_SECRET` | Optional | HMAC secret for Telegram callback verification |
| `OPENDENTAL_API_URL` | Optional | OpenDental REST API base URL |
| `OPENDENTAL_API_KEY` | Optional | OpenDental API key |
| `FHIR_BASE_URL` | Optional | FHIR R4 base URL |
| `FHIR_BEARER_TOKEN` | Optional | FHIR bearer token |

> **Note:** The system runs in **demo simulation mode** if `CALLE_API_KEY` is not set.
> The Web Dashboard includes a built-in EHR event simulator — no live EHR needed.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/events/trigger` | Ingest an EHR event → create a CallPlan |
| `GET` | `/api/plans` | List all plans |
| `GET` | `/api/plans/{id}` | Get a plan + call result |
| `POST` | `/api/plans/{id}/approve` | HITL approve (with optional script edit) |
| `POST` | `/api/plans/{id}/dispatch` | Dispatch approved plan to CALL-E |
| `POST` | `/api/plans/{id}/dismiss` | Dismiss / reject a plan |
| `GET` | `/api/audit` | Full audit log |
| `POST` | `/hitl/webhook` | Telegram bot webhook receiver |

Interactive API docs: **http://localhost:8000/docs**

---

## Running Tests

```bash
PYTHONPATH=. pytest tests/ -v
```

---

## Architecture

```
apps/python/medops_call_commander/
├── server.py              # FastAPI orchestration backbone
├── config.py              # Settings (env-driven)
├── core/                  # Enums, models, exceptions
├── supervisor/            # Event router
├── agents/                # Appointments, Billing, Lending agents
├── gates/                 # Consent gate, HITL gate (Telegram)
├── executor/              # CallExecutor (bounded polling)
├── providers/             # CALL-E MCP provider + CalleClient SDK wrapper
├── adapters/              # FHIR & OpenDental EHR adapters
├── audit/                 # In-memory audit log
└── static/                # Web Dashboard (HTML/CSS/JS)
```

---

## License

MIT
