import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { MessageSquare, Users, FileText, UserCheck, RefreshCw } from 'lucide-react';

interface DeliveryItem {
  id: number;
  recipient_phone: string;
  status: string;
  attempts: number;
  last_error: string;
  created_at: string;
}

interface UsageData {
  billing_period: string;
  messages: {
    sent: number;
    reserved: number;
    allowance: number;
    remaining: number;
    percent: number;
  };
  documents: {
    count: number;
    limit: number;
    remaining: number;
  };
  contacts: {
    count: number;
    limit: number;
    remaining: number;
  };
  staff: {
    count: number;
    limit: number;
    remaining: number;
  };
  alerts?: {
    resource: string;
    used: number;
    limit: number;
    percent: number;
    level: 'WARNING' | 'EXCEEDED';
    message: string;
  }[];
  recent_deliveries: DeliveryItem[];
}

export const UsagePage: React.FC = () => {
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUsage = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchApi<UsageData>('/api/usage/overview/');
      setData(res);
    } catch (err: any) {
      setError(err?.error || 'Failed to load usage data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsage();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Resource Quotas & Monthly Usage</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Current billing cycle consumption across outbound messages, contacts, documents, and team seats.
          </p>
        </div>
        <button onClick={loadUsage} className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Refresh Quotas
        </button>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {Array.isArray(data?.alerts) && data!.alerts.length > 0 && (
        <div style={{ display: 'grid', gap: '0.5rem' }}>
          {data!.alerts.map((al) => (
            <div
              key={al.resource}
              role="status"
              style={{
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                border: `1px solid ${al.level === 'EXCEEDED' ? 'var(--danger)' : 'var(--warning)'}`,
                backgroundColor: al.level === 'EXCEEDED' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                color: al.level === 'EXCEEDED' ? 'var(--danger)' : 'var(--warning)',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              {al.level === 'EXCEEDED' ? 'Quota limit reached: ' : 'Approaching quota limit: '}
              {al.message}
            </div>
          ))}
        </div>
      )}

      {/* Quota Progress Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(18rem, 1fr))', gap: '1rem' }}>
        {/* Messages */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MessageSquare size={16} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)" }}>Monthly Messages</h2>
            </div>
            <span style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{data?.billing_period || 'Current Month'}</span>
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.25rem' }}>
            {(data?.messages.sent || 0) + (data?.messages.reserved || 0)} / {data?.messages.allowance || 0}
          </div>
          <p style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.75rem' }}>
            {data?.messages.remaining || 0} outbound messages remaining
          </p>
          <div style={{ width: '100%', height: '0.5rem', backgroundColor: "var(--bg-card-hover)", borderRadius: '9999px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${data?.messages.percent || 0}%`,
                height: '100%',
                backgroundColor: (data?.messages.percent || 0) > 90 ? '#ef4444' : "var(--primary)",
                borderRadius: '9999px',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        </div>

        {/* Contacts */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Users size={16} style={{ color: "var(--primary)" }} />
            <h2 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)" }}>Customer Contacts</h2>
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.25rem' }}>
            {data?.contacts.count || 0} / {data?.contacts.limit || 0}
          </div>
          <p style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.75rem' }}>
            {data?.contacts.remaining || 0} contact slots available
          </p>
          <div style={{ width: '100%', height: '0.5rem', backgroundColor: "var(--bg-card-hover)", borderRadius: '9999px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.min(100, Math.round(((data?.contacts.count || 0) / (data?.contacts.limit || 1)) * 100))}%`,
                height: '100%',
                backgroundColor: "var(--primary)",
                borderRadius: '9999px',
              }}
            />
          </div>
        </div>

        {/* Knowledge Documents */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <FileText size={16} style={{ color: "var(--warning)" }} />
            <h2 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)" }}>Knowledge Documents</h2>
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.25rem' }}>
            {data?.documents.count || 0} / {data?.documents.limit || 0}
          </div>
          <p style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.75rem' }}>
            {data?.documents.remaining || 0} documents remaining
          </p>
          <div style={{ width: '100%', height: '0.5rem', backgroundColor: "var(--bg-card-hover)", borderRadius: '9999px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.min(100, Math.round(((data?.documents.count || 0) / (data?.documents.limit || 1)) * 100))}%`,
                height: '100%',
                backgroundColor: '#f59e0b',
                borderRadius: '9999px',
              }}
            />
          </div>
        </div>

        {/* Staff Seats */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <UserCheck size={16} style={{ color: "var(--primary)" }} />
            <h2 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)" }}>Team Seats</h2>
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.25rem' }}>
            {data?.staff.count || 0} / {data?.staff.limit || 0}
          </div>
          <p style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.75rem' }}>
            {data?.staff.remaining || 0} seats available for invite
          </p>
          <div style={{ width: '100%', height: '0.5rem', backgroundColor: "var(--bg-card-hover)", borderRadius: '9999px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.min(100, Math.round(((data?.staff.count || 0) / (data?.staff.limit || 1)) * 100))}%`,
                height: '100%',
                backgroundColor: '#a855f7',
                borderRadius: '9999px',
              }}
            />
          </div>
        </div>
      </div>

      {/* Recent Outbound Deliveries Table */}
      <div className="card">
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '1rem' }}>
          Recent WhatsApp Outbound Deliveries
        </h2>
        {data?.recent_deliveries && data.recent_deliveries.length > 0 ? (
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Recipient</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Notes</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_deliveries.map((d) => (
                  <tr key={d.id}>
                    <td style={{ fontWeight: 600 }}>{d.recipient_phone}</td>
                    <td>
                      <span className={`badge ${d.status === 'DELIVERED' ? 'badge-green' : d.status === 'FAILED' ? 'badge-red' : 'badge-amber'}`}>
                        {d.status}
                      </span>
                    </td>
                    <td>{d.attempts}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: '0.8rem' }}>{d.last_error || 'None'}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: '0.8rem' }}>{new Date(d.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>
            No outbound delivery records in the current period.
          </p>
        )}
      </div>
    </div>
  );
};
