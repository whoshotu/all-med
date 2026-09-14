import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, ShieldCheck, Activity, PhoneCall, FileText, X, Check, Copy, AlertCircle, Clock } from 'lucide-react';
import { useIdleTimeout } from '../hooks/useIdleTimeout';

export default function Dashboard() {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [patientPhone, setPatientPhone] = useState('+1');
  const [patientId, setPatientId] = useState('PAT-TEST-1');
  const [triggering, setTriggering] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [copied, setCopied] = useState(false);
  const navigate = useNavigate();

  // 3 minute Security timeout
  const isIdle = useIdleTimeout(180000);

  const fetchPlans = async () => {
    const token = sessionStorage.getItem('medops_jwt');
    if (!token) {
      navigate('/login');
      return;
    }

    try {
      const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
      const response = await fetch(`${API_BASE}/api/plans`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.status === 401) {
        sessionStorage.removeItem('medops_jwt');
        navigate('/login');
        return;
      }

      if (!response.ok) throw new Error('Failed to fetch plans');

      const data = await response.json();
      setPlans(data.plans || []);
      setError(null);
    } catch (err) {
      // TypeError means the request never reached the server (network down,
      // CORS, etc.). The call plan state on the server is unchanged.
      if (err instanceof TypeError) {
        setError('Unable to reach server — call state unchanged. Check your connection.');
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchPlans();
    const interval = setInterval(fetchPlans, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    sessionStorage.removeItem('medops_jwt');
    navigate('/login');
  };

  const handleTrigger = async (eventType) => {
    const token = sessionStorage.getItem('medops_jwt');
    const cleanPhone = patientPhone.trim();
    if (!cleanPhone || cleanPhone === '+1' || cleanPhone.length < 10) {
      alert('Please enter a full phone number in E.164 format (e.g. +1XXXXXXXXXX)');
      return;
    }

    setTriggering(true);
    try {
      const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
      const response = await fetch(`${API_BASE}/api/events/trigger`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          event_type: eventType,
          patient_id: patientId.trim() || 'PAT-TEST-1',
          patient_phone: cleanPhone,
          source_system: "opendental"
        })
      });
      if (!response.ok) {
         if (response.status === 401) {
            navigate('/login');
            return;
         }
         const errData = await response.json().catch(() => ({}));
         throw new Error(errData.detail || 'Failed to trigger event');
      }
      fetchPlans();
    } catch (err) {
      alert(err.message);
    } finally {
      setTriggering(false);
    }
  };

  const handleAction = async (planId, action) => {
    const token = sessionStorage.getItem('medops_jwt');
    try {
      const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
      
      // Step 1: Execute primary action
      let response = await fetch(`${API_BASE}/api/plans/${planId}/${action}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({})
      });
      
      if (!response.ok) {
        if (response.status === 401) {
          navigate('/login');
          return;
        }
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to ${action} plan (${response.status})`);
      }
      
      // Step 2: Auto-dispatch immediately if we just approved
      if (action === 'approve') {
        let dispatchResponse = await fetch(`${API_BASE}/api/plans/${planId}/dispatch`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        });
        if (!dispatchResponse.ok) {
          if (dispatchResponse.status === 401) {
            navigate('/login');
            return;
          }
          const dispatchErrData = await dispatchResponse.json().catch(() => ({}));
          throw new Error(dispatchErrData.detail || `Failed to dispatch approved plan (${dispatchResponse.status})`);
        }
      }
      
      fetchPlans();
    } catch (err) {
      alert(err.message);
    }
  };

  const copyEhrNote = (plan) => {
    const summary = plan.result?.structured?.call_summary || plan.result?.summary || 'Call dispatched and completed.';
    const outcome = plan.result?.outcome || plan.state;
    const note = `[MEDOPS CALL REPORT]\nPatient ID: ${plan.patient_id}\nAgent: ${plan.agent}\nStatus: ${outcome}\nCompleted At: ${plan.result?.completed_at || plan.dispatched_at || new Date().toISOString()}\n\nSummary & Transcript Notes:\n${summary}\n\nTranscript Ref: ${plan.result?.transcript_ref || plan.result_ref || 'N/A'}`;
    
    navigator.clipboard.writeText(note);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  if (isIdle) {
    return (
      <div className="login-container idle-blur">
        <div className="login-card card">
           <h3>Session Expired</h3>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-title">
          <Activity size={24} />
          CALL-E Commander
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <div className="hipaa-badge">
            <ShieldCheck size={14} /> SECURED
          </div>
          <button onClick={handleLogout} className="btn btn-outline" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <LogOut size={16} /> Logout
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="card">
          <h2 className="card-title">Trigger Manual Events</h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" htmlFor="patient_phone">Patient Phone (E.164 format)</label>
              <input
                id="patient_phone"
                type="tel"
                className="form-input"
                placeholder="+1XXXXXXXXXX"
                value={patientPhone}
                onChange={(e) => setPatientPhone(e.target.value)}
                required
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" htmlFor="patient_id">Patient ID</label>
              <input
                id="patient_id"
                type="text"
                className="form-input"
                placeholder="PAT-TEST-1"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={() => handleTrigger('missed_appointment')} disabled={triggering}>
              Missed Appointment
            </button>
            <button className="btn btn-primary" onClick={() => handleTrigger('invoice_60_days')} disabled={triggering}>
              Past Due
            </button>
            <button className="btn btn-primary" onClick={() => handleTrigger('loan_inquiry_submitted')} disabled={triggering}>
              Lending Follow-Up
            </button>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            Active Call Plans
            <span style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--color-text-muted)' }}>
              Auto-refreshing every 5s
            </span>
          </h2>
          
          {loading ? (
            <p style={{ color: 'var(--color-text-muted)' }}>Loading plans...</p>
          ) : error ? (
            <p style={{ color: 'var(--color-danger-red)' }}>{error}</p>
          ) : plans.length === 0 ? (
            <p style={{ color: 'var(--color-text-muted)' }}>No active call plans in the queue.</p>
          ) : (
            <div className="table-wrapper">
              <table className="clinical-table">
                <thead>
                  <tr>
                    <th>Plan ID</th>
                    <th>Agent</th>
                    <th>Patient ID</th>
                    <th>Consent</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map((plan) => (
                    <tr key={plan.plan_id}>
                      <td style={{ fontFamily: 'monospace' }}>{plan.plan_id.substring(0, 8)}...</td>
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <PhoneCall size={14} /> {plan.agent}
                        </span>
                      </td>
                      <td>{plan.patient_id}</td>
                      <td>
                        <span className={`status-badge ${plan.consent_granted ? 'status-completed' : 'status-pending'}`}>
                          {plan.consent_granted ? 'Granted' : 'Denied/Pending'}
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge ${plan.state === 'completed' ? 'status-completed' : plan.state === 'FAILED' ? 'status-pending' : 'status-pending'}`}>
                          {plan.state.toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          {plan.state === 'PENDING_APPROVAL' ? (
                            <>
                              <button className="btn btn-primary" onClick={() => handleAction(plan.plan_id, 'approve')} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>Approve</button>
                              <button className="btn btn-outline" onClick={() => handleAction(plan.plan_id, 'dismiss')} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', borderColor: 'var(--color-danger-red)', color: 'var(--color-danger-red)' }}>Dismiss</button>
                            </>
                          ) : null}
                          <button 
                            className="btn btn-outline" 
                            onClick={() => setSelectedPlan(plan)}
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                          >
                            <FileText size={12} /> {plan.result ? 'View Transcript & Notes' : 'Details'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* Clinical Review & Transcript Modal */}
      {selectedPlan && (
        <div className="modal-overlay" onClick={() => setSelectedPlan(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileText size={18} color="var(--color-primary-blue)" />
                  Clinical Call Review: Patient {selectedPlan.patient_id}
                </h3>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                  Plan ID: {selectedPlan.plan_id} • Agent: {selectedPlan.agent}
                </span>
              </div>
              <button 
                onClick={() => setSelectedPlan(null)} 
                className="btn btn-outline" 
                style={{ padding: '0.25rem', borderRadius: '50%', border: 'none' }}
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              {/* Call Outcome Status Box */}
              <div className="info-box">
                <div className="info-box-title">
                  <Activity size={14} /> Call Outcome Status
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <span className={`status-badge ${selectedPlan.state === 'completed' ? 'status-completed' : 'status-pending'}`}>
                    STATE: {selectedPlan.state.toUpperCase()}
                  </span>
                  {selectedPlan.result?.outcome && (
                    <span className="status-badge status-completed">
                      CALL RESULT: {selectedPlan.result.outcome.toUpperCase()}
                    </span>
                  )}
                  {selectedPlan.result?.completed_at && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Clock size={12} /> {new Date(selectedPlan.result.completed_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Conversation Summary & Notes Box */}
              <div className="info-box" style={{ backgroundColor: '#f8fafc', borderColor: '#cbd5e1' }}>
                <div className="info-box-title" style={{ color: 'var(--color-primary-blue)' }}>
                  <FileText size={14} /> Conversation Summary & Transcript Notes
                </div>
                <div className="info-box-content">
                  {selectedPlan.result?.structured?.call_summary || 
                   selectedPlan.result?.summary || 
                   (selectedPlan.state === 'completed' 
                      ? 'Call completed successfully. Patient engaged with automated domain agent.' 
                      : selectedPlan.state === 'PENDING_APPROVAL' 
                      ? 'Pending clinical admin approval prior to outbound dispatch.' 
                      : 'Call dispatched or pending final outcome resolution.')}
                </div>

                {/* Structured Clinical Key-Values */}
                {selectedPlan.result?.structured && Object.keys(selectedPlan.result.structured).length > 0 && (
                  <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                      STRUCTURED CLINICAL OUTCOMES:
                    </div>
                    <div className="badge-grid">
                      {Object.entries(selectedPlan.result.structured).map(([key, val]) => (
                        key !== 'call_summary' && (
                          <div key={key} style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                            <strong>{key.replace(/_/g, ' ')}:</strong> {String(val)}
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Call Task Script */}
              <div className="info-box">
                <div className="info-box-title">
                  <PhoneCall size={14} /> Dispatched Task Script
                </div>
                <div className="info-box-content" style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                  {selectedPlan.script}
                </div>
              </div>

              {/* Reference ID & Compliance Note */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                <span>Transcript Ref: <code>{selectedPlan.result?.transcript_ref || selectedPlan.result_ref || 'N/A'}</code></span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <ShieldCheck size={12} color="var(--color-success-green)" /> HIPAA Zero-Retention Enforced
                </span>
              </div>
            </div>

            <div className="modal-footer">
              <button 
                className="btn btn-outline" 
                onClick={() => copyEhrNote(selectedPlan)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}
              >
                {copied ? <Check size={14} color="var(--color-success-green)" /> : <Copy size={14} />}
                {copied ? 'Copied Note!' : 'Copy EHR Chart Note'}
              </button>
              <button className="btn btn-primary" onClick={() => setSelectedPlan(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
