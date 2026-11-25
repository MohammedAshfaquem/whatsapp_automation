import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { fetchApi } from '../api/client';
import {
  MessageSquare,
  Users,
  FileText,
  UserCheck,
  ArrowRight,
} from 'lucide-react';

export const DashboardPage: React.FC<{ onNavigate: (path: string) => void }> = ({ onNavigate }) => {
  const { tenant, usage, membership } = useAuth();
  const [crmMetrics, setCrmMetrics] = useState<any>(null);
  const [recentActivities, setRecentActivities] = useState<any[]>([]);

  useEffect(() => {
    fetchApi('/api/crm/overview/')
      .then((data: any) => {
        setCrmMetrics(data.metrics);
        setRecentActivities(data.recent_activities || []);
      })
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      {/* Welcome Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, rgba(17, 183, 109, 0.12) 0%, var(--bg-card) 100%)",
          border: '1px solid rgba(17, 183, 109, 0.25)',
          borderRadius: '0.75rem',
          padding: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <span style={{ width: '0.625rem', height: '0.625rem', borderRadius: '50%', backgroundColor: "var(--primary)", display: 'inline-block' }}></span>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: "var(--primary)", textTransform: 'uppercase' }}>
              System Operational • AI Grounding Active
            </span>
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.25rem' }}>
            {tenant?.name || 'Workspace Dashboard'}
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: '0.875rem' }}>
            Plan: <strong style={{ color: "var(--text-main)" }}>{tenant?.plan_name}</strong> • Role:{' '}
            <strong style={{ color: "var(--text-main)" }}>{membership?.role_display}</strong>
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => onNavigate('/app/inbox')} className="btn btn-primary">
            <MessageSquare size={16} /> Open WhatsApp Inbox
          </button>
        </div>
      </div>

      {/* Quota & Usage Grid */}
      {usage && (
        <div>
          <h2 style={{ fontSize: '0.9rem', fontWeight: 600, color: "var(--text-muted)", textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>
            Monthly Subscription Quotas
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(15rem, 1fr))', gap: '1rem' }}>
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                <span>WhatsApp Messages</span>
                <MessageSquare size={16} style={{ color: "var(--primary)" }} />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>
                {usage.messages.sent?.toLocaleString()} / {usage.messages.allowance?.toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                {usage.messages.remaining?.toLocaleString()} remaining this billing cycle
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                <span>Customer Contacts</span>
                <Users size={16} style={{ color: "var(--primary)" }} />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>
                {usage.contacts.count?.toLocaleString()} / {usage.contacts.limit?.toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                {usage.contacts.remaining?.toLocaleString()} slots available
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                <span>Knowledge Documents</span>
                <FileText size={16} style={{ color: "var(--warning)" }} />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>
                {usage.documents.count} / {usage.documents.limit}
              </div>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                Uploaded for AI vector grounding
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                <span>Team Seats</span>
                <UserCheck size={16} style={{ color: "var(--primary)" }} />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>
                {usage.staff.count} / {usage.staff.limit}
              </div>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                Active members & pending invites
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CRM Highlights */}
      <div>
        <h2 style={{ fontSize: '0.9rem', fontWeight: 600, color: "var(--text-muted)", textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>
          CRM Pipeline & Lead Engagement
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(14rem, 1fr))', gap: '1rem' }}>
          <div className="card">
            <div style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Pipeline Value</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--primary)", marginTop: '0.25rem' }}>
              ₹{crmMetrics?.pipeline_value ? Number(crmMetrics.pipeline_value).toLocaleString() : '0'}
            </div>
            <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
              {crmMetrics?.open_deals_count || 0} active deals in progress
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Total Contacts</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", marginTop: '0.25rem' }}>
              {crmMetrics?.total_contacts || 0}
            </div>
            <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
              Across {crmMetrics?.total_companies || 0} companies
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Pending Activities</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--warning)", marginTop: '0.25rem' }}>
              {crmMetrics?.pending_activities_count || 0}
            </div>
            <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
              {crmMetrics?.overdue_activities_count || 0} overdue follow-ups
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Recent Bookings</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--primary)", marginTop: '0.25rem' }}>
              {crmMetrics?.recent_bookings_count || 0}
            </div>
            <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
              Scheduled consultations
            </div>
          </div>
        </div>
      </div>

      {/* Actionable Follow-ups */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Urgent Tasks & Follow-ups</h3>
          <button onClick={() => onNavigate('/app/tasks')} className="btn btn-sm btn-secondary">
            View All Tasks <ArrowRight size={14} />
          </button>
        </div>

        {recentActivities.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem 1rem', color: "var(--text-muted)", fontSize: '0.875rem' }}>
            No pending tasks. Great job!
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {recentActivities.map((act) => (
              <div
                key={act.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.75rem 1rem',
                  backgroundColor: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: '0.5rem',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 600, color: "var(--text-main)" }}>{act.title}</div>
                  <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                    Customer: {act.customer_name || 'N/A'} • Assigned to: {act.assigned_to || 'Team'}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`badge ${act.priority === 'HIGH' ? 'badge-red' : 'badge-amber'}`}>
                    {act.priority}
                  </span>
                  <span className="badge badge-gray">{act.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
