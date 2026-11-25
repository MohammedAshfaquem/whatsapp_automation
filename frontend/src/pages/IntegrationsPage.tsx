import { Modal } from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import {
  Plug,
  Webhook,
  Calendar,
  Layers,
  ShoppingBag,
  Plus,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

interface ConnectorItem {
  type: string;
  name: string;
  status: string;
  doc: string;
}

interface WebhookEndpointItem {
  id: number;
  target_url: string;
  subscribed_events: string[];
  is_active: boolean;
  created_at: string;
}

interface DeliveryLogItem {
  id: number;
  event_type: string;
  status_code: number;
  is_success: boolean;
  attempts: number;
  response: string;
  created_at: string;
}

export const IntegrationsPage: React.FC = () => {
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [endpoints, setEndpoints] = useState<WebhookEndpointItem[]>([]);
  const [deliveries, setDeliveries] = useState<DeliveryLogItem[]>([]);

  // New Webhook Endpoint Modal
  const [showAddWebhook, setShowAddWebhook] = useState(false);
  const [targetUrl, setTargetUrl] = useState('');
  const [subscribedEvents, setSubscribedEvents] = useState('lead.created, deal.won, ticket.created');
  const [savingWebhook, setSavingWebhook] = useState(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [intRes, hookRes] = await Promise.all([
        fetchApi<{ connectors: ConnectorItem[] }>('/api/crm/integrations/'),
        fetchApi<{ endpoints: WebhookEndpointItem[]; recent_deliveries: DeliveryLogItem[] }>('/api/crm/webhooks/'),
      ]);
      setConnectors(intRes.connectors || []);
      setEndpoints(hookRes.endpoints || []);
      setDeliveries(hookRes.recent_deliveries || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetUrl.trim()) return;

    try {
      setSavingWebhook(true);
      setWebhookError(null);
      const events = subscribedEvents
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      await fetchApi('/api/crm/webhooks/', {
        method: 'POST',
        body: JSON.stringify({
          target_url: targetUrl.trim(),
          subscribed_events: events.length > 0 ? events : ['*'],
        }),
      });

      setTargetUrl('');
      setShowAddWebhook(false);
      await loadData();
    } catch (err: any) {
      setWebhookError(err?.error || 'Failed to register webhook endpoint');
    } finally {
      setSavingWebhook(false);
    }
  };

  const getConnectorIcon = (type: string) => {
    switch (type) {
      case 'CALENDAR':
        return <Calendar size={20} style={{ color: "var(--primary)" }} />;
      case 'CRM_CONNECTOR':
        return <Layers size={20} style={{ color: "var(--warning)" }} />;
      case 'COMMERCE':
        return <ShoppingBag size={20} style={{ color: "var(--primary)" }} />;
      default:
        return <Plug size={20} style={{ color: "var(--primary)" }} />;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem', maxWidth: '80rem', margin: '0 auto' }}>
      {/* Header */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <Plug size={22} style={{ color: "var(--primary)" }} />
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Integration Centre</h1>
        </div>
        <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Connect third-party enterprise apps, synchronize calendars, and dispatch signed outbound webhooks.
        </p>
      </div>

      {/* External Connectors Grid */}
      <div>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.85rem' }}>
          Pre-built Connectors
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(20rem, 1fr))', gap: '1rem' }}>
          {connectors.map((c) => (
            <div key={c.type} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                  <div
                    style={{
                      padding: '0.5rem',
                      borderRadius: '0.375rem',
                      backgroundColor: "var(--bg-card)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    {getConnectorIcon(c.type)}
                  </div>
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: "var(--text-main)" }}>{c.name}</h3>
                    <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{c.type}</div>
                  </div>
                </div>
                <span
                  style={{
                    padding: '0.2rem 0.5rem',
                    borderRadius: '0.25rem',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    backgroundColor: c.status === 'CONNECTED' ? 'rgba(17, 183, 109, 0.2)' : "var(--bg-card-hover)",
                    color: c.status === 'CONNECTED' ? "var(--primary)" : "var(--text-muted)",
                  }}
                >
                  {c.status}
                </span>
              </div>
              <p style={{ fontSize: '0.825rem', color: "var(--text-muted)", flex: 1, margin: 0 }}>{c.doc}</p>
              <div style={{ paddingTop: '0.5rem', borderTop: "1px solid var(--border)" }}>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8rem', width: '100%', justifyContent: 'center' }}
                  onClick={() => alert(`Connector setup for ${c.name} requires tenant external API keys.`)}
                >
                  Configure Connector
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Webhooks Section */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Webhook size={18} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>Signed Outbound Webhooks</h2>
            </div>
            <p style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>
              Payloads are signed with HMAC-SHA256 (`X-Neoriz-Signature`) and guarded by SSRF validation.
            </p>
          </div>
          <button onClick={() => setShowAddWebhook(true)} className="btn btn-primary" style={{ fontSize: '0.85rem' }}>
            <Plus size={15} /> Add Endpoint
          </button>
        </div>

        {/* Endpoints Table */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {endpoints.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>
              No outbound webhook endpoints configured yet.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: "var(--bg-card)", borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                    <th style={{ padding: '0.75rem 1rem' }}>Destination URL</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Subscribed Events</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Registered</th>
                  </tr>
                </thead>
                <tbody>
                  {endpoints.map((ep) => (
                    <tr key={ep.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', color: "var(--primary)" }}>
                        {ep.target_url}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                          {ep.subscribed_events.map((ev, i) => (
                            <span
                              key={i}
                              style={{
                                backgroundColor: "var(--bg-card-hover)",
                                color: "var(--text-main)",
                                padding: '0.15rem 0.4rem',
                                borderRadius: '0.25rem',
                                fontSize: '0.7rem',
                              }}
                            >
                              {ev}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span
                          style={{
                            padding: '0.2rem 0.5rem',
                            borderRadius: '0.25rem',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            backgroundColor: ep.is_active ? 'rgba(17, 183, 109, 0.2)' : "var(--bg-card-hover)",
                            color: ep.is_active ? "var(--primary)" : "var(--text-muted)",
                          }}
                        >
                          {ep.is_active ? 'ACTIVE' : 'PAUSED'}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem', color: "var(--text-muted)" }}>
                        {new Date(ep.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Delivery Logs */}
        <div>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.5rem' }}>
            Recent Webhook Delivery Logs
          </h3>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {deliveries.length === 0 ? (
              <div style={{ padding: '1.5rem', textAlign: 'center', color: "var(--text-muted)", fontSize: '0.85rem' }}>
                No outbound webhook events dispatched recently.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ backgroundColor: "var(--bg-card)", borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                      <th style={{ padding: '0.6rem 0.85rem' }}>Event</th>
                      <th style={{ padding: '0.6rem 0.85rem' }}>Status</th>
                      <th style={{ padding: '0.6rem 0.85rem' }}>HTTP Code</th>
                      <th style={{ padding: '0.6rem 0.85rem' }}>Attempts</th>
                      <th style={{ padding: '0.6rem 0.85rem' }}>Response Snippet</th>
                      <th style={{ padding: '0.6rem 0.85rem' }}>Dispatched At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.map((l) => (
                      <tr key={l.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: '0.6rem 0.85rem', fontWeight: 600, color: "var(--text-main)" }}>{l.event_type}</td>
                        <td style={{ padding: '0.6rem 0.85rem' }}>
                          {l.is_success ? (
                            <span style={{ color: "var(--primary)", fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                              <CheckCircle2 size={13} /> DELIVERED
                            </span>
                          ) : (
                            <span style={{ color: "var(--danger)", fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                              <XCircle size={13} /> FAILED
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '0.6rem 0.85rem', fontFamily: 'monospace' }}>{l.status_code || '---'}</td>
                        <td style={{ padding: '0.6rem 0.85rem' }}>{l.attempts}</td>
                        <td style={{ padding: '0.6rem 0.85rem', fontFamily: 'monospace', color: "var(--text-muted)" }}>
                          {l.response || '(empty)'}
                        </td>
                        <td style={{ padding: '0.6rem 0.85rem', color: "var(--text-muted)" }}>
                          {new Date(l.created_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Webhook Modal */}
      {showAddWebhook && (
        <Modal title="Add Outbound Webhook Endpoint" onClose={() => setShowAddWebhook(false)} maxWidth="32rem" zIndex={50} className="card" style={{ width: '100%', maxWidth: '32rem', padding: '1.5rem' }}>

            {webhookError && (
              <div
                style={{
                  padding: '0.75rem',
                  borderRadius: '0.375rem',
                  marginBottom: '1rem',
                  fontSize: '0.85rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  color: "var(--danger)",
                }}
              >
                {webhookError}
              </div>
            )}

            <form onSubmit={handleCreateWebhook} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.35rem' }}>
                  Target Destination URL *
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://api.mycompany.com/webhooks/neoriz"
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  className="input"
                  style={{ width: '100%' }}
                />
                <span style={{ fontSize: '0.7rem', color: "var(--text-muted)", marginTop: '0.25rem', display: 'block' }}>
                  Loopback, internal, private LAN, and cloud metadata addresses are strictly blocked by SSRF firewall.
                </span>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: "var(--text-muted)", marginBottom: '0.35rem' }}>
                  Subscribed Event Topics (comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="lead.created, deal.won, ticket.created, *"
                  value={subscribedEvents}
                  onChange={(e) => setSubscribedEvents(e.target.value)}
                  className="input"
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowAddWebhook(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={savingWebhook} className="btn btn-primary">
                  {savingWebhook ? 'Registering...' : 'Register Endpoint'}
                </button>
              </div>
            </form>

        </Modal>
      )}
    </div>
  );
};
