import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { Layers, Users, MessageSquare, CalendarCheck, ShieldCheck, Activity, RefreshCw } from 'lucide-react';

export const PlatformDashboardPage: React.FC<{ onNavigate: (path: string) => void }> = ({ onNavigate }) => {
  const [metrics, setMetrics] = useState<any>(null);
  const [monitoring, setMonitoring] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    Promise.all([
      fetchApi('/api/platform/metrics/'),
      fetchApi('/api/platform/monitoring/'),
    ])
      .then(([metricsData, monitoringData]) => {
        setMetrics(metricsData);
        setMonitoring(monitoringData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <ShieldCheck size={20} style={{ color: "var(--primary)" }} />
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Super Admin</h1>
          </div>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Global SaaS platform health, provisioned business tenants, and subscription metrics.
          </p>
        </div>
        <button onClick={loadData} disabled={loading} className="btn btn-secondary" style={{ fontSize: '0.8rem' }}>
          <RefreshCw size={14} /> Refresh Health
        </button>
      </div>

      {/* Operational Health & Monitoring Alert */}
      {monitoring && (
        <div
          className="card"
          style={{
            borderLeft: `4px solid ${monitoring.overall_health === 'HEALTHY' ? '#11B76D' : '#f59e0b'}`,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={18} style={{ color: monitoring.overall_health === 'HEALTHY' ? "var(--primary)" : "var(--warning)" }} />
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: "var(--text-main)" }}>
                Operational Health Status: {monitoring.overall_health}
              </span>
            </div>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.5rem',
                borderRadius: '0.25rem',
                fontWeight: 700,
                backgroundColor: monitoring.overall_health === 'HEALTHY' ? 'rgba(17, 183, 109, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                color: monitoring.overall_health === 'HEALTHY' ? "var(--primary)" : "var(--warning)",
              }}
            >
              {monitoring.overall_health === 'HEALTHY' ? 'All Systems Nominal' : 'Attention Required'}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(11rem, 1fr))', gap: '0.75rem', marginTop: '0.25rem' }}>
            <div style={{ backgroundColor: "var(--bg-card)", padding: '0.65rem 0.85rem', borderRadius: '0.375rem', border: "1px solid var(--border)" }}>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>Stalled Leases</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: monitoring.stalled_leases_count > 0 ? "var(--danger)" : "var(--text-main)" }}>
                {monitoring.stalled_leases_count}
              </div>
            </div>
            <div style={{ backgroundColor: "var(--bg-card)", padding: '0.65rem 0.85rem', borderRadius: '0.375rem', border: "1px solid var(--border)" }}>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>Failed Deliveries</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: monitoring.failed_deliveries_count > 0 ? "var(--danger)" : "var(--text-main)" }}>
                {monitoring.failed_deliveries_count}
              </div>
            </div>
            <div style={{ backgroundColor: "var(--bg-card)", padding: '0.65rem 0.85rem', borderRadius: '0.375rem', border: "1px solid var(--border)" }}>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>Failed Automations</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: monitoring.failed_automations_count > 0 ? "var(--danger)" : "var(--text-main)" }}>
                {monitoring.failed_automations_count}
              </div>
            </div>
            <div style={{ backgroundColor: "var(--bg-card)", padding: '0.65rem 0.85rem', borderRadius: '0.375rem', border: "1px solid var(--border)" }}>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>Failed Webhooks</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: monitoring.failed_webhooks_count > 0 ? "var(--danger)" : "var(--text-main)" }}>
                {monitoring.failed_webhooks_count}
              </div>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(14rem, 1fr))', gap: '1rem' }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem' }}>
            <span>Total Tenants</span>
            <Layers size={16} style={{ color: "var(--primary)" }} />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: "var(--text-main)", marginTop: '0.35rem' }}>
            {metrics?.total_tenants || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: "var(--primary)", marginTop: '0.25rem' }}>
            {metrics?.active_tenants || 0} active workspaces
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem' }}>
            <span>Registered Users</span>
            <Users size={16} style={{ color: "var(--primary)" }} />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: "var(--text-main)", marginTop: '0.35rem' }}>
            {metrics?.total_users || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
            Across all workspaces
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem' }}>
            <span>Total Messages Processed</span>
            <MessageSquare size={16} style={{ color: "var(--warning)" }} />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: "var(--text-main)", marginTop: '0.35rem' }}>
            {metrics?.total_messages || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
            Inbound & outbound
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', color: "var(--text-muted)", fontSize: '0.8rem' }}>
            <span>Total Bookings</span>
            <CalendarCheck size={16} style={{ color: "var(--primary)" }} />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: "var(--text-main)", marginTop: '0.35rem' }}>
            {metrics?.total_bookings || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
            Consultation requests
          </div>
        </div>
      </div>

      <div className="card">
        <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '1rem' }}>
          Quick Platform Actions
        </h2>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => onNavigate('/app/platform/tenants')} className="btn btn-primary">
            <Layers size={15} /> Manage Business Tenants
          </button>
          <button onClick={() => onNavigate('/app/platform/matrix')} className="btn btn-secondary">
            View Access Matrix & Plans
          </button>
          <button onClick={() => onNavigate('/app/platform/audit')} className="btn btn-secondary">
            Review Audit Logs
          </button>
        </div>
      </div>
    </div>
  );
};
