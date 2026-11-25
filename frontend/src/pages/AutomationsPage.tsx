import { Modal } from '../components/Modal';
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ToggleLeft, ToggleRight, History, Sparkles } from 'lucide-react';

interface AutomationRule {
  id: number;
  name: string;
  description: string;
  trigger_type: string;
  trigger_display: string;
  conditions: Record<string, any>;
  action_type: string;
  action_display: string;
  action_config: Record<string, any>;
  is_active: boolean;
  execution_count: number;
}

interface AutomationLog {
  id: number;
  rule_id: number;
  event: string;
  status: string;
  details: Record<string, any>;
  executed_at: string;
}

export const AutomationsPage: React.FC = () => {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [logs, setLogs] = useState<AutomationLog[]>([]);
  const [triggers, setTriggers] = useState<{ value: string; label: string }[]>([]);
  const [actions, setActions] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [dryRunRule, setDryRunRule] = useState<AutomationRule | null>(null);
  const [dryRunResult, setDryRunResult] = useState<any>(null);
  const [settings, setSettings] = useState<any>({
    business_hours: { enabled: false, timezone: 'Asia/Kolkata', days: {} },
    currently_open: true,
    after_hours_auto_reply: '',
    greeting_auto_reply: '',
    auto_assign_inbound: false,
    no_response_followup_minutes: 0,
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsNotice, setSettingsNotice] = useState('');
  const [newRule, setNewRule] = useState({ name: '', trigger_type: 'lead.created', action_type: 'ASSIGN_STAFF', task_title: '' });

  const fetchAutomations = async () => {
    try {
      setLoading(true);
      const [res, settingsRes] = await Promise.all([
        api.get('/api/crm/automations/'),
        api.get('/api/crm/automations/settings/').catch(() => ({ data: null })),
      ]);
      setRules(res.data.rules || []);
      setLogs(res.data.recent_logs || []);
      setTriggers(res.data.triggers || []);
      setActions(res.data.actions || []);
      if (settingsRes?.data) setSettings(settingsRes.data);
    } catch (err) {
      console.error('Failed to load automations', err);
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingSettings(true);
      setSettingsNotice('');
      const res = await api.post('/api/crm/automations/settings/', {
        business_hours: settings.business_hours,
        after_hours_auto_reply: settings.after_hours_auto_reply,
        greeting_auto_reply: settings.greeting_auto_reply,
        auto_assign_inbound: settings.auto_assign_inbound,
        no_response_followup_minutes: Number(settings.no_response_followup_minutes || 0),
      });
      setSettings(res.data);
      setSettingsNotice('Business hours & operational automation rules saved.');
    } catch (err: any) {
      setSettingsNotice(err?.response?.data?.error || 'Could not save automation settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRule.name.trim()) return;
    try {
      await api.post('/api/crm/automations/', {
        name: newRule.name.trim(),
        trigger_type: newRule.trigger_type,
        action_type: newRule.action_type,
        action_config: newRule.task_title ? { task_title: newRule.task_title, reply_text: newRule.task_title } : {},
      });
      setNewRule({ name: '', trigger_type: 'lead.created', action_type: 'ASSIGN_STAFF', task_title: '' });
      fetchAutomations();
    } catch (err) {
      console.error('Failed to create automation rule', err);
    }
  };

  useEffect(() => {
    fetchAutomations();
  }, []);

  const toggleRule = async (ruleId: number) => {
    try {
      await api.post(`/api/crm/automations/${ruleId}/toggle/`);
      setRules((prev) =>
        prev.map((r) => (r.id === ruleId ? { ...r, is_active: !r.is_active } : r))
      );
    } catch (err) {
      console.error('Failed to toggle rule', err);
    }
  };

  const handleDryRun = async (rule: AutomationRule) => {
    setDryRunRule(rule);
    setDryRunResult(null);
    try {
      const res = await api.post(`/api/crm/automations/${rule.id}/dry-run/`, {
        sample_context: rule.conditions || {},
      });
      setDryRunResult(res.data);
    } catch (err) {
      setDryRunResult({ error: 'Dry run failed' });
    }
  };

  return (
    <div style={{ padding: '1.75rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)", margin: 0 }}>Workflow Automation</h1>
        <p style={{ color: "var(--text-muted)", fontSize: '0.88rem', margin: '0.25rem 0 0' }}>
          Bounded, tenant-scoped workflow rules executing automatic task assignment, onboarding triggers, and escalations.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1.5rem', marginBottom: '2rem' }}>
        <form onSubmit={saveSettings} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', padding: '1.25rem', display: 'grid', gap: '0.85rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Business Hours, Away Reply &amp; Follow-up SLA</h2>
              <span style={{ fontSize: '0.8rem', color: settings.currently_open ? 'var(--primary)' : 'var(--warning)' }}>
                Current schedule state: {settings.currently_open ? 'Open / Active Hours' : 'Outside Business Hours'}
              </span>
            </div>
            <button type="submit" disabled={savingSettings} className="btn btn-primary btn-sm">
              {savingSettings ? 'Saving...' : 'Save Operational Settings'}
            </button>
          </div>
          {settingsNotice && <div style={{ fontSize: '0.82rem', color: 'var(--primary)' }}>{settingsNotice}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.85rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.88rem', fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={!!settings.business_hours?.enabled}
                onChange={(e) => setSettings({ ...settings, business_hours: { ...settings.business_hours, enabled: e.target.checked } })}
              />
              Enforce Business Hours Schedule
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.88rem', fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={!!settings.auto_assign_inbound}
                onChange={(e) => setSettings({ ...settings, auto_assign_inbound: e.target.checked })}
              />
              Auto-Assign Human Handoffs Round-Robin
            </label>
            <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.82rem' }}>
              No-Response Follow-Up Timer (minutes, 0 = off)
              <input
                type="number"
                min={0}
                max={10080}
                className="input-field"
                value={settings.no_response_followup_minutes || 0}
                onChange={(e) => setSettings({ ...settings, no_response_followup_minutes: Number(e.target.value) })}
              />
            </label>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.85rem' }}>
            <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.82rem' }}>
              Away Auto-Reply (sent outside business hours)
              <textarea
                rows={2}
                className="input-field"
                placeholder="Thanks for messaging! Our team is offline and will reply next business day."
                value={settings.after_hours_auto_reply || ''}
                onChange={(e) => setSettings({ ...settings, after_hours_auto_reply: e.target.value })}
              />
            </label>
            <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.82rem' }}>
              Optional Welcome / Greeting Text
              <textarea
                rows={2}
                className="input-field"
                placeholder="Welcome to our business! How can we help today?"
                value={settings.greeting_auto_reply || ''}
                onChange={(e) => setSettings({ ...settings, greeting_auto_reply: e.target.value })}
              />
            </label>
          </div>
        </form>

        <form onSubmit={handleCreateRule} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', padding: '1rem 1.25rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'end' }}>
          <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.8rem', flex: '1 1 12rem' }}>
            Rule Name
            <input className="input-field" required placeholder="e.g. Auto-assign new leads" value={newRule.name} onChange={(e) => setNewRule({ ...newRule, name: e.target.value })} />
          </label>
          <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.8rem' }}>
            Trigger
            <select className="input-field" value={newRule.trigger_type} onChange={(e) => setNewRule({ ...newRule, trigger_type: e.target.value })}>
              {(triggers.length ? triggers : [{ value: 'lead.created', label: 'New Enquiry' }, { value: 'conversation.after_hours', label: 'Outside Business Hours' }, { value: 'conversation.no_response', label: 'Unanswered Chat Follow-up' }]).map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.8rem' }}>
            Action
            <select className="input-field" value={newRule.action_type} onChange={(e) => setNewRule({ ...newRule, action_type: e.target.value })}>
              {(actions.length ? actions : [{ value: 'ASSIGN_STAFF', label: 'Assign Eligible Staff' }, { value: 'CREATE_TASK', label: 'Create Follow-up Task' }, { value: 'AUTO_REPLY', label: 'Send Automated WhatsApp Reply' }]).map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'grid', gap: '0.25rem', fontSize: '0.8rem', flex: '1 1 12rem' }}>
            Task / Reply Text (optional)
            <input className="input-field" placeholder="Task title or message text" value={newRule.task_title} onChange={(e) => setNewRule({ ...newRule, task_title: e.target.value })} />
          </label>
          <button type="submit" className="btn btn-primary btn-sm">Add Rule</button>
        </form>

        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: "1px solid var(--border)", fontWeight: 700, color: "var(--text-main)" }}>
            Active Automation Rules
          </div>

          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading automation rules...</div>
          ) : rules.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>No automation rules configured yet.</div>
          ) : (
            <div>
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  style={{
                    padding: '1.25rem',
                    borderBottom: "1px solid var(--border)",
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '1rem' }}>{rule.name}</span>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '12px',
                          backgroundColor: rule.is_active ? "var(--primary-light)" : "var(--bg-card-hover)",
                          color: rule.is_active ? "var(--primary)" : "var(--text-muted)",
                        }}
                      >
                        {rule.is_active ? 'Active' : 'Paused'}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.84rem', color: "var(--text-muted)", marginTop: '0.35rem' }}>
                      <strong style={{ color: "var(--text-main)" }}>Trigger:</strong> {rule.trigger_display} &rarr;{' '}
                      <strong style={{ color: "var(--text-main)" }}>Action:</strong> {rule.action_display}
                    </div>

                    {rule.description && (
                      <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginTop: '0.2rem' }}>{rule.description}</div>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <button
                      onClick={() => handleDryRun(rule)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        backgroundColor: "var(--bg-card-hover)",
                        color: "var(--text-main)",
                        border: "1px solid var(--border)",
                        borderRadius: '6px',
                        padding: '0.4rem 0.75rem',
                        cursor: 'pointer',
                        fontSize: '0.8rem',
                      }}
                    >
                      <Sparkles size={14} color="#11b76d" /> Dry Run Preview
                    </button>

                    <button
                      onClick={() => toggleRule(rule.id)}
                      style={{
                        backgroundColor: 'transparent',
                        border: 'none',
                        color: rule.is_active ? "var(--primary)" : "var(--text-muted)",
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                      title={rule.is_active ? 'Pause Rule' : 'Enable Rule'}
                    >
                      {rule.is_active ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Execution Logs */}
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: "1px solid var(--border)", fontWeight: 700, color: "var(--text-main)", display: 'flex', alignItems: 'center', gap: '6px' }}>
            <History size={16} /> Recent Execution Audit Trail
          </div>

          {logs.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>No automation runs recorded yet.</div>
          ) : (
            <div style={{ fontSize: '0.85rem' }}>
              {logs.map((log) => (
                <div
                  key={log.id}
                  style={{
                    padding: '0.75rem 1.25rem',
                    borderBottom: "1px solid var(--border)",
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{log.event}</span>
                    <span style={{ color: "var(--text-muted)", marginLeft: '8px' }}>
                      {new Date(log.executed_at).toLocaleTimeString()}
                    </span>
                  </div>

                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      backgroundColor: log.status === 'SUCCESS' ? "var(--primary-light)" : '#fff0ed',
                      color: log.status === 'SUCCESS' ? "var(--primary)" : "var(--danger)",
                    }}
                  >
                    {log.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Dry Run Modal */}
      {dryRunRule && (
        <Modal title={`Dry Run Simulation: ${dryRunRule.name}`} onClose={() => setDryRunRule(null)} maxWidth="540px" zIndex={50} style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: '8px',
              padding: '1.75rem',
              maxWidth: '540px',
              width: '90%',
            }}>

            {dryRunResult ? (
              <pre
                style={{
                  backgroundColor: "var(--bg-card)",
                  padding: '1rem',
                  borderRadius: '6px',
                  color: "var(--primary)",
                  fontSize: '0.8rem',
                  overflowX: 'auto',
                }}
              >
                {JSON.stringify(dryRunResult, null, 2)}
              </pre>
            ) : (
              <div style={{ color: "var(--text-muted)" }}>Simulating action...</div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
              <button
                onClick={() => setDryRunRule(null)}
                style={{
                  backgroundColor: "var(--bg-card-hover)",
                  color: "var(--text-main)",
                  border: "1px solid var(--border)",
                  borderRadius: '6px',
                  padding: '0.45rem 1rem',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>

        </Modal>
      )}
    </div>
  );
};
