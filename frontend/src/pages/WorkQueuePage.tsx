import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Clock, AlertTriangle, MessageSquare, CheckSquare, Flame, RefreshCw, UserCheck } from 'lucide-react';

interface QueueItem {
  id: number;
  type: string;
  title: string;
  contact_id?: number;
  contact_name?: string;
  phone?: string;
  last_message_at?: string;
  due_date?: string;
  priority?: string;
  stage_name?: string;
  amount?: string;
  currency?: string;
  owner?: string;
  assigned_to?: string;
}

interface WorkQueueData {
  summary: {
    unanswered_count: number;
    today_followups_count: number;
    overdue_count: number;
    stale_deals_count: number;
    no_action_deals_count: number;
    total_actionable: number;
  };
  unanswered_enquiries: QueueItem[];
  today_followups: QueueItem[];
  overdue_tasks: QueueItem[];
  stale_deals: QueueItem[];
  deals_without_action: QueueItem[];
}

interface WorkQueuePageProps {
  onNavigate?: (path: string) => void;
}

export const WorkQueuePage: React.FC<WorkQueuePageProps> = ({ onNavigate }) => {
  const [data, setData] = useState<WorkQueueData | null>(null);
  const [activeTab, setActiveTab] = useState<'unanswered' | 'today' | 'overdue' | 'stale' | 'no_action'>('unanswered');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const goTo = (path: string) => {
    if (onNavigate) {
      onNavigate(path);
    } else {
      window.location.href = path;
    }
  };

  const handleCompleteTask = async (taskId: number) => {
    try {
      await api.post(`/api/crm/activities/${taskId}/complete/`);
      fetchQueue();
    } catch (err) {
      setError('Could not complete this task. Please try again.');
    }
  };

  const fetchQueue = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/api/crm/work-queue/');
      setData(res);
    } catch (err) {
      setData(null);
      setError('Could not load the work queue. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const getActiveItems = (): QueueItem[] => {
    if (!data) return [];
    switch (activeTab) {
      case 'unanswered':
        return data.unanswered_enquiries;
      case 'today':
        return data.today_followups;
      case 'overdue':
        return data.overdue_tasks;
      case 'stale':
        return data.stale_deals;
      case 'no_action':
        return data.deals_without_action;
      default:
        return [];
    }
  };

  return (
    <div style={{ padding: '1.75rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", margin: 0 }}>Sales Work Queue</h1>
          <p style={{ color: "var(--text-muted)", fontSize: '0.88rem', margin: '0.25rem 0 0' }}>
            Actionable sales pipeline items, unanswered WhatsApp inquiries, and overdue follow-ups.
          </p>
        </div>
        <button
          onClick={fetchQueue}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            backgroundColor: "var(--bg-card-hover)",
            color: "var(--text-main)",
            border: "1px solid var(--border)",
            borderRadius: '6px',
            padding: '0.5rem 0.85rem',
            cursor: 'pointer',
            fontSize: '0.85rem',
          }}
        >
          <RefreshCw size={14} /> Refresh Queue
        </button>
      </div>

      {/* KPI Tabs Header */}
      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <div
            onClick={() => setActiveTab('unanswered')}
            style={{
              backgroundColor: activeTab === 'unanswered' ? "var(--primary-light)" : "var(--bg-card)",
              border: activeTab === 'unanswered' ? '2px solid #11b76d' : "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1rem',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontWeight: 600 }}>Unanswered Enquiries</span>
              <MessageSquare size={16} color="#11b76d" />
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", marginTop: '0.35rem' }}>
              {data.summary.unanswered_count}
            </div>
          </div>

          <div
            onClick={() => setActiveTab('today')}
            style={{
              backgroundColor: activeTab === 'today' ? "var(--primary-light)" : "var(--bg-card)",
              border: activeTab === 'today' ? '2px solid #11b76d' : "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1rem',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontWeight: 600 }}>Today's Follow-ups</span>
              <Clock size={16} color="#3b82f6" />
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", marginTop: '0.35rem' }}>
              {data.summary.today_followups_count}
            </div>
          </div>

          <div
            onClick={() => setActiveTab('overdue')}
            style={{
              backgroundColor: activeTab === 'overdue' ? '#fff0ed' : "var(--bg-card)",
              border: activeTab === 'overdue' ? '2px solid #ef4444' : "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1rem',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontWeight: 600 }}>Overdue Tasks</span>
              <AlertTriangle size={16} color="#ef4444" />
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", marginTop: '0.35rem' }}>
              {data.summary.overdue_count}
            </div>
          </div>

          <div
            onClick={() => setActiveTab('stale')}
            style={{
              backgroundColor: activeTab === 'stale' ? '#fff3dc' : "var(--bg-card)",
              border: activeTab === 'stale' ? '2px solid #f59e0b' : "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1rem',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontWeight: 600 }}>Stale Deals (&gt;7d)</span>
              <Flame size={16} color="#f59e0b" />
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", marginTop: '0.35rem' }}>
              {data.summary.stale_deals_count}
            </div>
          </div>

          <div
            onClick={() => setActiveTab('no_action')}
            style={{
              backgroundColor: activeTab === 'no_action' ? "var(--primary-light)" : "var(--bg-card)",
              border: activeTab === 'no_action' ? '2px solid #11b76d' : "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1rem',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontWeight: 600 }}>Deals Without Next Action</span>
              <CheckSquare size={16} color="#a855f7" />
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", marginTop: '0.35rem' }}>
              {data.summary.no_action_deals_count}
            </div>
          </div>
        </div>
      )}

      {/* Items List */}
      <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ padding: '1rem 1.25rem', borderBottom: "1px solid var(--border)", fontWeight: 700, color: "var(--text-main)", fontSize: '0.95rem' }}>
          {activeTab === 'unanswered' && 'Unanswered Customer Inquiries'}
          {activeTab === 'today' && "Today's Scheduled Follow-ups"}
          {activeTab === 'overdue' && 'Overdue Actions Requiring Immediate Attention'}
          {activeTab === 'stale' && 'Stale Opportunities Without Recent Activity'}
          {activeTab === 'no_action' && 'Active Deals Without Scheduled Next Activity'}
        </div>

        {error ? (<div role="alert" style={{ padding: '1rem', color: "var(--danger)" }}>{error}</div>) : loading ? (
          <div style={{ padding: '2.5rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading work queue...</div>
        ) : getActiveItems().length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: "var(--text-muted)" }}>
            <CheckSquare size={36} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
            <div style={{ fontWeight: 600, color: "var(--text-muted)" }}>Queue is completely clear!</div>
            <div style={{ fontSize: '0.82rem', marginTop: '0.25rem' }}>No pending items in this category.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {getActiveItems().map((item) => (
              <div
                key={`${item.type}-${item.id}`}
                style={{
                  padding: '1rem 1.25rem',
                  borderBottom: "1px solid var(--border)",
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '0.92rem' }}>{item.title}</div>
                  <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginTop: '0.2rem' }}>
                    {item.contact_name && `Contact: ${item.contact_name}`}
                    {item.phone && ` • Phone: ${item.phone}`}
                    {item.due_date && ` • Due: ${new Date(item.due_date).toLocaleString()}`}
                    {item.amount && ` • Value: ${item.currency || 'INR'} ${parseFloat(item.amount).toLocaleString()}`}
                    {item.stage_name && ` • Stage: ${item.stage_name}`}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                  {item.priority && (
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: item.priority === 'HIGH' ? '#fff0ed' : "var(--bg-card-hover)",
                        color: item.priority === 'HIGH' ? "var(--danger)" : "var(--text-main)",
                      }}
                    >
                      {item.priority}
                    </span>
                  )}
                  {item.owner && (
                    <span style={{ fontSize: '0.78rem', color: "var(--text-muted)", display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <UserCheck size={13} /> @{item.owner}
                    </span>
                  )}

                  {/* Contextual Action Buttons */}
                  {item.type === 'ENQUIRY' && (
                    <button
                      onClick={() => goTo('/app/inbox')}
                      className="btn btn-primary btn-sm"
                      style={{ fontSize: '0.78rem', padding: '0.35rem 0.65rem' }}
                    >
                      <MessageSquare size={13} /> Open Chat
                    </button>
                  )}

                  {(item.type === 'FOLLOW_UP_TODAY' || item.type === 'OVERDUE_TASK') && (
                    <div style={{ display: 'flex', gap: '0.35rem' }}>
                      <button
                        onClick={() => handleCompleteTask(item.id)}
                        className="btn btn-secondary btn-sm"
                        style={{ fontSize: '0.78rem', padding: '0.35rem 0.65rem' }}
                      >
                        <CheckSquare size={13} /> Done
                      </button>
                      <button
                        onClick={() => goTo('/app/tasks')}
                        className="btn btn-secondary btn-sm"
                        style={{ fontSize: '0.78rem', padding: '0.35rem 0.65rem' }}
                      >
                        View Tasks
                      </button>
                    </div>
                  )}

                  {(item.type === 'STALE_DEAL' || item.type === 'NO_NEXT_ACTION') && (
                    <button
                      onClick={() => goTo('/app/deals')}
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.78rem', padding: '0.35rem 0.65rem' }}
                    >
                      Open Deals
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
