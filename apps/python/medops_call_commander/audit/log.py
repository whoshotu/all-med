import logging
from dataclasses import asdict
from datetime import datetime
from typing import List

from ..core.models import AuditEntry

logger = logging.getLogger(__name__)


class AuditLog:
    """
    Immutable append-only audit log.
    Stage 6 will add persistent storage (SQLite or Postgres).
    This stub satisfies HITLGate and all gate dependencies now.

    Rules:
    - append() only — no update, no delete
    - Never stores PHI: no phone numbers, names, balances, transcript content
    - Every CallPlan state transition must be logged before the state changes
    """

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        """Write an audit entry. Raises if PHI fields are detected."""
        self._check_no_phi(entry)
        self._entries.append(entry)
        logger.info(
            "AUDIT plan_id=%s action=%s admin=%s ts=%s",
            entry.plan_id,
            entry.action,
            entry.admin_id or "system",
            entry.timestamp.isoformat(),
        )

    def get(self, plan_id: str) -> List[AuditEntry]:
        """Return all entries for a given plan_id."""
        return [e for e in self._entries if e.plan_id == plan_id]

    def all(self) -> List[AuditEntry]:
        """Return full log. Read-only — returns a copy."""
        return list(self._entries)

    @staticmethod
    def _check_no_phi(entry: AuditEntry) -> None:
        """
        Lightweight guard: rejects entries whose reason field
        contains patterns that look like phone numbers or emails.
        Full PHI scanning handled at the adapter layer.
        """
        suspicious = ["+1", "@", "dob:", "ssn:", "balance:"]
        reason = (entry.reason or "").lower()
        for pattern in suspicious:
            if pattern in reason:
                raise ValueError(
                    f"AuditEntry.reason appears to contain PHI (matched '{pattern}'). "
                    f"Strip PHI before logging."
                )
