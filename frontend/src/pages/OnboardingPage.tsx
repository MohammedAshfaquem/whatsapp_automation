import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { CheckCircle2, Circle, Bot, Send, ShieldCheck } from 'lucide-react';

interface OnboardingStepInfo {
  id: string;
  title: string;
  completed: boolean;
}

interface ChecklistItem {
  key: string;
  title: string;
  completed: boolean;
  optional: boolean;
  href: string;
}

interface OnboardingStatus {
  current_step: string;
  is_completed: boolean;
  completed_steps_count: number;
  steps: OnboardingStepInfo[];
  checklist?: {
    items: ChecklistItem[];
    completed_count: number;
    total_count: number;
    required_completed_count: number;
    required_total_count: number;
    all_required_done: boolean;
  } | null;
}

interface TestResult {
  success: boolean;
  query: string;
  response: string;
  grounding: string[];
  shop_name: string;
  tested_at: string;
}

export const OnboardingPage: React.FC = () => {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [testQuery, setTestQuery] = useState('What services do you provide?');
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      setError(null);
      const res = await fetchApi<OnboardingStatus>('/api/onboarding/status/');
      setStatus(res);
    } catch (err: any) {
      setError(err?.error || 'Failed to load onboarding status.');
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleTestAssistant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testQuery.trim()) return;
    try {
      setTesting(true);
      setError(null);
      const res = await fetchApi<{ status: string; result: TestResult }>('/api/onboarding/test-assistant/', {
        method: 'POST',
        body: JSON.stringify({ query: testQuery.trim() }),
      });
      setTestResult(res.result);
      loadStatus();
    } catch (err: any) {
      setError(err?.error || 'Simulation test failed.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '64rem', margin: '0 auto' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Tenant Workspace Onboarding</h1>
        <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Guided 8-step setup for grounding your AI assistant, configuring Meta Cloud WhatsApp credentials, and reviewing live readiness.
        </p>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Live 8-Item Client Setup Checklist */}
      {status?.checklist && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>Client Launch Checklist</h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Real-time verification across account security, plan entitlement, and Meta Cloud WhatsApp readiness.
              </p>
            </div>
            <span className="badge badge-green">
              {status.checklist.required_completed_count} of {status.checklist.required_total_count} Required Complete
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(15rem, 1fr))', gap: '0.65rem' }}>
            {status.checklist.items.map((item) => (
              <a
                key={item.key}
                href={item.href}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                  padding: '0.7rem 0.85rem',
                  borderRadius: '0.5rem',
                  textDecoration: 'none',
                  backgroundColor: item.completed ? 'rgba(17, 183, 109, 0.08)' : 'var(--bg-card)',
                  border: `1px solid ${item.completed ? 'rgba(17, 183, 109, 0.35)' : 'var(--border)'}`,
                  color: 'var(--text-main)',
                }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.84rem', fontWeight: 600 }}>
                  {item.completed ? <CheckCircle2 size={16} style={{ color: 'var(--primary)' }} /> : <Circle size={16} style={{ color: 'var(--text-muted)' }} />}
                  {item.title}
                </span>
                <span style={{ fontSize: '0.72rem', fontWeight: 600, color: item.completed ? '#047857' : '#64748b' }}>
                  {item.completed ? 'Done' : item.optional ? 'Optional' : 'Setup'}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* 8-Step Progress Bar */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>Setup Progress</h2>
          <span className="badge badge-green">
            {status?.completed_steps_count || 0} of {status?.steps.length || 8} Steps Completed
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(12rem, 1fr))', gap: '0.75rem' }}>
          {status?.steps.map((s, idx) => (
            <div
              key={s.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.75rem',
                backgroundColor: s.completed ? 'rgba(17, 183, 109, 0.08)' : "var(--bg-card)",
                border: `1px solid ${s.completed ? 'rgba(17, 183, 109, 0.3)' : "var(--border)"}`,
                borderRadius: '0.5rem',
              }}
            >
              {s.completed ? (
                <CheckCircle2 size={18} style={{ color: "var(--primary)", flexShrink: 0 }} />
              ) : (
                <Circle size={18} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
              )}
              <div>
                <div style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>Step {idx + 1}</div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: s.completed ? "var(--text-main)" : "var(--text-muted)" }}>
                  {s.title}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Interactive Synthetic Assistant Test Sandbox */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <Bot size={20} style={{ color: "var(--primary)" }} />
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>
            Live Synthetic Assistant Simulation Sandbox
          </h2>
        </div>
        <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", lineHeight: 1.5, marginBottom: '1.25rem' }}>
          Test how the AI assistant responds to customer inquiries using your business profile, service offerings, and indexed FAQs.
          Runs strictly in an isolated simulation sandbox: zero live WhatsApp outbound deliveries are sent and zero unintended customer deal records are created.
        </p>

        <form onSubmit={handleTestAssistant} style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <input
            type="text"
            className="input-field"
            value={testQuery}
            onChange={(e) => setTestQuery(e.target.value)}
            placeholder="Type a test customer message (e.g. What services do you offer?)"
            style={{ flex: 1 }}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={testing || !testQuery.trim()}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Send size={14} className={testing ? 'spin' : ''} />
            {testing ? 'Simulating...' : 'Run Simulation'}
          </button>
        </form>

        {testResult && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>Test Prompt:</div>
              <div style={{ fontSize: '0.9rem', color: "var(--text-main)", fontWeight: 500 }}>"{testResult.query}"</div>
            </div>

            <div>
              <div style={{ fontSize: '0.75rem', color: "var(--primary)", fontWeight: 600, marginBottom: '0.25rem' }}>
                Grounding Knowledge Sources Used:
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8rem', color: "var(--text-muted)" }}>
                {testResult.grounding.map((g, idx) => (
                  <li key={idx}>{g}</li>
                ))}
              </ul>
            </div>

            <div>
              <div style={{ fontSize: '0.75rem', color: "var(--primary)", fontWeight: 600, marginBottom: '0.25rem' }}>
                AI Assistant Response:
              </div>
              <div style={{ padding: '0.85rem', backgroundColor: "var(--bg-card)", borderLeft: '3px solid #11B76D', borderRadius: '0.25rem', fontSize: '0.9rem', color: "var(--text-main)", lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {testResult.response}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Readiness Review Card */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <ShieldCheck size={18} style={{ color: "var(--primary)" }} />
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>
            Production Launch Readiness
          </h2>
        </div>
        <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", lineHeight: 1.5 }}>
          Once your business profile, services catalog, and Meta Cloud API credentials are saved and verified, your workspace is fully prepared for live WhatsApp customer conversations.
        </p>
      </div>
    </div>
  );
};
