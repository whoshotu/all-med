"""
MedOps Call Commander — AGY Supervisor Entry Point
====================================================
Multi-agent orchestrator using the Google Antigravity SDK.

The Supervisor agent:
  - Loads three domain skills (Appointments, Billing, Lending) from skills/
  - Connects to the FastMCP bridge (mcp_server.py) via stdio
  - Spawns subagents as needed for domain-specific call plan creation
  - Enforces HITL approval before any call is dispatched

Usage:
    # Start the FastAPI server first (in another terminal):
    PYTHONPATH=. uvicorn apps.python.medops_call_commander.server:app --port 8000

    # Then run the AGY agent:
    PYTHONPATH=. python agy_main.py "Remind patient PAT-001 about appointment tomorrow at 2pm"

    # Interactive mode (no prompt argument):
    PYTHONPATH=. python agy_main.py

Environment variables:
    GEMINI_API_KEY      Required — Gemini API key for the AGY agent
    MEDOPS_SERVER_URL   Optional — FastAPI base URL (default: http://localhost:8000)
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.antigravity import Agent, LocalAgentConfig, types

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
SKILLS_DIR = PROJECT_ROOT / "skills"
MCP_SERVER = PROJECT_ROOT / "mcp_server.py"

# ---------------------------------------------------------------------------
# Supervisor system instructions
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTIONS = """
You are the MedOps Call Commander Supervisor — an AI orchestrator for a medical
practice's outbound phone call pipeline.

Your responsibilities:
1. Classify incoming requests into one of three domains:
   - Appointments (appointment_reminder, appointment_reschedule)
   - Billing (billing_reminder, payment_overdue)
   - Lending (lending_offer, loan_followup)

2. Use your domain skills (loaded from the skills/ directory) to generate
   appropriate call scripts and trigger events via the MCP tools.

3. ALWAYS follow the HITL workflow:
   a. Call trigger_event → get plan_id
   b. Show the admin the plan details and generated script
   c. Ask for explicit approval before calling dispatch_plan
   d. Call approve_plan, then dispatch_plan only after confirmed approval

4. NEVER dispatch a call without explicit admin confirmation.

5. If a request is ambiguous, ask clarifying questions before triggering an event.

6. After every dispatch, confirm the outcome and that PHI has been scrubbed.

Available MCP tools:
- trigger_event   — create a CallPlan from an EHR event
- list_plans      — see all pending/active plans
- approve_plan    — approve a plan (optionally edit the script)
- dispatch_plan   — send an approved plan to CALL-E
- dismiss_plan    — reject/cancel a plan
- get_audit_log   — view the full audit trail

You operate on behalf of authorised medical practice administrators only.
"""

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------
def build_config() -> LocalAgentConfig:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "⚠️  GEMINI_API_KEY not set.\n"
            "   Get one at: https://aistudio.google.com/app/api-keys\n"
            "   Then add it to your .env file: GEMINI_API_KEY=your_key_here\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return LocalAgentConfig(
        api_key=api_key,
        system_instructions=SYSTEM_INSTRUCTIONS,
        skills_paths=[str(SKILLS_DIR)],
        mcp_servers=[
            types.McpStdioServer(
                command=sys.executable,
                args=[str(MCP_SERVER)],
                env={
                    **os.environ,
                    "MEDOPS_SERVER_URL": os.environ.get(
                        "MEDOPS_SERVER_URL", "http://localhost:8000"
                    ),
                },
            )
        ],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def chat_once(prompt: str) -> None:
    """Send a single prompt and stream the response."""
    config = build_config()
    async with Agent(config) as agent:
        print(f"\n🏥 MedOps Supervisor > {prompt}\n")
        print("─" * 60)
        response = await agent.chat(prompt)
        async for chunk in response:
            print(chunk, end="", flush=True)
        print("\n" + "─" * 60)


async def interactive() -> None:
    """Interactive REPL mode."""
    config = build_config()
    print("\n🏥 MedOps Call Commander — AGY Supervisor")
    print("   Type your request, or 'quit' to exit.\n")
    async with Agent(config) as agent:
        while True:
            try:
                prompt = input("Admin > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break
            print()
            response = await agent.chat(prompt)
            async for chunk in response:
                print(chunk, end="", flush=True)
            print("\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single-shot mode: pass prompt as CLI argument
        user_prompt = " ".join(sys.argv[1:])
        asyncio.run(chat_once(user_prompt))
    else:
        # Interactive REPL mode
        asyncio.run(interactive())
