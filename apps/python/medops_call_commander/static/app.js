document.addEventListener('DOMContentLoaded', () => {
  fetchPlans();
  fetchAuditLog();

  // Poll state every 4 seconds for live updates
  setInterval(() => {
    fetchPlans();
    fetchAuditLog();
  }, 4000);

  const form = document.getElementById('custom-event-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const event_type = document.getElementById('event_type').value;
    const patient_id = document.getElementById('patient_id').value;
    const patient_phone = document.getElementById('patient_phone').value;
    const source_system = document.getElementById('source_system').value;

    await triggerEvent({
      event_type,
      patient_id,
      patient_phone,
      source_system,
      priority: event_type.includes('90') ? 'urgent' : 'routine'
    });
  });
});

async function quickTrigger(eventType, patientId, agentType, sourceSystem) {
  await triggerEvent({
    event_type: eventType,
    patient_id: patientId,
    patient_phone: '+14155550199',
    priority: eventType.includes('90') ? 'urgent' : 'routine',
    source_system: sourceSystem.toLowerCase().replace(' ', '_')
  });
}

async function triggerEvent(payload) {
  try {
    const res = await fetch('/api/events/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      alert(`⚠️ Action Blocked: ${data.detail || 'Failed to trigger event'}`);
    } else {
      fetchPlans();
      fetchAuditLog();
    }
  } catch (err) {
    alert(`Server Error: ${err.message}`);
  }
}

async function fetchPlans() {
  try {
    const res = await fetch('/api/plans');
    const plans = await res.json();
    renderPlans(plans);
  } catch (err) {
    console.error('Failed to fetch plans', err);
  }
}

async function fetchAuditLog() {
  try {
    const res = await fetch('/api/audit');
    const logs = await res.json();
    renderAuditLog(logs);
  } catch (err) {
    console.error('Failed to fetch audit log', err);
  }
}

function renderPlans(plans) {
  const container = document.getElementById('plans-list');
  if (!plans || plans.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No active call plans in queue.</p>
        <span>Trigger an event above to start the multi-agent pipeline.</span>
      </div>`;
    return;
  }

  container.innerHTML = plans.map(plan => {
    const isPending = plan.state === 'PENDING_APPROVAL';
    const isApproved = plan.state === 'APPROVED';
    const isCompleted = plan.state === 'COMPLETED';

    return `
      <div class="plan-card ${plan.state.toLowerCase()}">
        <div class="plan-card-header">
          <div class="plan-title">
            <span class="agent-chip ${plan.agent}">${plan.agent.toUpperCase()} AGENT</span>
            <span>Plan #${plan.plan_id.slice(0, 8)}</span>
          </div>
          <span class="plan-state-badge ${plan.state}">${plan.state}</span>
        </div>

        <div class="plan-details">
          <div class="detail-item">
            <span class="detail-label">Patient ID</span>
            <span class="detail-val">${plan.patient_id}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Phone Masked</span>
            <span class="detail-val">${plan.phone_masked}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Trigger Event</span>
            <span class="detail-val">${plan.source_event}</span>
          </div>
        </div>

        <div class="script-box">
          "${plan.script}"
        </div>

        ${plan.result_ref ? `
          <div class="call-result-box">
            <div class="result-header">✓ CALL-E Execution Ref: ${plan.result_ref}</div>
            <p>E.164 phone zeroed post-dispatch (PHI scrubbed: ${plan.is_phi_scrubbed ? 'Yes' : 'No'}).</p>
          </div>
        ` : ''}

        <div class="plan-actions">
          ${isPending ? `
            <button class="btn btn-sm btn-ghost" onclick="openEditModal('${plan.plan_id}', \`${escapeHtml(plan.script)}\`)">Edit Script</button>
            <button class="btn btn-sm btn-danger" onclick="dismissPlan('${plan.plan_id}')">Dismiss</button>
            <button class="btn btn-sm btn-primary" onclick="approvePlan('${plan.plan_id}')">Approve (HITL)</button>
          ` : ''}

          ${isApproved ? `
            <button class="btn btn-sm btn-primary" onclick="dispatchPlan('${plan.plan_id}')">
              <span>Execute CALL-E Call</span>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function renderAuditLog(logs) {
  const tbody = document.getElementById('audit-log-body');
  if (!logs || logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Audit log empty</td></tr>';
    return;
  }

  tbody.innerHTML = logs.reverse().slice(0, 15).map(entry => `
    <tr>
      <td>${new Date(entry.timestamp).toLocaleTimeString()}</td>
      <td><strong>${entry.action}</strong></td>
      <td><code>${entry.plan_id ? entry.plan_id.slice(0, 8) : 'N/A'}</code></td>
      <td>${entry.agent_type || 'system'}</td>
      <td>${entry.admin_id || 'system'}</td>
      <td>${entry.reason || ''}</td>
    </tr>
  `).join('');
}

async function approvePlan(planId, customScript = null) {
  try {
    const res = await fetch(`/api/plans/${planId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script: customScript, admin_id: 'admin_web_dashboard' })
    });
    if (res.ok) {
      fetchPlans();
      fetchAuditLog();
    } else {
      const data = await res.json();
      alert(`Error approving plan: ${data.detail}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function dispatchPlan(planId) {
  try {
    const res = await fetch(`/api/plans/${planId}/dispatch`, {
      method: 'POST'
    });
    const data = await res.json();
    if (res.ok) {
      fetchPlans();
      fetchAuditLog();
    } else {
      alert(`Dispatch Error: ${data.detail}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function dismissPlan(planId) {
  try {
    await fetch(`/api/plans/${planId}/dismiss`, { method: 'POST' });
    fetchPlans();
    fetchAuditLog();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

function openEditModal(planId, currentScript) {
  document.getElementById('modal-plan-id').value = planId;
  document.getElementById('modal-script-text').value = currentScript;
  document.getElementById('edit-modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('edit-modal').classList.add('hidden');
}

function confirmApproveWithScript() {
  const planId = document.getElementById('modal-plan-id').value;
  const scriptText = document.getElementById('modal-script-text').value;
  closeModal();
  approvePlan(planId, scriptText);
}

function escapeHtml(str) {
  return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
