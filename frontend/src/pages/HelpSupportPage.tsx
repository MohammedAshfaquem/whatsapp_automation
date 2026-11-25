import React, { useEffect, useState, useRef } from 'react';
import { useVisibleAutoSync } from '../hooks/useVisibleAutoSync';
import { fetchApi } from '../api/client';
import Modal from '../components/Modal';
import {
  LifeBuoy,
  Plus,
  Send,
  CheckCircle2,
  RotateCcw,
  Clock,
  Paperclip,
  RefreshCw,
} from 'lucide-react';

interface TicketItem {
  id: string;
  ticket_number: string;
  subject: string;
  category: string;
  category_display: string;
  priority: string;
  priority_display: string;
  status: string;
  status_display: string;
  sla_cycle_started_at: string | null;
  sla_deadline_at: string | null;
  sla_breached: boolean;
  sla_threshold_minutes: number;
  updated_at: string;
  created_at: string;
}

interface MessageItem {
  id: string;
  sender_name: string;
  sender_type: string;
  body: string;
  attachment?: { name: string; size: number; url: string } | null;
  created_at: string;
}

export const HelpSupportPage: React.FC = () => {
  const [tickets, setTickets] = useState<TicketItem[]>([]);
  const [categories, setCategories] = useState<{ value: string; label: string }[]>([]);
  const [priorities, setPriorities] = useState<{ value: string; label: string }[]>([]);
  const [slaMinutes, setSlaMinutes] = useState(10);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TicketItem | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    subject: '',
    category: 'META_SETUP',
    priority: 'NORMAL',
    description: '',
  });
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [replyText, setReplyText] = useState('');
  const [replyFile, setReplyFile] = useState<File | null>(null);
  const [replying, setReplying] = useState(false);

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

  const loadTickets = async (filter = statusFilter, quiet = false) => {
    const version = ++listVersion.current;
    try {
      if (!quiet) setLoading(true);
      const qs = filter ? `?status=${encodeURIComponent(filter)}` : '';
      const res = await fetchApi<{
        tickets: TicketItem[];
        categories: { value: string; label: string }[];
        priorities: { value: string; label: string }[];
        sla_config: { threshold_minutes: number };
      }>(`/api/support/tickets/${qs}`);
      if (!mounted.current || version !== listVersion.current || filter !== queryRef.current) return;
      setTickets(res.tickets || []);
      if (res.categories) setCategories(res.categories);
      if (res.priorities) setPriorities(res.priorities);
      if (res.sla_config?.threshold_minutes) setSlaMinutes(res.sla_config.threshold_minutes);
    } catch (err: any) {
      if (quiet) throw err;
      if (mounted.current && version === listVersion.current) setError(err?.error || 'Could not load support tickets.');
    } finally {
      if (!quiet && mounted.current) setLoading(false);
    }
  };

  const openTicket = async (ticketId: string, quiet = false) => {
    if (quiet && selectionRef.current !== ticketId) return;
    if (!quiet) { selectionRef.current = ticketId; if (selected?.id !== ticketId) { setSelected(null); setMessages([]); } }
    const version = ++detailVersion.current;
    try {
      if (!quiet) setError(null);
      const res = await fetchApi<{ ticket: TicketItem; messages: MessageItem[] }>(
        `/api/support/tickets/${ticketId}/`
      );
      if (!mounted.current || selectionRef.current !== ticketId || version !== detailVersion.current) return;
      setSelected(res.ticket);
      setMessages(res.messages || []);
    } catch (err: any) {
      if (quiet) throw err;
      if (mounted.current && selectionRef.current === ticketId && version === detailVersion.current) setError(err?.error || 'Failed to load ticket conversation.');
    }
  };

  useEffect(() => {
    loadTickets();
  }, [statusFilter]);

  const {refresh, syncError} = useVisibleAutoSync(async () => {
    const reads = await Promise.allSettled([
      loadTickets(statusFilter, true),
      selectionRef.current ? openTicket(selectionRef.current, true) : Promise.resolve(),
    ]);
    if (reads.some(result => result.status === 'rejected')) throw new Error('Sync interrupted');
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('subject', createForm.subject);
      fd.append('category', createForm.category);
      fd.append('priority', createForm.priority);
      fd.append('description', createForm.description);
      if (createFile) fd.append('attachment', createFile);
      const res = await fetchApi<{ ticket: TicketItem; message: string }>('/api/support/tickets/', {
        method: 'POST',
        body: fd,
      });
      setShowCreate(false);
      setCreateForm({ subject: '', category: 'META_SETUP', priority: 'NORMAL', description: '' });
      setCreateFile(null);
      setFeedback(res.message);
      await loadTickets();
      await openTicket(res.ticket.id);
    } catch (err: any) {
      setError(err?.error || 'Could not submit support ticket.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    setError(null);
    setReplying(true);
    try {
      const fd = new FormData();
      fd.append('body', replyText);
      if (replyFile) fd.append('attachment', replyFile);
      await fetchApi(`/api/support/tickets/${selected.id}/reply/`, {
        method: 'POST',
        body: fd,
      });
      if (selectionRef.current === selected.id) setReplyText(current => current === replyText ? '' : current);
      if (selectionRef.current === selected.id) setReplyFile(current => current === replyFile ? null : current);
      await Promise.allSettled([openTicket(selected.id, true), loadTickets()]);
    } catch (err: any) {
      setError(err?.error || 'Could not send reply.');
    } finally {
      setReplying(false);
    }
  };

  const handleStatusAction = async (action: 'resolve' | 'reopen') => {
    if (!selected) return;
    setError(null);
    try {
      await fetchApi(`/api/support/tickets/${selected.id}/status/`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      await Promise.allSettled([openTicket(selected.id, true), loadTickets()]);
    } catch (err: any) {
      setError(err?.error || 'Could not update ticket status.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '78rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>Platform Help &amp; Support</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Direct ticket channel to Neoriz platform engineers for onboarding, Meta verification, billing, or urgent platform issues.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button type="button" className="btn btn-secondary" onClick={() => void refresh()} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <RefreshCw size={14} /> Refresh
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
            <Plus size={16} /> Open Platform Ticket
          </button>
        </div>
      </div>

      <div style={{ padding: '0.75rem 1rem', borderRadius: '0.5rem', background: 'rgba(17,183,109,0.08)', border: '1px solid rgba(17,183,109,0.28)', fontSize: '0.84rem', color: '#065f46', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <LifeBuoy size={16} />
        <span>
          <strong>{slaMinutes}-Minute Urgent Escalation Policy:</strong> Any client message left unanswered for {slaMinutes} minutes automatically triggers an urgent alert to Neoriz Platform Operations.
        </span>
      </div>

      <p role="status" style={{fontSize:'.8rem',color:syncError?'var(--danger)':'var(--text-muted)'}}>{syncError ? 'Connection interrupted. Retrying automatic sync…' : 'Auto-sync every 2.5 seconds while visible; refreshes when you return.'}</p>
      {feedback && <div role="status" style={{ padding: '0.75rem 1rem', background: 'rgba(17,183,109,0.12)', borderRadius: '0.5rem', color: '#047857', fontSize: '0.86rem' }}>{feedback}</div>}
      {error && <div role="alert" style={{ padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.12)', borderRadius: '0.5rem', color: '#b91c1c', fontSize: '0.86rem' }}>{error}</div>}

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {[
          { label: 'All', value: '' },
          { label: 'Open', value: 'OPEN' },
          { label: 'Awaiting Platform', value: 'AWAITING_PLATFORM' },
          { label: 'Awaiting Reply', value: 'AWAITING_CLIENT' },
          { label: 'Resolved', value: 'RESOLVED' },
        ].map((t) => (
          <button
            key={t.label}
            type="button"
            className={statusFilter === t.value ? 'btn btn-primary' : 'btn btn-secondary'}
            onClick={() => setStatusFilter(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selected ? 'minmax(18rem, 1fr) minmax(24rem, 1.5fr)' : '1fr', gap: '1rem', alignItems: 'start' }}>
        {/* Ticket List */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>Your Support Tickets</h2>
          {loading && tickets.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.86rem' }}>Loading tickets...</div>
          ) : tickets.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.86rem' }}>No platform support tickets found.</div>
          ) : (
            tickets.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => openTicket(t.id)}
                style={{
                  textAlign: 'left',
                  padding: '0.8rem',
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
                  <span style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-main)' }}>{t.ticket_number}: {t.subject}</span>
                  <span className="badge badge-gray">{t.status_display}</span>
                </div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  {t.category_display} &bull; Priority: {t.priority_display}
                  {t.sla_breached ? ' • SLA Escalated' : ''}
                </div>
              </button>
            ))
          )}
        </div>

        {/* Thread Detail */}
        {selected && (
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.75rem' }}>
              <div>
                <h2 style={{ fontSize: '1.08rem', fontWeight: 700, color: 'var(--text-main)' }}>{selected.ticket_number} — {selected.subject}</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                  Status: <strong>{selected.status_display}</strong> &bull; {selected.category_display} &bull; {selected.priority_display}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.45rem' }}>
                {selected.status !== 'RESOLVED' && selected.status !== 'CLOSED' ? (
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => handleStatusAction('resolve')} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                    <CheckCircle2 size={14} /> Mark Resolved
                  </button>
                ) : (
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => handleStatusAction('reopen')} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                    <RotateCcw size={14} /> Reopen
                  </button>
                )}
              </div>
            </div>

            {selected.sla_deadline_at && (selected.status === 'OPEN' || selected.status === 'AWAITING_PLATFORM') && (
              <div style={{ fontSize: '0.78rem', color: selected.sla_breached ? '#b45309' : 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Clock size={14} />
                {selected.sla_breached
                  ? 'Platform escalation triggered — Neoriz engineering team notified.'
                  : `Response SLA threshold: ${new Date(selected.sla_deadline_at).toLocaleTimeString()}`}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '24rem', overflowY: 'auto' }}>
              {messages.map((m) => (
                <div
                  key={m.id}
                  style={{
                    padding: '0.8rem 0.95rem',
                    borderRadius: '0.5rem',
                    border: '1px solid var(--border)',
                    background: m.sender_type === 'PLATFORM' ? 'rgba(17,183,109,0.07)' : m.sender_type === 'SYSTEM' ? '#f8fafc' : 'var(--bg-card)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    <strong>{m.sender_type === 'PLATFORM' ? `Neoriz Support (${m.sender_name})` : m.sender_name}</strong>
                    <span>{new Date(m.created_at).toLocaleString()}</span>
                  </div>
                  <div style={{ fontSize: '0.88rem', color: 'var(--text-main)', whiteSpace: 'pre-wrap' }}>{m.body}</div>
                  {m.attachment && (
                    <div style={{ marginTop: '0.45rem' }}>
                      <a href={m.attachment.url} style={{ fontSize: '0.78rem', color: 'var(--primary)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Paperclip size={13} /> {m.attachment.name}
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <form onSubmit={handleReply} style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
              <textarea
                className="input-field"
                rows={3}
                placeholder="Write a reply to Neoriz Support..."
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <input type="file" onChange={(e) => setReplyFile(e.target.files?.[0] || null)} />
                <button type="submit" className="btn btn-primary" disabled={replying || (!replyText.trim() && !replyFile)} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Send size={14} /> {replying ? 'Sending...' : 'Send Reply'}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {showCreate && (
        <Modal title="Open Platform Support Ticket" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>Subject *</label>
              <input className="input-field" required value={createForm.subject} onChange={(e) => setCreateForm({ ...createForm, subject: e.target.value })} placeholder="Brief summary of the issue" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>Category</label>
                <select className="input-field" value={createForm.category} onChange={(e) => setCreateForm({ ...createForm, category: e.target.value })}>
                  {(categories.length > 0 ? categories : [{ value: 'META_SETUP', label: 'Meta & WhatsApp Setup' }, { value: 'BILLING', label: 'Billing & Subscription' }, { value: 'WHATSAPP_DELIVERY', label: 'WhatsApp Delivery & Webhooks' }, { value: 'ACCOUNT', label: 'Account, Email & Staff Access' }, { value: 'BUG', label: 'Platform Bug / Outage' }, { value: 'OTHER', label: 'Other Platform Help' }]).map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>Priority</label>
                <select className="input-field" value={createForm.priority} onChange={(e) => setCreateForm({ ...createForm, priority: e.target.value })}>
                  {(priorities.length > 0 ? priorities : [{ value: 'LOW', label: 'Low' }, { value: 'NORMAL', label: 'Normal' }, { value: 'HIGH', label: 'High' }, { value: 'URGENT', label: 'Urgent' }]).map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>Details *</label>
              <textarea className="input-field" required rows={4} value={createForm.description} onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} placeholder="Describe what happened, steps, or error messages..." />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>Attachment (Optional, max 5 MB)</label>
              <input type="file" onChange={(e) => setCreateFile(e.target.files?.[0] || null)} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? 'Submitting...' : 'Submit Ticket'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
