import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { BarChart2, MessageSquare, TrendingUp, CheckSquare, CalendarCheck, RefreshCw } from 'lucide-react';

interface ReportsData {
  conversations: {
    total: number;
    active: number;
    human_takeover: number;
    unanswered_inbound?: number;
    unread_messages?: number;
    avg_first_response_minutes?: number | null;
  };
  deals: {
    open: number;
    won: number;
    lost: number;
    pipeline_value: string;
  };
  activities: {
    pending: number;
    overdue: number;
    completed: number;
  };
  bookings: {
    total: number;
    confirmed: number;
  };
  agents?: {
    user_id: number;
    username: string;
    full_name: string;
    role: string;
    open_chats: number;
    replies_sent: number;
  }[];
  campaigns?: {
    total: number;
    completed: number;
    sent: number;
    delivered: number;
    read: number;
    failed: number;
  };
}

export const ReportsPage: React.FC = () => {
  const [data, setData] = useState<ReportsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReports = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchApi<ReportsData>('/api/reports/overview/');
      setData(res);
    } catch (err: any) {
      setError(err?.error || 'Failed to load reports overview.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Workspace Reports & Analytics</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Operational performance across WhatsApp conversations, sales pipelines, follow-ups, and bookings.
          </p>
        </div>
        <button onClick={loadReports} className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Refresh Metrics
        </button>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Primary KPI Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(18rem, 1fr))', gap: '1rem' }}>
        {/* WhatsApp Conversations */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <div style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem', backgroundColor: 'rgba(17, 183, 109, 0.1)', color: "var(--primary)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <MessageSquare size={16} />
            </div>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Customer Conversations</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Total Handled</span>
              <span style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>{data?.conversations.total || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Active AI Dialogues</span>
              <span style={{ color: "var(--primary)", fontWeight: 600 }}>{data?.conversations.active || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Human Handover</span>
              <span style={{ color: "var(--warning)", fontWeight: 600 }}>{data?.conversations.human_takeover || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Unanswered Inbound</span>
              <span style={{ color: "var(--danger)", fontWeight: 600 }}>{data?.conversations.unanswered_inbound || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Avg First Response</span>
              <span style={{ color: "var(--text-main)", fontWeight: 600 }}>
                {data?.conversations.avg_first_response_minutes != null ? `${data.conversations.avg_first_response_minutes} min` : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Sales Pipeline */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <div style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem', backgroundColor: 'var(--primary-light)', color: "var(--primary)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <TrendingUp size={16} />
            </div>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Deals Pipeline</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Open Pipeline Value</span>
              <span style={{ fontSize: '1.35rem', fontWeight: 700, color: "var(--primary)" }}>₹{data?.deals.pipeline_value || '0.00'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Active Deals Open</span>
              <span style={{ color: "var(--text-main)", fontWeight: 600 }}>{data?.deals.open || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Closed Won</span>
              <span style={{ color: "var(--primary)", fontWeight: 600 }}>{data?.deals.won || 0} deals</span>
            </div>
          </div>
        </div>

        {/* Tasks & Activities */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <div style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem', backgroundColor: 'var(--primary-light)', color: "var(--primary)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckSquare size={16} />
            </div>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Follow-up Tasks</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Pending Follow-ups</span>
              <span style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>{data?.activities.pending || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Overdue Tasks</span>
              <span style={{ color: "var(--danger)", fontWeight: 600 }}>{data?.activities.overdue || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Completed</span>
              <span style={{ color: "var(--primary)", fontWeight: 600 }}>{data?.activities.completed || 0}</span>
            </div>
          </div>
        </div>

        {/* Service Bookings */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <div style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem', backgroundColor: 'rgba(245, 158, 11, 0.1)', color: "var(--warning)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CalendarCheck size={16} />
            </div>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Bookings & Demos</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Total Requests</span>
              <span style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>{data?.bookings.total || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: "var(--text-muted)" }}>Confirmed Appointments</span>
              <span style={{ color: "var(--primary)", fontWeight: 600 }}>{data?.bookings.confirmed || 0}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Campaigns & Agent Workload */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(22rem, 1fr))', gap: '1rem' }}>
        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <BarChart2 size={16} style={{ color: 'var(--primary)' }} /> Campaign Outcomes
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', fontSize: '0.85rem' }}>
            <div><span style={{ color: 'var(--text-muted)', display: 'block' }}>Campaigns</span><strong>{data?.campaigns?.total ?? 0}</strong></div>
            <div><span style={{ color: 'var(--text-muted)', display: 'block' }}>Sent</span><strong>{data?.campaigns?.sent ?? 0}</strong></div>
            <div><span style={{ color: 'var(--text-muted)', display: 'block' }}>Delivered</span><strong style={{ color: 'var(--primary)' }}>{data?.campaigns?.delivered ?? 0}</strong></div>
            <div><span style={{ color: 'var(--text-muted)', display: 'block' }}>Read</span><strong style={{ color: 'var(--primary)' }}>{data?.campaigns?.read ?? 0}</strong></div>
            <div><span style={{ color: 'var(--text-muted)', display: 'block' }}>Failed/Blocked</span><strong style={{ color: 'var(--danger)' }}>{data?.campaigns?.failed ?? 0}</strong></div>
          </div>
        </div>

        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>Agent Workload</h2>
          {!data?.agents?.length ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active agents yet.</p>
          ) : (
            <table className="custom-table" style={{ width: '100%' }}>
              <thead><tr><th>Agent</th><th>Role</th><th>Open Chats</th><th>Replies Sent</th></tr></thead>
              <tbody>
                {data.agents.map((a) => (
                  <tr key={a.user_id}>
                    <td>{a.full_name} (@{a.username})</td>
                    <td>{a.role}</td>
                    <td>{a.open_chats}</td>
                    <td>{a.replies_sent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};
