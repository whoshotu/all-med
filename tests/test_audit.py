import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone
from apps.python.medops_call_commander.audit.log import AuditLog
from apps.python.medops_call_commander.core.models import AuditEntry

@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    os.remove(path)


def test_audit_log_persistence(temp_db_path):
    """Test that data is persistently written to SQLite and can be re-loaded."""
    # First instance creates and writes
    log_a = AuditLog(db_path=temp_db_path)
    entry = AuditEntry(
        plan_id="plan-123",
        action="CREATED",
        agent_type="appointments",
        admin_id="system",
        reason="Test reason"
    )
    log_a.append(entry)

    # Second instance loads from same file
    log_b = AuditLog(db_path=temp_db_path)
    entries = log_b.get("plan-123")
    
    assert len(entries) == 1
    assert entries[0].plan_id == "plan-123"
    assert entries[0].action == "CREATED"
    assert entries[0].agent_type == "appointments"
    assert entries[0].reason == "Test reason"


def test_audit_log_hipaa_file_permissions(temp_db_path):
    """Test that the DB file is locked down to 0o600 permissions."""
    if os.name != 'posix':
        pytest.skip("File permission test only valid on POSIX systems")
        
    log = AuditLog(db_path=temp_db_path)
    
    # Check permissions
    st = os.stat(temp_db_path)
    # The last 3 octal digits represent user/group/other permissions
    permissions = oct(st.st_mode)[-3:]
    assert permissions == '600', f"Expected file permissions to be 600, got {permissions}"


def test_audit_log_phi_rejection(temp_db_path):
    """Test that attempts to log PHI are rejected."""
    log = AuditLog(db_path=temp_db_path)
    
    phi_entry = AuditEntry(
        plan_id="plan-456",
        action="CREATED",
        reason="Patient dob: 01/01/1990"
    )
    
    with pytest.raises(ValueError, match="appears to contain PHI"):
        log.append(phi_entry)
