import { Modal } from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { Check, X, Copy } from 'lucide-react';

export const PlatformStaffRequestsPage: React.FC = () => {
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<{
    name: string;
    activationUrl?: string;
    message: string;
  } | null>(null);

  const [reviewNotesModal, setReviewNotesModal] = useState<{
    id: string;
    action: 'approve' | 'reject';
    name: string;
  } | null>(null);
  const [notesInput, setNotesInput] = useState('');

  const loadRequests = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{ staff_requests: any[] }>('/api/platform/staff-requests/');
      setRequests(data.staff_requests || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRequests();
  }, []);

  const handleAction = async (requestId: string, action: 'approve' | 'reject', notes: string) => {
    try {
      setActingId(requestId);
      const res = await fetchApi<{
        status: string;
        activation_url?: string;
        message: string;
      }>(`/api/platform/staff-requests/${requestId}/${action}/`, {
        method: 'POST',
        body: JSON.stringify({ review_notes: notes }),
      });

      setReviewNotesModal(null);
      setNotesInput('');
      setActionResult({
        name: requests.find((r) => r.id === requestId)?.full_name || 'Staff User',
        activationUrl: res.activation_url,
        message: res.message,
      });

      await loadRequests();
    } catch (err: any) {
      alert(err?.error || `Could not ${action} request`);
    } finally {
      setActingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '85rem', margin: '0 auto' }}>
      {/* Header */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)" }}>Staff Access Requests</h1>
          <span style={{ fontSize: '0.75rem', background: 'var(--primary-light)', color: "var(--primary)", border: '1px solid var(--primary-border)', padding: '0.2rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
            Super Admin Inbox
          </span>
        </div>
        <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Review staff member requests submitted by client workspace administrators. Only Super Admin provisions global identities.
        </p>
      </div>

      {/* Requests Table */}
      <div className="table-container" style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '10px', overflow: 'hidden' }}>
        <table className="custom-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-card)" }}>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Candidate</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Target Workspace</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Role Requested</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Status</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Submitted By</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'right', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
                  Loading staff access requests...
                </td>
              </tr>
            ) : requests.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
                  No staff access requests submitted yet.
                </td>
              </tr>
            ) : (
              requests.map((r) => {
                const isPending = r.status === 'PENDING';
                const isApproved = r.status === 'APPROVED';

                return (
                  <tr key={r.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '0.9rem' }}>{r.full_name}</div>
                      <div style={{ fontSize: '0.75rem', color: "var(--primary)" }}>{r.email}</div>
                      {r.notes && (
                        <div style={{ fontSize: '0.725rem', color: "var(--text-muted)", marginTop: '0.2rem' }}>
                          Note: "{r.notes}"
                        </div>
                      )}
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: "var(--text-main)", fontSize: '0.85rem' }}>{r.tenant_name}</div>
                      <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>ID #{r.tenant_id}</div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span className="badge badge-gray" style={{ fontWeight: 700 }}>
                        {r.role_display}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span
                        className={`badge ${
                          isPending ? 'badge-amber' : isApproved ? 'badge-green' : 'badge-red'
                        }`}
                      >
                        {r.status_display}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontSize: '0.825rem', color: "var(--text-main)" }}>@{r.requested_by}</div>
                      <div style={{ fontSize: '0.725rem', color: "var(--text-muted)" }}>{new Date(r.created_at).toLocaleDateString()}</div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      {isPending ? (
                        <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                          <button
                            onClick={() => {
                              setReviewNotesModal({ id: r.id, action: 'approve', name: r.full_name });
                              setNotesInput('');
                            }}
                            disabled={actingId === r.id}
                            className="btn btn-sm btn-primary"
                            style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                          >
                            <Check size={13} /> Approve
                          </button>
                          <button
                            onClick={() => {
                              setReviewNotesModal({ id: r.id, action: 'reject', name: r.full_name });
                              setNotesInput('');
                            }}
                            disabled={actingId === r.id}
                            className="btn btn-sm btn-secondary"
                            style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.35rem 0.65rem', fontSize: '0.75rem', borderColor: '#ef4444', color: "var(--danger)" }}
                          >
                            <X size={13} /> Reject
                          </button>
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                          {isApproved ? 'Approved by @' + r.reviewed_by : 'Rejected'}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Action Notes Modal */}
      {reviewNotesModal && (
        <Modal title={reviewNotesModal.action === 'approve' ? 'Approve Staff Access' : 'Reject Staff Access'} onClose={() => setReviewNotesModal(null)} maxWidth="480px" zIndex={100} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '12px', padding: '2rem', width: '100%', maxWidth: '480px' }}>

            <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", marginBottom: '1.25rem' }}>
              Candidate: <strong>{reviewNotesModal.name}</strong>.
              {reviewNotesModal.action === 'approve'
                ? ' This will provision the user account into the client workspace and generate a single-use password activation link.'
                : ' This will reject the request and inform the client administrator.'}
            </p>

            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>
                Review Notes (Optional)
              </label>
              <textarea
                rows={3}
                value={notesInput}
                onChange={(e) => setNotesInput(e.target.value)}
                placeholder="e.g. Approved per 5-seat quota or reason for rejection..."
                style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)", fontSize: '0.85rem' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button onClick={() => setReviewNotesModal(null)} className="btn btn-secondary">
                Cancel
              </button>
              <button
                onClick={() => handleAction(reviewNotesModal.id, reviewNotesModal.action, notesInput)}
                className={`btn ${reviewNotesModal.action === 'approve' ? 'btn-primary' : 'btn-secondary'}`}
                style={{
                  fontWeight: 700,
                  ...(reviewNotesModal.action === 'reject' ? { borderColor: '#ef4444', color: "var(--danger)" } : {}),
                }}
              >
                {reviewNotesModal.action === 'approve' ? 'Confirm Approval & Provision' : 'Confirm Rejection'}
              </button>
            </div>

        </Modal>
      )}

      {/* Result Modal with Activation Link */}
      {actionResult && (
        <Modal title="Staff Access Provisioned" onClose={() => setActionResult(null)} maxWidth="540px" zIndex={110} style={{ background: "var(--bg-card)", border: '1px solid #10b981', borderRadius: '12px', padding: '2rem', width: '100%', maxWidth: '540px' }}>

            <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: "var(--primary-light)", color: "var(--primary)", display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem' }}>
              <Check size={24} />
            </div>

            <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", textAlign: 'center', marginBottom: '1.25rem' }}>
              {actionResult.message}
            </p>

            {actionResult.activationUrl && (
              <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', padding: '1rem', marginBottom: '1.5rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: "var(--primary)", marginBottom: '0.35rem' }}>
                  Activation Link (Deliver to {actionResult.name}):
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input
                    type="text"
                    readOnly
                    value={actionResult.activationUrl}
                    style={{ flex: 1, padding: '0.5rem', background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--primary)", fontSize: '0.8rem', fontFamily: 'monospace' }}
                  />
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(actionResult.activationUrl!);
                      alert('Activation URL copied to clipboard!');
                    }}
                    className="btn btn-secondary"
                    style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                  >
                    <Copy size={14} /> Copy
                  </button>
                </div>
              </div>
            )}

            <button onClick={() => setActionResult(null)} className="btn btn-primary" style={{ width: '100%', padding: '0.75rem', fontWeight: 700 }}>
              Close
            </button>

        </Modal>
      )}
    </div>
  );
};
