import React, { useEffect, useState, useRef } from 'react';
import { useVisibleAutoSync } from '../hooks/useVisibleAutoSync';
import { fetchApi } from '../api/client';
import { AlertTriangle, Lock, MessageSquare, RefreshCw, Send, Paperclip } from 'lucide-react';

interface PlatformTicket {
  id: string;
  ticket_number: string;
  tenant_id: number;
  tenant_name: string;
  subject: string;
  category: string;
  category_display: string;
  priority: string;
  priority_display: string;
  status: string;
  status_display: string;
  assigned_to: { id: number; username: string } | null;
  sla_cycle_started_at: string | null;
  sla_breached: boolean;
  current_cycle_escalated?: boolean;
  escalations_count?: number;
  updated_at: string;
}

interface PlatformMessage {
  id: string;
  sender_name: string;
  sender_type: string;
  is_internal_note: boolean;
  body: string;
  attachment?: { name: string; url: string } | null;
  created_at: string;
}

interface EscalationLog {
  id: string;
  cycle_started_at: string;
  escalated_to_email: string;
  status: string;
  reason: string;
  email_status: string | null;
  sent_at: string | null;
}

export const PlatformSupportPage: React.FC = () => {
  const [tickets, setTickets] = useState<PlatformTicket[]>([]);
  const [counts, setCounts] = useState<any>(null);
  const [operators, setOperators] = useState<{ id: number; username: string; full_name: string }[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<PlatformTicket | null>(null);
  const [messages, setMessages] = useState<PlatformMessage[]>([]);
  const [escalations, setEscalations] = useState<EscalationLog[]>([]);
  const [replyBody, setReplyBody] = useState('');
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const selectionRef = useRef<string | null>(null);
  const listVersion = useRef(0);
  const detailVersion = useRef(0);
  const mounted = useRef(true);
  const queryRef = useRef('');
  queryRef.current = statusFilter;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; listVersion.current++; detailVersion.current++; };
  }, []);

  const loadQueue = async (statusArg = statusFilter, queryArg = search, quiet = false) => {
    const version = ++listVersion.current;
    try {
      const p = new URLSearchParams();
      if (statusArg) p.set('status', statusArg);
      if (queryArg.trim()) p.set('q', queryArg.trim());
      const res = await fetchApi<{
        tickets: PlatformTicket[];
        counts: any;
        operators: { id: number; username: string; full_name: string }[];
      }>(`/api/platform/support/tickets/${p.toString() ? `?${p.toString()}` : ''}`);
      if (!mounted.current || version !== listVersion.current || statusArg !== queryRef.current) return;
      setTickets(res.tickets || []);
      setCounts(res.counts);
      setOperators(res.operators || []);
    } catch (err: any) {
      if (quiet) throw err;
      if (mounted.current && version === listVersion.current) setError(err?.error || 'Could not load platform support queue.');
    }
  };

  const openDetail = async (ticketId: string, quiet = false) => {
    if (quiet && selectionRef.current !== ticketId) return;
    if (!quiet) { selectionRef.current = ticketId; if (selected?.id !== ticketId) { setSelected(null); setMessages([]); } }
    const version = ++detailVersion.current;
    try {
      const res = await fetchApi<{
        ticket: PlatformTicket;
        messages: PlatformMessage[];
        escalations: EscalationLog[];
      }>(`/api/platform/support/tickets/${ticketId}/`);
      if (!mounted.current || selectionRef.current !== ticketId || version !== detailVersion.current) return;
      setSelected(res.ticket);
      setMessages(res.messages || []);
      setEscalations(res.escalations || []);
    } catch (err: any) {
      if (quiet) throw err;
      if (mounted.current && selectionRef.current === ticketId && version === detailVersion.current) setError(err?.error || 'Could not load ticket details.');
    }
  };

  useEffect(() => {
    loadQueue();
  }, [statusFilter]);

  const {refresh, syncError} = useVisibleAutoSync(async () => {
    const reads = await Promise.allSettled([
      loadQueue(statusFilter, search, true),
      selectionRef.current ? openDetail(selectionRef.current, true) : Promise.resolve(),
    ]);
    if (reads.some(result => result.status === 'rejected')) throw new Error('Sync interrupted');
  });

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !replyBody.trim()) return;
    setError(null);
    setFeedback(null);
    setSending(true);
    try {
      await fetchApi(`/api/platform/support/tickets/${selected.id}/reply/`, {
        method: 'POST',
        body: JSON.stringify({
          body: replyBody.trim(),
          is_internal_note: isInternalNote,
        }),
      });
      if (selectionRef.current === selected.id) setReplyBody(current => current === replyBody ? '' : current);
      setFeedback(
        isInternalNote
          ? 'Internal operator note recorded (hidden from client; SLA timer unchanged).'
          : 'Public reply sent to client and SLA response timer cleared.'
      );
      await Promise.allSettled([openDetail(selected.id, true), loadQueue()]);
    } catch (err: any) {
      setError(err?.error || 'Failed to submit response.');
    } finally {
      setSending(false);
    }
  };

  const handleMetaUpdate = async (patch: { status?: string; priority?: string; assigned_to_id?: number }) => {
    if (!selected) return;
    setError(null);
    try {
      await fetchApi(`/api/platform/support/tickets/${selected.id}/update/`, {
        method: 'POST',
        body: JSON.stringify(patch),
      });
      await Promise.allSettled([openDetail(selected.id, true), loadQueue()]);
    } catch (err: any) {
      setError(err?.error || 'Update failed.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>Platform Support Queue &amp; SLA Console</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Respond to client workspace tickets, record internal operator notes, and audit 10-minute emergency SLA escalations.
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void refresh()} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <p role="status" style={{fontSize:'.8rem',color:syncError?'var(--danger)':'var(--text-muted)'}}>{syncError ? 'Connection interrupted. Retrying automatic sync…' : 'Auto-sync every 2.5 seconds while visible; refreshes when you return.'}</p>
      {feedback && <div role="status" style={{ padding: '0.75rem 1rem', background: 'rgba(17,183,109,0.12)', borderRadius: '0.5rem', color: '#047857', fontSize: '0.86rem' }}>{feedback}</div>}
      {error && <div role="alert" style={{ padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.12)', borderRadius: '0.5rem', color: '#b91c1c', fontSize: '0.86rem' }}>{error}</div>}

      {counts && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(9.5rem, 1fr))', gap: '0.75rem' }}>
          {[
            { label: 'Total Tickets', val: counts.total, filter: '' },
            { label: 'Awaiting Platform', val: counts.open, filter: 'OPEN' },
            { label: 'Breached SLA (>10m)', val: counts.breached, filter: 'BREACHED' },
            { label: 'Escalated Alerts', val: counts.escalated, filter: 'ESCALATED' },
            { label: 'Awaiting Client', val: counts.awaiting_client, filter: 'AWAITING_CLIENT' },
            { label: 'Resolved', val: counts.resolved, filter: 'RESOLVED' },
          ].map((k) => (
            <button
              key={k.label}
              type="button"
              onClick={() => setStatusFilter(k.filter)}
              className="card"
              style={{ textAlign: 'left', cursor: 'pointer', border: statusFilter === k.filter ? '1.5px solid var(--primary)' : '1px solid var(--border)' }}
            >
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontWeight: 600 }}>{k.label}</div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: k.filter === 'BREACHED' && k.val > 0 ? '#dc2626' : 'var(--text-main)' }}>{k.val}</div>
            </button>
          ))}
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); loadQueue(); }} style={{ display: 'flex', gap: '0.6rem' }}>
        <input className="input-field" placeholder="Search ticket number, subject, or client business..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: 1 }} />
        <button type="submit" className="btn btn-secondary">Filter</button>
      </form>

      <div style={{ display: 'grid', gridTemplateColumns: selected ? 'minmax(18rem, 1fr) minmax(25rem, 1.5fr)' : '1fr', gap: '1rem', alignItems: 'start' }}>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {tickets.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.86rem' }}>No tickets match the current queue filter.</div>
          ) : (
            tickets.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => openDetail(t.id)}
                style={{
                  textAlign: 'left',
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  border: selected?.id === t.id ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                  background: selected?.id === t.id ? 'rgba(17,183,109,0.06)' : 'var(--bg-card)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.3rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.88rem' }}>{t.ticket_number} &bull; {t.tenant_name}</span>
                  <span className="badge badge-gray">{t.status_display}</span>
                </div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-main)' }}>{t.subject}</div>
                <div style={{ fontSize: '0.75rem', color: t.sla_breached ? '#dc2626' : 'var(--text-muted)' }}>
                  {t.priority_display} &bull; {t.category_display}
                  {t.sla_breached ? ' • SLA BREACHED' : ''}
                  {t.escalations_count ? ` • ${t.escalations_count} escalation(s)` : ''}
                </div>
              </button>
            ))
          )}
        </div>

        {selected && (
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.75rem' }}>
              <div>
                <h2 style={{ fontSize: '1.08rem', fontWeight: 700 }}>{selected.ticket_number} — {selected.subject}</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Client Workspace: <strong>{selected.tenant_name}</strong></div>
              </div>
              <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                <select className="input-field" value={selected.status} onChange={(e) => handleMetaUpdate({ status: e.target.value })}>
                  <option value="OPEN">Open</option>
                  <option value="AWAITING_PLATFORM">Awaiting Platform</option>
                  <option value="AWAITING_CLIENT">Awaiting Client</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="CLOSED">Closed</option>
                </select>
                <select className="input-field" value={selected.priority} onChange={(e) => handleMetaUpdate({ priority: e.target.value })}>
                  <option value="LOW">Low</option>
                  <option value="NORMAL">Normal</option>
                  <option value="HIGH">High</option>
                  <option value="URGENT">Urgent</option>
                </select>
                <select className="input-field" value={selected.assigned_to?.id || 0} onChange={(e) => handleMetaUpdate({ assigned_to_id: Number(e.target.value) })}>
                  <option value={0}>Unassigned</option>
                  {operators.map((op) => (
                    <option key={op.id} value={op.id}>{op.full_name} (@{op.username})</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem', maxHeight: '22rem', overflowY: 'auto' }}>
              {messages.map((m) => (
                <div
                  key={m.id}
                  style={{
                    padding: '0.8rem 0.95rem',
                    borderRadius: '0.5rem',
                    border: m.is_internal_note ? '1px solid #f59e0b' : '1px solid var(--border)',
                    background: m.is_internal_note ? '#fffbeb' : m.sender_type === 'PLATFORM' ? 'rgba(17,183,109,0.07)' : 'var(--bg-card)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', fontWeight: 700, color: m.is_internal_note ? '#92400e' : 'var(--text-main)' }}>
                      {m.is_internal_note ? <Lock size={12} /> : <MessageSquare size={12} />}
                      {m.sender_name} {m.is_internal_note ? '(INTERNAL NOTE — HIDDEN FROM CLIENT)' : `(${m.sender_type})`}
                    </span>
                    <span>{new Date(m.created_at).toLocaleString()}</span>
                  </div>
                  <div style={{ fontSize: '0.88rem', whiteSpace: 'pre-wrap' }}>{m.body}</div>
                  {m.attachment && (
                    <a href={m.attachment.url} style={{ fontSize: '0.78rem', color: 'var(--primary)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.35rem' }}>
                      <Paperclip size={13} /> {m.attachment.name}
                    </a>
                  )}
                </div>
              ))}
            </div>

            <form onSubmit={handleReply} style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', fontWeight: 600, color: isInternalNote ? '#92400e' : 'var(--text-main)' }}>
                <input type="checkbox" checked={isInternalNote} onChange={(e) => setIsInternalNote(e.target.checked)} />
                Internal Operator Note (strictly hidden from client; does NOT stop 10-min SLA timer)
              </label>
              <textarea
                className="input-field"
                rows={3}
                placeholder={isInternalNote ? 'Internal engineering/support note...' : 'Reply directly to the client...'}
                value={replyBody}
                onChange={(e) => setReplyBody(e.target.value)}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button type="submit" className="btn btn-primary" disabled={sending || !replyBody.trim()} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Send size={14} /> {sending ? 'Sending...' : isInternalNote ? 'Save Internal Note' : 'Send Public Reply'}
                </button>
              </div>
            </form>

            {escalations.length > 0 && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
                <h3 style={{ fontSize: '0.88rem', fontWeight: 700, marginBottom: '0.5rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <AlertTriangle size={14} style={{ color: '#d97706' }} /> Emergency SLA Escalation Audit Log
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.78rem' }}>
                  {escalations.map((e) => (
                    <div key={e.id} style={{ padding: '0.5rem 0.65rem', borderRadius: '0.4rem', background: '#f8fafc', border: '1px solid var(--border)' }}>
                      <strong>{e.status}</strong> &rarr; {e.escalated_to_email} &bull; Email: {e.email_status || 'PENDING'} &bull; Cycle started: {new Date(e.cycle_started_at).toLocaleString()}
                      {e.reason ? ` — ${e.reason}` : ''}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
