import Modal from '../components/Modal';
import { PasswordInput } from '../components/PasswordInput';
import React, { useEffect, useState } from 'react';
import { TeamMember, Invitation } from '../types';
import { fetchApi } from '../api/client';
import { UserCheck, Plus, Shield, KeyRound, Edit3, Power } from 'lucide-react';

interface ManagedTeamMember extends TeamMember {
  first_name?: string;
  last_name?: string;
  internal_identifier?: string;
  is_synthetic_identifier?: boolean;
  recovery_email?: string;
  recovery_email_verified?: boolean;
  email_verified?: boolean;
  skip_mailbox_gate?: boolean;
  has_usable_password?: boolean;
  is_shared_account?: boolean;
  can_manage?: boolean;
}

interface StaffAccessRequestItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  role_display: string;
  status: string;
  status_display: string;
  notes: string;
  review_notes?: string;
  created_at: string;
}

interface TeamAuditEvent {
  id: number;
  action: string;
  summary: string;
  actor: string;
  created_at: string;
}

function generateStrongPassword(): string {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const lower = 'abcdefghijkmnopqrstuvwxyz';
  const digits = '23456789';
  const symbols = '!@#$%^&*';
  const all = upper + lower + digits + symbols;
  const pick = (pool: string) => pool[Math.floor(Math.random() * pool.length)];
  const chars = [pick(upper), pick(lower), pick(digits), pick(symbols)];
  for (let i = 0; i < 10; i++) chars.push(pick(all));
  return chars.sort(() => Math.random() - 0.5).join('');
}

export const TeamPage: React.FC = () => {
  const [members, setMembers] = useState<ManagedTeamMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [staffRequests, setStaffRequests] = useState<StaffAccessRequestItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<TeamAuditEvent[]>([]);
  const [actorRole, setActorRole] = useState<string>('');
  const [seatSummary, setSeatSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Add Staff Direct Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    username: '',
    full_name: '',
    role: 'STAFF',
    contact_email: '',
    synthetic_identifier: '',
    password: '',
  });
  const [addingStaff, setAddingStaff] = useState(false);

  // Edit Staff Modal
  const [editTarget, setEditTarget] = useState<ManagedTeamMember | null>(null);
  const [editForm, setEditForm] = useState({
    username: '',
    full_name: '',
    role: 'STAFF',
    contact_email: '',
    is_active: true,
  });
  const [savingEdit, setSavingEdit] = useState(false);

  // Reset Password Modal
  const [resetTarget, setResetTarget] = useState<ManagedTeamMember | null>(null);
  const [resetPasswords, setResetPasswords] = useState({ new_password: '', confirm_password: '' });
  const [resettingPw, setResettingPw] = useState(false);

  // Request Staff Access Modal (legacy Super Admin escalation request preserved)
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [reqFullName, setReqFullName] = useState('');
  const [reqEmail, setReqEmail] = useState('');
  const [reqRole, setReqRole] = useState('STAFF');
  const [reqNotes, setReqNotes] = useState('');
  const [submittingReq, setSubmittingReq] = useState(false);
  const [reqError, setReqError] = useState<string | null>(null);

  // Remove Member & Reassign Work Modal
  const [memberToRemove, setMemberToRemove] = useState<ManagedTeamMember | null>(null);
  const [showReassignModal, setShowReassignModal] = useState(false);
  const [reassignInfo, setReassignInfo] = useState<{ open_deals: number; open_tasks: number } | null>(null);
  const [reassignToUserId, setReassignToUserId] = useState<string>('');
  const [reassigning, setReassigning] = useState(false);

  const loadTeam = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{
        members: ManagedTeamMember[];
        invitations: Invitation[];
        staff_requests: StaffAccessRequestItem[];
        audit_logs?: TeamAuditEvent[];
        actor_role?: string;
        seat_summary: any;
      }>('/api/team/');
      setMembers(data.members || []);
      setInvitations(data.invitations || []);
      setStaffRequests(data.staff_requests || []);
      setAuditLogs(data.audit_logs || []);
      setActorRole(data.actor_role || '');
      setSeatSummary(data.seat_summary);
    } catch (err: any) {
      setActionError(err?.error || 'Could not load team directory.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTeam();
  }, []);

  const canManageTeam = actorRole === 'OWNER' || actorRole === 'ADMIN' || actorRole === 'SUPERUSER';

  const handleAddStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    setSuccessMsg(null);
    setAddingStaff(true);
    try {
      const res = await fetchApi<{ message: string }>('/api/team/members/', {
        method: 'POST',
        body: JSON.stringify(addForm),
      });
      setShowAddModal(false);
      setAddForm({ username: '', full_name: '', role: 'STAFF', contact_email: '', synthetic_identifier: '', password: '' });
      setSuccessMsg(res.message);
      await loadTeam();
    } catch (err: any) {
      setActionError(err?.error || 'Failed to create staff account.');
    } finally {
      setAddingStaff(false);
    }
  };

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTarget) return;
    setActionError(null);
    setSuccessMsg(null);
    setSavingEdit(true);
    try {
      const payload = editTarget.is_shared_account
        ? { role: editForm.role, is_active: editForm.is_active }
        : editForm;
      const res = await fetchApi<{ message: string }>(`/api/team/members/${editTarget.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      setEditTarget(null);
      setSuccessMsg(res.message);
      await loadTeam();
    } catch (err: any) {
      setActionError(err?.error || 'Failed to update team member.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleToggleActive = async (m: ManagedTeamMember) => {
    setActionError(null);
    setSuccessMsg(null);
    try {
      const res = await fetchApi<{ message: string }>(`/api/team/members/${m.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !m.is_active }),
      });
      setSuccessMsg(res.message);
      await loadTeam();
    } catch (err: any) {
      setActionError(err?.error || 'Failed to toggle active status.');
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetTarget) return;
    setActionError(null);
    setSuccessMsg(null);
    setResettingPw(true);
    try {
      const res = await fetchApi<{ message: string }>(`/api/team/members/${resetTarget.id}/reset-password/`, {
        method: 'POST',
        body: JSON.stringify(resetPasswords),
      });
      setResetTarget(null);
      setResetPasswords({ new_password: '', confirm_password: '' });
      setSuccessMsg(res.message);
      await loadTeam();
    } catch (err: any) {
      setActionError(err?.error || 'Failed to reset password.');
    } finally {
      setResettingPw(false);
    }
  };

  const handleRequestStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingReq(true);
    setReqError(null);
    setSuccessMsg(null);
    try {
      const res = await fetchApi<{ message: string }>('/api/team/request-staff/', {
        method: 'POST',
        body: JSON.stringify({
          full_name: reqFullName,
          email: reqEmail,
          role: reqRole,
          notes: reqNotes,
        }),
      });
      setSuccessMsg(res.message);
      setShowRequestModal(false);
      setReqFullName('');
      setReqEmail('');
      setReqNotes('');
      await loadTeam();
    } catch (err: any) {
      setReqError(err?.error || 'Failed to submit staff request.');
    } finally {
      setSubmittingReq(false);
    }
  };

  const handleInitiateRemove = async (member: ManagedTeamMember) => {
    setActionError(null);
    try {
      await fetchApi(`/api/team/members/${member.id}/remove/`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      await loadTeam();
    } catch (err: any) {
      if (err?.requires_reassign) {
        setMemberToRemove(member);
        setReassignInfo({
          open_deals: err.open_deals || 0,
          open_tasks: err.open_tasks || 0,
        });
        const eligible = members.filter((m) => m.id !== member.id && m.is_active);
        if (eligible.length > 0) setReassignToUserId(String(eligible[0].user_id));
        setShowReassignModal(true);
      } else {
        setActionError(err?.error || 'Failed to remove team member.');
      }
    }
  };

  const handleReassignAndRemove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memberToRemove || !reassignToUserId) return;
    setReassigning(true);
    setActionError(null);
    try {
      await fetchApi('/api/team/reassign-work/', {
        method: 'POST',
        body: JSON.stringify({
          from_user_id: memberToRemove.user_id,
          to_user_id: reassignToUserId,
        }),
      });
      await fetchApi(`/api/team/members/${memberToRemove.id}/remove/`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setShowReassignModal(false);
      setMemberToRemove(null);
      await loadTeam();
    } catch (err: any) {
      setActionError(err?.error || 'Reassignment failed.');
    } finally {
      setReassigning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>Team Management &amp; Staff Administration</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Create workspace staff accounts directly, manage roles, reset staff passwords securely, and review access audits.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
          {canManageTeam && (
            <button
              type="button"
              onClick={() => {
                setActionError(null);
                setShowAddModal(true);
              }}
              disabled={seatSummary && !seatSummary.can_add}
              className="btn btn-primary"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Plus size={16} /> Add Staff Member
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setReqError(null);
              setShowRequestModal(true);
            }}
            disabled={seatSummary && !seatSummary.can_add}
            className="btn btn-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
          >
            <UserCheck size={15} /> Request Staff Access
          </button>
        </div>
      </div>

      {successMsg && (
        <div role="status" style={{ padding: '0.75rem 1rem', backgroundColor: 'rgba(17, 183, 109, 0.12)', border: '1px solid rgba(17, 183, 109, 0.35)', borderRadius: '0.5rem', color: '#047857', fontSize: '0.85rem' }}>
          {successMsg}
        </div>
      )}

      {actionError && (
        <div role="alert" style={{ padding: '0.75rem 1rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: 'var(--danger)', fontSize: '0.85rem' }}>
          {actionError}
        </div>
      )}

      {seatSummary && (
        <div className="card" style={{ padding: '1rem 1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Subscription Seat Allocation: </span>
            <strong style={{ color: 'var(--text-main)' }}>{seatSummary.used}</strong> / {seatSummary.allocated} seats occupied
          </div>
          <span className={`badge ${seatSummary.can_add ? 'badge-green' : 'badge-amber'}`}>
            {seatSummary.can_add ? 'Seats Available' : 'Seat Limit Reached'}
          </span>
        </div>
      )}

      {/* 1. Team Members Table */}
      <div>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.75rem' }}>Workspace Team Members</h2>
        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>Member</th>
                <th>Contact / Identifier</th>
                <th>Role</th>
                <th>Status</th>
                <th>Joined Date</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && members.length === 0 ? (
                <tr><td colSpan={6} style={{ color: 'var(--text-muted)' }}>Loading team...</td></tr>
              ) : members.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{m.full_name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      @{m.username}
                      {m.is_synthetic_identifier && m.internal_identifier ? ` • ID: ${m.internal_identifier}` : ''}
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.84rem' }}>{m.email || (m.internal_identifier ? 'Internal staff account' : '—')}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {m.recovery_email_verified ? `Recovery verified: ${m.recovery_email}` : m.skip_mailbox_gate ? 'Staff mailbox gate exempt' : m.email_verified ? 'Email verified' : 'Unverified email'}
                      {m.is_shared_account ? ' • Multi-workspace identity' : ''}
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${m.role === 'OWNER' ? 'badge-green' : m.role === 'ADMIN' ? 'badge-blue' : 'badge-gray'}`}>
                      {m.role_display}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${m.is_active ? 'badge-green' : 'badge-red'}`}>
                      {m.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                    {new Date(m.joined_at).toLocaleDateString()}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '0.35rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      {m.can_manage && (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              setActionError(null);
                              setEditTarget(m);
                              setEditForm({
                                username: m.username,
                                full_name: m.full_name,
                                role: m.role,
                                contact_email: m.email || '',
                                is_active: m.is_active,
                              });
                            }}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                          >
                            <Edit3 size={13} /> Edit
                          </button>
                          {!m.is_shared_account && (
                            <button
                              type="button"
                              className="btn btn-sm btn-secondary"
                              onClick={() => {
                                setActionError(null);
                                setResetTarget(m);
                                setResetPasswords({ new_password: '', confirm_password: '' });
                              }}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                            >
                              <KeyRound size={13} /> Reset Password
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => handleToggleActive(m)}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                          >
                            <Power size={13} /> {m.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </>
                      )}
                      {m.role !== 'OWNER' && m.is_active && (
                        <button
                          type="button"
                          onClick={() => handleInitiateRemove(m)}
                          className="btn btn-sm btn-danger"
                        >
                          Revoke Access
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 2. Team Security & Activity Log */}
      {auditLogs.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Shield size={16} style={{ color: 'var(--primary)' }} />
            <h2 style={{ fontSize: '0.98rem', fontWeight: 600, color: 'var(--text-main)' }}>Recent Team &amp; Credential Audit History</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.82rem' }}>
            {auditLogs.map((a) => (
              <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', padding: '0.45rem 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--text-main)' }}>{a.summary} <span style={{ color: 'var(--text-muted)' }}>by @{a.actor}</span></span>
                <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{new Date(a.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Staff Access Requests Submitted to Super Admin */}
      {staffRequests.length > 0 && (
        <div>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.75rem' }}>
            Staff Access Requests (Super Admin Review)
          </h2>
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Requested Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {staffRequests.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 600 }}>{r.full_name}</td>
                    <td>{r.email}</td>
                    <td><span className="badge badge-gray">{r.role_display}</span></td>
                    <td><span className={`badge ${r.status === 'APPROVED' ? 'badge-green' : r.status === 'REJECTED' ? 'badge-red' : 'badge-amber'}`}>{r.status_display}</span></td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{new Date(r.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 4. Pending Invitations Table */}
      {invitations.length > 0 && (
        <div>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.75rem' }}>Pending Invitations</h2>
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Invited Email</th>
                  <th>Assigned Role</th>
                  <th>Status</th>
                  <th>Sent At</th>
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv) => (
                  <tr key={inv.id}>
                    <td style={{ fontWeight: 600 }}>{inv.email}</td>
                    <td><span className="badge badge-gray">{inv.role_display}</span></td>
                    <td><span className={`badge ${inv.is_expired ? 'badge-red' : 'badge-amber'}`}>{inv.is_expired ? 'Expired' : 'Pending'}</span></td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{new Date(inv.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Add Staff Direct Modal */}
      {showAddModal && (
        <Modal title="Add Staff Member" onClose={() => setShowAddModal(false)}>
          <form onSubmit={handleAddStaff} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Username *</label>
              <input className="input-field" required value={addForm.username} onChange={(e) => setAddForm({ ...addForm, username: e.target.value })} placeholder="e.g. aisha_support" />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Full Name</label>
              <input className="input-field" value={addForm.full_name} onChange={(e) => setAddForm({ ...addForm, full_name: e.target.value })} placeholder="e.g. Aisha Khan" />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Workspace Role *</label>
              <select className="input-field" value={addForm.role} onChange={(e) => setAddForm({ ...addForm, role: e.target.value })}>
                <option value="STAFF">Staff (Inbox, CRM Deals, Bookings &amp; Tasks)</option>
                {(actorRole === 'OWNER' || actorRole === 'SUPERUSER') && (
                  <option value="ADMIN">Client Administrator (Settings, Team &amp; Knowledge Base)</option>
                )}
              </select>
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Contact / Recovery Email (Optional)</label>
              <input type="email" className="input-field" value={addForm.contact_email} onChange={(e) => setAddForm({ ...addForm, contact_email: e.target.value })} placeholder="Optional deliverable email" />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Internal Identifier (Optional)</label>
              <input className="input-field" value={addForm.synthetic_identifier} onChange={(e) => setAddForm({ ...addForm, synthetic_identifier: e.target.value })} placeholder="e.g. desk1@company.internal" />
            </div>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                <label htmlFor="add-staff-password" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Initial Password *</label>
                <button type="button" onClick={() => setAddForm({ ...addForm, password: generateStrongPassword() })} style={{ fontSize: '0.75rem', color: 'var(--primary)', background: 'transparent', border: 0, cursor: 'pointer', fontWeight: 600 }}>
                  Generate Strong Password
                </button>
              </div>
              <PasswordInput id="add-staff-password" visibilityLabel="initial staff password" className="input-field" required autoComplete="new-password" value={addForm.password} onChange={(e) => setAddForm({ ...addForm, password: e.target.value })} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem', marginTop: '0.35rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setShowAddModal(false)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={addingStaff}>{addingStaff ? 'Creating...' : 'Create Staff Account'}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Edit Staff Modal */}
      {editTarget && (
        <Modal title={`Edit ${editTarget.full_name}`} onClose={() => setEditTarget(null)}>
          <form onSubmit={handleEditSave} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            {editTarget.is_shared_account && (
              <div style={{ padding: '0.65rem', background: '#fef3c7', borderRadius: '0.4rem', fontSize: '0.8rem', color: '#92400e' }}>
                Shared multi-workspace user: only workspace role and active status can be edited from this workspace.
              </div>
            )}
            {!editTarget.is_shared_account && (
              <>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Username *</label>
                  <input className="input-field" required value={editForm.username} onChange={(e) => setEditForm({ ...editForm, username: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Full Name</label>
                  <input className="input-field" value={editForm.full_name} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Contact Email</label>
                  <input type="email" className="input-field" value={editForm.contact_email} onChange={(e) => setEditForm({ ...editForm, contact_email: e.target.value })} />
                </div>
              </>
            )}
            {(actorRole === 'OWNER' || actorRole === 'SUPERUSER') && (
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Role</label>
                <select className="input-field" value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}>
                  <option value="STAFF">Tenant Staff</option>
                  <option value="ADMIN">Tenant Administrator</option>
                  {actorRole === 'SUPERUSER' && <option value="OWNER">Tenant Owner</option>}
                </select>
              </div>
            )}
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
              <input type="checkbox" checked={editForm.is_active} onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })} />
              Active in this workspace
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setEditTarget(null)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={savingEdit}>{savingEdit ? 'Saving...' : 'Save Changes'}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Administrative Password Reset Modal (No Old Password Required) */}
      {resetTarget && (
        <Modal title={`Reset Password for @${resetTarget.username}`} onClose={() => setResetTarget(null)}>
          <form onSubmit={handleResetPassword} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Administrative reset sets a new password immediately without requiring their current password and revokes any active login sessions for @{resetTarget.username}.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => {
                  const pw = generateStrongPassword();
                  setResetPasswords({ new_password: pw, confirm_password: pw });
                }}
                style={{ fontSize: '0.78rem', color: 'var(--primary)', background: 'transparent', border: 0, cursor: 'pointer', fontWeight: 600 }}
              >
                Generate Strong Password
              </button>
            </div>
            <div>
              <label htmlFor="reset-new-password" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>New Password *</label>
              <PasswordInput id="reset-new-password" visibilityLabel="new password" className="input-field" required autoComplete="new-password" value={resetPasswords.new_password} onChange={(e) => setResetPasswords({ ...resetPasswords, new_password: e.target.value })} />
            </div>
            <div>
              <label htmlFor="reset-confirm-password" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>Confirm New Password *</label>
              <PasswordInput id="reset-confirm-password" visibilityLabel="confirm new password" className="input-field" required autoComplete="new-password" value={resetPasswords.confirm_password} onChange={(e) => setResetPasswords({ ...resetPasswords, confirm_password: e.target.value })} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setResetTarget(null)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={resettingPw}>{resettingPw ? 'Updating...' : 'Reset Password & Revoke Sessions'}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Request Staff Access Modal */}
      {showRequestModal && (
        <Modal title="Request Staff Access" onClose={() => setShowRequestModal(false)}>
          <div style={{ padding: '1.25rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Super Admin reviews requests and provisions secure single-use activation credentials.
            </p>
          </div>
          <form onSubmit={handleRequestStaff} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {reqError && <div style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{reqError}</div>}
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>Full Name *</label>
              <input type="text" required value={reqFullName} onChange={(e) => setReqFullName(e.target.value)} className="input-field" placeholder="e.g. Priya Sharma" />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>Email Address *</label>
              <input type="email" required value={reqEmail} onChange={(e) => setReqEmail(e.target.value)} className="input-field" placeholder="priya@example.com" />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>Workspace Role</label>
              <select value={reqRole} onChange={(e) => setReqRole(e.target.value)} className="input-field">
                <option value="STAFF">Staff (Chat, CRM Deals, Bookings &amp; Tasks)</option>
                <option value="ADMIN">Client Administrator (Settings, Team &amp; Knowledge Base)</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>Notes / Business Justification</label>
              <textarea value={reqNotes} onChange={(e) => setReqNotes(e.target.value)} className="input-field" rows={2} placeholder="Reason for account provisioning..." />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button type="button" onClick={() => setShowRequestModal(false)} className="btn btn-secondary">Cancel</button>
              <button type="submit" disabled={submittingReq} className="btn btn-primary">{submittingReq ? 'Submitting...' : 'Submit Request to Super Admin'}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Reassign Work Before Member Removal Modal */}
      {showReassignModal && memberToRemove && reassignInfo && (
        <Modal title="Reassign Open Work Before Removal" onClose={() => setShowReassignModal(false)}>
          <form onSubmit={handleReassignAndRemove} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              <strong>{memberToRemove.full_name}</strong> currently has{' '}
              <span style={{ color: 'var(--warning)', fontWeight: 600 }}>{reassignInfo.open_deals} open deal(s)</span> and{' '}
              <span style={{ color: 'var(--warning)', fontWeight: 600 }}>{reassignInfo.open_tasks} active task(s)</span>.
              To prevent orphaned customer deals, you must reassign them to an active team member before revoking access.
            </p>
            <div>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>Reassign Open Work To:</label>
              <select value={reassignToUserId} onChange={(e) => setReassignToUserId(e.target.value)} className="input-field" required>
                {members
                  .filter((m) => m.id !== memberToRemove.id && m.is_active)
                  .map((m) => (
                    <option key={m.id} value={m.user_id}>{m.full_name} (@{m.username}) — {m.role_display}</option>
                  ))}
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button type="button" onClick={() => setShowReassignModal(false)} className="btn btn-secondary">Cancel</button>
              <button type="submit" disabled={reassigning} className="btn btn-danger">{reassigning ? 'Reassigning & Revoking...' : 'Reassign Work & Revoke Access'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
