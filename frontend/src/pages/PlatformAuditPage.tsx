import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';

export const PlatformAuditPage: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApi<{ logs: any[] }>('/api/platform/audit/')
      .then((data) => setLogs(data.logs || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Platform Security Audit Trail</h1>
        <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Immutable log of privilege escalations, tenant status changes, inspection events, and invitations.
        </p>
      </div>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Actor</th>
              <th>Target Workspace</th>
              <th>Action</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading audit trail...' : 'No audit entries recorded.'}
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id}>
                  <td style={{ color: "var(--text-muted)", fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td style={{ fontWeight: 600 }}>@{log.actor__username || 'system'}</td>
                  <td>
                    {log.tenant__name ? (
                      <span className="badge badge-gray">{log.tenant__name}</span>
                    ) : (
                      <span className="badge badge-blue">Platform</span>
                    )}
                  </td>
                  <td>
                    <span className="badge badge-amber">{log.action}</span>
                  </td>
                  <td style={{ color: "var(--text-main)" }}>{log.summary}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
