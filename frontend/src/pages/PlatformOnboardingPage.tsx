import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import {
  CheckCircle2,
  Clock,
  Mail,
  Plus,
  RefreshCw,
  Edit3,
  KeyRound,
} from 'lucide-react';

interface PlanOption {
  id: number;
  code: string;
  name: string;
  max_staff: number;
}

interface OnboardingRow {
  id: string;
  source: 'SELF_REGISTRATION' | 'SUPERADMIN_INVITE';
  source_display: string;
  business_name: string;
  owner_full_name: string;
  owner_email: string;
  desired_username: string;
  whatsapp_number: string;
  requested_plan: { id: number; code: string; name: string } | null;
  assigned_plan: { id: number; code: string; name: string } | null;
  registration_status: string;
  registration_status_display: string;
  email_verified: boolean;
  email_verified_at: string | null;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  approval_status_display: string;
  approved_by: string | null;
  approved_at: string | null;
  decision_reason: string;
  password_set: boolean;
  verification_expires_at: string | null;
  activation_expires_at: string | null;
  email_delivery: {
    purpose: string;
    status: string;
    status_label: string;
    attempts: number;
    last_error: string;
    updated_at: string;
  } | null;
  next_action: string;
  created_at: string;
}

interface OnboardingResponse {
  onboardings: OnboardingRow[];
  counts: {
    total: number;
    pending_approval: number;
    awaiting_email: number;
    awaiting_password: number;
    active: number;
    rejected: number;
  };
  plans: PlanOption[];
}

export const PlatformOnboardingPage: React.FC = () => {
  const [data, setData] = useState<OnboardingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [search, setSearch] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Invite modal state
  const [showInvite, setShowInvite] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    business_name: '',
    owner_full_name: '',
    owner_email: '',
    desired_username: '',
    whatsapp_number: '',
    plan_code: 'basic',
    notes: '',
  });

  // Approve modal state
  const [approveTarget, setApproveTarget] = useState<OnboardingRow | null>(null);
  const [approvePlan, setApprovePlan] = useState('');
  const [approveWa, setApproveWa] = useState('');
  const [approveReason, setApproveReason] = useState('');

  // Reject modal state
  const [rejectTarget, setRejectTarget] = useState<OnboardingRow | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // Edit email modal state
  const [editEmailTarget, setEditEmailTarget] = useState<OnboardingRow | null>(null);
  const [newEmail, setNewEmail] = useState('');

  const load = async (statusArg = filterStatus, queryArg = search) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusArg) params.set('status', statusArg);
      if (queryArg.trim()) params.set('q', queryArg.trim());
      const qs = params.toString() ? `?${params.toString()}` : '';
      const res = await fetchApi<OnboardingResponse>(`/api/platform/onboarding/${qs}`);
      setData(res);
      if (res.plans.length > 0 && !inviteForm.plan_code) {
        setInviteForm((prev) => ({ ...prev, plan_code: res.plans[0].code }));
      }
    } catch (err: any) {
      setError(err?.error || 'Failed to load client onboardings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filterStatus]);

  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);
    setBusyId('invite');
    try {
      const res = await fetchApi<{ message: string }>('/api/platform/onboarding/invite/', {
        method: 'POST',
        body: JSON.stringify(inviteForm),
      });
      setFeedback(res.message);
      setShowInvite(false);
      setInviteForm({
        business_name: '',
        owner_full_name: '',
        owner_email: '',
        desired_username: '',
        whatsapp_number: '',
        plan_code: data?.plans[0]?.code || 'basic',
        notes: '',
      });
      await load();
    } catch (err: any) {
      setError(err?.error || 'Could not invite client.');
    } finally {
      setBusyId(null);
    }
  };

  const handleApproveSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!approveTarget) return;
    setError(null);
    setFeedback(null);
    setBusyId(approveTarget.id);
    try {
      const res = await fetchApi<{ message: string }>(`/api/platform/onboarding/${approveTarget.id}/approve/`, {
        method: 'POST',
        body: JSON.stringify({
          plan_code: approvePlan,
          whatsapp_number: approveWa,
          decision_reason: approveReason,
        }),
      });
      setFeedback(res.message);
      setApproveTarget(null);
      await load();
    } catch (err: any) {
      setError(err?.error || 'Approval failed.');
    } finally {
      setBusyId(null);
    }
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectTarget) return;
    setError(null);
    setFeedback(null);
    setBusyId(rejectTarget.id);
    try {
      await fetchApi(`/api/platform/onboarding/${rejectTarget.id}/reject/`, {
        method: 'POST',
        body: JSON.stringify({ reason: rejectReason }),
      });
      setFeedback(`Rejected onboarding for ${rejectTarget.business_name}.`);
      setRejectTarget(null);
      setRejectReason('');
      await load();
    } catch (err: any) {
      setError(err?.error || 'Rejection failed.');
    } finally {
      setBusyId(null);
    }
  };

  const handleChangeEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editEmailTarget) return;
    setError(null);
    setFeedback(null);
    setBusyId(editEmailTarget.id);
    try {
      const res = await fetchApi<{ message: string }>(`/api/platform/onboarding/${editEmailTarget.id}/change-email/`, {
        method: 'POST',
        body: JSON.stringify({ new_email: newEmail }),
      });
      setFeedback(res.message);
      setEditEmailTarget(null);
      setNewEmail('');
      await load();
    } catch (err: any) {
      setError(err?.error || 'Could not update email.');
    } finally {
      setBusyId(null);
    }
  };

  const handleResend = async (row: OnboardingRow, kind: 'verification' | 'activation') => {
    setError(null);
    setFeedback(null);
    setBusyId(row.id);
    const path =
      kind === 'verification'
        ? `/api/platform/onboarding/${row.id}/resend-verification/`
        : `/api/platform/onboarding/${row.id}/resend-activation/`;
    try {
      const res = await fetchApi<{ message: string }>(path, { method: 'POST', body: '{}' });
      setFeedback(res.message);
      await load();
    } catch (err: any) {
      setError(err?.error || 'Could not resend email.');
    } finally {
      setBusyId(null);
    }
  };

  const counts = data?.counts;
  const plans = data?.plans || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>
            Client Onboarding &amp; Approvals
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Review public client registrations, invite workspaces, enforce email verification, and assign active plans.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.65rem' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => load()}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              setError(null);
              setShowInvite(true);
            }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
          >
            <Plus size={15} /> Create &amp; Invite Client
          </button>
        </div>
      </div>

      {feedback && (
        <div style={{ padding: '0.85rem 1rem', borderRadius: '0.5rem', background: 'rgba(17,183,109,0.1)', border: '1px solid rgba(17,183,109,0.35)', color: '#065f46', fontSize: '0.88rem' }}>
          {feedback}
        </div>
      )}
      {error && (
        <div style={{ padding: '0.85rem 1rem', borderRadius: '0.5rem', background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', color: '#b91c1c', fontSize: '0.88rem' }}>
          {error}
        </div>
      )}

      {/* Summary KPI Bar */}
      {counts && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(10.5rem, 1fr))', gap: '0.85rem' }}>
          {[
            { label: 'Total Records', val: counts.total, filter: '' },
            { label: 'Pending Approval', val: counts.pending_approval, filter: 'PENDING_APPROVAL' },
            { label: 'Awaiting Email', val: counts.awaiting_email, filter: 'AWAITING_EMAIL' },
            { label: 'Awaiting Password', val: counts.awaiting_password, filter: 'AWAITING_PASSWORD' },
            { label: 'Active Workspaces', val: counts.active, filter: 'APPROVED' },
            { label: 'Rejected', val: counts.rejected, filter: 'REJECTED' },
          ].map((c) => (
            <button
              key={c.label}
              type="button"
              onClick={() => setFilterStatus(c.filter)}
              className="card"
              style={{
                textAlign: 'left',
                cursor: 'pointer',
                border: filterStatus === c.filter ? '1.5px solid var(--primary)' : '1px solid var(--border)',
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>{c.label}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)', marginTop: '0.25rem' }}>{c.val}</div>
            </button>
          ))}
        </div>
      )}

      {/* Search */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(filterStatus, search);
        }}
        style={{ display: 'flex', gap: '0.65rem' }}
      >
        <input
          type="text"
          className="input-field"
          placeholder="Search business name, owner email, full name, or username..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-secondary">Search</button>
      </form>

      {/* Records List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        {loading && !data ? (
          <div className="card">Loading client onboardings...</div>
        ) : (data?.onboardings || []).length === 0 ? (
          <div className="card" style={{ color: 'var(--text-muted)' }}>No onboarding records match the selected filter.</div>
        ) : (
          (data?.onboardings || []).map((row) => (
            <div key={row.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>{row.business_name}</h2>
                    <span className="badge" style={{ fontSize: '0.7rem', background: '#f1f5f9', color: '#334155' }}>
                      {row.source_display}
                    </span>
                    <span
                      className="badge"
                      style={{
                        fontSize: '0.7rem',
                        background:
                          row.approval_status === 'APPROVED'
                            ? 'rgba(17,183,109,0.12)'
                            : row.approval_status === 'REJECTED'
                            ? 'rgba(239,68,68,0.12)'
                            : '#fef3c7',
                        color:
                          row.approval_status === 'APPROVED'
                            ? '#047857'
                            : row.approval_status === 'REJECTED'
                            ? '#b91c1c'
                            : '#92400e',
                      }}
                    >
                      {row.approval_status_display}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Owner: <strong>{row.owner_full_name}</strong> (@{row.desired_username}) &bull; {row.owner_email}
                    {row.whatsapp_number ? ` • WA: ${row.whatsapp_number}` : ''}
                  </div>
                </div>

                <div style={{ textAlign: 'right', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  <div>
                    Requested: <strong>{row.requested_plan?.name || 'Any'}</strong>
                    {row.assigned_plan ? (
                      <>
                        {' '}&rarr; Assigned: <strong style={{ color: '#047857' }}>{row.assigned_plan.name}</strong>
                      </>
                    ) : null}
                  </div>
                  <div style={{ marginTop: '0.2rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Next: {row.next_action}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.65rem', fontSize: '0.78rem', alignItems: 'center' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: row.email_verified ? '#047857' : '#b45309' }}>
                  {row.email_verified ? <CheckCircle2 size={14} /> : <Mail size={14} />}
                  Email: {row.email_verified ? 'Verified' : 'Unverified'}
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: row.password_set ? '#047857' : '#64748b' }}>
                  {row.password_set ? <CheckCircle2 size={14} /> : <KeyRound size={14} />}
                  Password: {row.password_set ? 'Set by Owner' : 'Not Set'}
                </span>
                {row.email_delivery && (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: row.email_delivery.status === 'FAILED' ? '#b91c1c' : '#475569' }}>
                    <Clock size={14} />
                    Mail ({row.email_delivery.purpose}): {row.email_delivery.status_label}
                    {row.email_delivery.last_error ? ` — ${row.email_delivery.last_error}` : ''}
                  </span>
                )}
              </div>

              {row.decision_reason && (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Decision note: {row.decision_reason}
                </div>
              )}

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', paddingTop: '0.35rem', borderTop: '1px solid var(--border)' }}>
                {row.approval_status === 'PENDING' && (
                  <>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busyId === row.id}
                      onClick={() => {
                        setApproveTarget(row);
                        setApprovePlan(row.requested_plan?.code || plans[0]?.code || 'basic');
                        setApproveWa(row.whatsapp_number || '');
                        setApproveReason('');
                      }}
                    >
                      Approve &amp; Assign Plan
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busyId === row.id}
                      onClick={() => {
                        setRejectTarget(row);
                        setRejectReason('');
                      }}
                      style={{ color: '#b91c1c' }}
                    >
                      Reject
                    </button>
                  </>
                )}

                {!row.email_verified && row.approval_status !== 'REJECTED' && (
                  <>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busyId === row.id}
                      onClick={() => handleResend(row, 'verification')}
                    >
                      Resend Verification Email
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busyId === row.id}
                      onClick={() => {
                        setEditEmailTarget(row);
                        setNewEmail(row.owner_email);
                      }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}
                    >
                      <Edit3 size={13} /> Change Owner Email
                    </button>
                  </>
                )}

                {row.email_verified && row.approval_status === 'APPROVED' && !row.password_set && (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busyId === row.id}
                    onClick={() => handleResend(row, 'activation')}
                  >
                    Resend Password Setup Link
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Invite Client Modal */}
      {showInvite && (
        <div role="dialog" aria-label="Create and Invite Client" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: '1rem' }}>
          <div className="card" style={{ maxWidth: '32rem', width: '100%' }}>
            <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.75rem' }}>Create &amp; Invite New Client</h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Approves workspace immediately and sends a 30-minute verification email first. The owner sets their own password after verifying their inbox.
            </p>
            <form onSubmit={handleInviteSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <input className="input-field" required placeholder="Business Name" value={inviteForm.business_name} onChange={(e) => setInviteForm({ ...inviteForm, business_name: e.target.value })} />
              <input className="input-field" required placeholder="Owner Full Name" value={inviteForm.owner_full_name} onChange={(e) => setInviteForm({ ...inviteForm, owner_full_name: e.target.value })} />
              <input className="input-field" required type="email" placeholder="Owner Email (deliverable mailbox)" value={inviteForm.owner_email} onChange={(e) => setInviteForm({ ...inviteForm, owner_email: e.target.value })} />
              <input className="input-field" required placeholder="Desired Username" value={inviteForm.desired_username} onChange={(e) => setInviteForm({ ...inviteForm, desired_username: e.target.value })} />
              <input className="input-field" placeholder="WhatsApp Number (Optional E.164 e.g. +919876543210)" value={inviteForm.whatsapp_number} onChange={(e) => setInviteForm({ ...inviteForm, whatsapp_number: e.target.value })} />
              <select className="input-field" value={inviteForm.plan_code} onChange={(e) => setInviteForm({ ...inviteForm, plan_code: e.target.value })}>
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>{p.name} ({p.max_staff} seats)</option>
                ))}
              </select>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowInvite(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={busyId === 'invite'}>
                  {busyId === 'invite' ? 'Inviting...' : 'Send Invite & Verification'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Approve Modal */}
      {approveTarget && (
        <div role="dialog" aria-label="Approve Client Registration" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: '1rem' }}>
          <div className="card" style={{ maxWidth: '28rem', width: '100%' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.5rem' }}>Approve {approveTarget.business_name}</h2>
            {!approveTarget.email_verified && (
              <div style={{ padding: '0.65rem', background: '#fef3c7', borderRadius: '0.4rem', fontSize: '0.8rem', color: '#92400e', marginBottom: '0.75rem' }}>
                Owner email is not yet verified. Approval provisions the workspace plan, while password setup remains gated until email verification completes.
              </div>
            )}
            <form onSubmit={handleApproveSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Assigned Subscription Plan</label>
              <select className="input-field" value={approvePlan} onChange={(e) => setApprovePlan(e.target.value)} required>
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>{p.name} ({p.max_staff} staff)</option>
                ))}
              </select>
              <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>WhatsApp Number (Optional E.164)</label>
              <input className="input-field" value={approveWa} onChange={(e) => setApproveWa(e.target.value)} placeholder="+919876543210" />
              <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Decision Notes (Optional)</label>
              <input className="input-field" value={approveReason} onChange={(e) => setApproveReason(e.target.value)} placeholder="Approved on Basic/Growth tier..." />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button type="button" className="btn-secondary" onClick={() => setApproveTarget(null)}>Cancel</button>
                <button type="submit" className="btn-primary">Confirm Approval</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {rejectTarget && (
        <div role="dialog" aria-label="Reject Registration" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: '1rem' }}>
          <div className="card" style={{ maxWidth: '28rem', width: '100%' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.5rem' }}>Reject {rejectTarget.business_name}</h2>
            <form onSubmit={handleRejectSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <textarea className="input-field" required rows={3} placeholder="Reason for rejection (audited)..." value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button type="button" className="btn-secondary" onClick={() => setRejectTarget(null)}>Cancel</button>
                <button type="submit" className="btn-primary" style={{ background: '#dc2626' }}>Confirm Rejection</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Change Email Modal */}
      {editEmailTarget && (
        <div role="dialog" aria-label="Change Owner Email" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: '1rem' }}>
          <div className="card" style={{ maxWidth: '28rem', width: '100%' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.5rem' }}>Update Email for {editEmailTarget.business_name}</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Invalidates open verification links and dispatches a fresh 30-minute verification link to the new address.
            </p>
            <form onSubmit={handleChangeEmailSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <input className="input-field" type="email" required value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button type="button" className="btn-secondary" onClick={() => setEditEmailTarget(null)}>Cancel</button>
                <button type="submit" className="btn-primary">Update &amp; Resend</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
