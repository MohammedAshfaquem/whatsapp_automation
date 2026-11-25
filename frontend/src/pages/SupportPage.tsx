import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { LifeBuoy, CheckSquare } from 'lucide-react';

interface SupportTicket {
  id: number;
  ticket_number: string;
  contact_id: number;
  contact_name: string;
  contact_phone: string;
  subject: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  assigned_to: string;
  response_target_hours: number;
  created_at: string;
}

interface OnboardingChecklist {
  id: number;
  title: string;
  deal_title: string;
  contact_name: string;
  is_completed: boolean;
  target_date: string;
  tasks: Array<{
    id: number;
    title: string;
    order: number;
    is_done: boolean;
  }>;
}

export const SupportPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'tickets' | 'onboarding'>('tickets');
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [checklists, setChecklists] = useState<OnboardingChecklist[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [tRes, oRes] = await Promise.all([
        api.get('/api/crm/tickets/'),
        api.get('/api/crm/onboarding/'),
      ]);
      setTickets(tRes.data.tickets);
      setChecklists(oRes.data.checklists);
    } catch (err) {
      console.error('Failed to load support data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const toggleTask = async (taskId: number) => {
    try {
      await api.post(`/api/crm/onboarding/tasks/${taskId}/toggle/`);
      fetchData();
    } catch (err) {
      console.error('Failed to toggle task', err);
    }
  };

  return (
    <div style={{ padding: '1.75rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", margin: 0 }}>Customer Support & Onboarding</h1>
          <p style={{ color: "var(--text-muted)", fontSize: '0.88rem', margin: '0.25rem 0 0' }}>
            Multi-agent customer support tickets, response targets, and post-sale onboarding delivery.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '6px', padding: '3px' }}>
          <button
            onClick={() => setActiveTab('tickets')}
            style={{
              padding: '0.4rem 0.85rem',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: activeTab === 'tickets' ? "var(--primary)" : 'transparent',
              color: activeTab === 'tickets' ? '#ffffff' : "var(--text-muted)",
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Support Tickets ({tickets.length})
          </button>
          <button
            onClick={() => setActiveTab('onboarding')}
            style={{
              padding: '0.4rem 0.85rem',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: activeTab === 'onboarding' ? "var(--primary)" : 'transparent',
              color: activeTab === 'onboarding' ? '#ffffff' : "var(--text-muted)",
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Post-Sale Onboarding ({checklists.length})
          </button>
        </div>
      </div>

      {activeTab === 'tickets' ? (
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: "1px solid var(--border)", fontWeight: 700, color: "var(--text-main)" }}>
            Customer Support Tickets
          </div>

          {loading ? (
            <div style={{ padding: '2.5rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading tickets...</div>
          ) : tickets.length === 0 ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: "var(--text-muted)" }}>
              <LifeBuoy size={36} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
              <div style={{ fontWeight: 600, color: "var(--text-muted)" }}>No active support tickets</div>
              <div style={{ fontSize: '0.82rem', marginTop: '0.25rem' }}>Customer issues logged from WhatsApp or portal appear here.</div>
            </div>
          ) : (
            <div>
              {tickets.map((t) => (
                <div
                  key={t.id}
                  style={{
                    padding: '1.15rem 1.25rem',
                    borderBottom: "1px solid var(--border)",
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 700, color: "var(--primary)", fontSize: '0.85rem' }}>{t.ticket_number}</span>
                      <span style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '0.95rem' }}>{t.subject}</span>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                      Customer: <strong>{t.contact_name}</strong> ({t.contact_phone}) • Owner: @{t.assigned_to} • SLA: {t.response_target_hours}h
                    </div>

                    <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>{t.description}</div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: t.priority === 'URGENT' ? '#fff0ed' : "var(--bg-card-hover)",
                        color: t.priority === 'URGENT' ? "var(--danger)" : "var(--text-main)",
                      }}
                    >
                      {t.priority}
                    </span>
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: t.status === 'RESOLVED' ? "var(--primary-light)" : '#e5f6ec',
                        color: t.status === 'RESOLVED' ? "var(--primary)" : "var(--primary)",
                      }}
                    >
                      {t.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {loading ? (
            <div style={{ padding: '2.5rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading onboarding checklists...</div>
          ) : checklists.length === 0 ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: "var(--text-muted)", backgroundColor: "var(--bg-card)", borderRadius: '8px', border: "1px solid var(--border)" }}>
              <CheckSquare size={36} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
              <div style={{ fontWeight: 600, color: "var(--text-muted)" }}>No onboarding checklists</div>
              <div style={{ fontSize: '0.82rem', marginTop: '0.25rem' }}>Won deals automatically generate post-sale onboarding workflows.</div>
            </div>
          ) : (
            checklists.map((c) => (
              <div
                key={c.id}
                style={{
                  backgroundColor: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: '8px',
                  padding: '1.25rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: "var(--text-main)" }}>{c.title}</h3>
                    <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginTop: '2px' }}>
                      Linked Deal: {c.deal_title || 'N/A'} • Contact: {c.contact_name || 'N/A'}
                    </div>
                  </div>

                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '3px 10px',
                      borderRadius: '12px',
                      backgroundColor: c.is_completed ? "var(--primary-light)" : '#e5f6ec',
                      color: c.is_completed ? "var(--primary)" : "var(--primary)",
                    }}
                  >
                    {c.is_completed ? 'Completed' : 'In Progress'}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {c.tasks.map((task) => (
                    <div
                      key={task.id}
                      onClick={() => toggleTask(task.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '0.5rem 0.75rem',
                        backgroundColor: task.is_done ? '#edf7f1' : "var(--bg-card-hover)",
                        border: "1px solid var(--border)",
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                      }}
                    >
                      <input type="checkbox" checked={task.is_done} readOnly style={{ cursor: 'pointer' }} />
                      <span style={{ textDecoration: task.is_done ? 'line-through' : 'none', color: task.is_done ? "var(--text-muted)" : "var(--text-main)" }}>
                        {task.title}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
