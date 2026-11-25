import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, AlertTriangle, Save, Database, RefreshCw } from 'lucide-react';

interface SystemSettingsData {
  verification_expiry_minutes: number;
  resend_cooldown_seconds: number;
  resend_max_per_hour: number;
  support_alert_email: string;
  support_escalation_minutes: number;
  global_outbound_paused: boolean;
  global_outbound_pause_reason: string;
  maintenance_mode: boolean;
  maintenance_message: string;
  last_backup_verified_at: string | null;
  last_backup_note: string;
}

export const PlatformSystemSettingsPage: React.FC = () => {
  const { user } = useAuth();
  const [form, setForm] = useState<SystemSettingsData>({
    verification_expiry_minutes: 30,
    resend_cooldown_seconds: 60,
    resend_max_per_hour: 5,
    support_alert_email: 'support@neorizsolutions.com',
    support_escalation_minutes: 10,
    global_outbound_paused: false,
    global_outbound_pause_reason: '',
    maintenance_mode: false,
    maintenance_message: 'Scheduled maintenance is in progress. Please try again shortly.',
    last_backup_verified_at: null,
    last_backup_note: '',
  });
  const [backupNote, setBackupNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const platformRole = (user as any)?.platform_role || (user?.is_superuser ? 'SUPER_ADMIN' : '');
  const canEdit = platformRole === 'SUPER_ADMIN' || (!platformRole && user?.is_superuser);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await fetchApi<SystemSettingsData>('/api/platform/system-settings/');
      setForm(res);
    } catch (e: any) {
      setError(e?.error || 'Unable to load platform system settings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const res = await fetchApi<SystemSettingsData>('/api/platform/system-settings/', {
        method: 'POST',
        body: JSON.stringify(form),
      });
      setForm(res);
      setSuccess('Platform system settings updated.');
    } catch (err: any) {
      setError(err?.error || 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleRecordBackup = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const res = await fetchApi<SystemSettingsData>('/api/platform/system-settings/', {
        method: 'POST',
        body: JSON.stringify({
          record_backup_verification: true,
          backup_note: backupNote || 'Verified restore & backup snapshot',
        }),
      });
      setForm(res);
      setBackupNote('');
      setSuccess('Operator backup verification recorded.');
    } catch (err: any) {
      setError(err?.error || 'Could not record backup verification.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={{ maxWidth: '72rem', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>System Settings &amp; Safeguards</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Global verification policies, SLA thresholds, outbound kill-switch, maintenance mode, and backup verification log.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={loadSettings} disabled={loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && <div role="alert" className="card" style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}>{error}</div>}
      {success && <div role="status" className="card" style={{ color: 'var(--primary)', borderColor: 'var(--primary)' }}>{success}</div>}
      {!canEdit && <div className="card" style={{ color: 'var(--text-muted)' }}>Read-only view: SUPER_ADMIN role is required to save policy changes.</div>}

      <form onSubmit={handleSave} style={{ display: 'grid', gap: '1.25rem' }}>
        <div className="card" style={{ display: 'grid', gap: '1rem' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={17} style={{ color: 'var(--primary)' }} /> Verification &amp; SLA Policies
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Verification expiry (minutes)
              <input className="input-field" type="number" min={5} max={1440} disabled={!canEdit} value={form.verification_expiry_minutes} onChange={e => setForm({ ...form, verification_expiry_minutes: Number(e.target.value) })} />
            </label>
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Resend cooldown (seconds)
              <input className="input-field" type="number" min={15} max={600} disabled={!canEdit} value={form.resend_cooldown_seconds} onChange={e => setForm({ ...form, resend_cooldown_seconds: Number(e.target.value) })} />
            </label>
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Max verification emails / hour
              <input className="input-field" type="number" min={1} max={50} disabled={!canEdit} value={form.resend_max_per_hour} onChange={e => setForm({ ...form, resend_max_per_hour: Number(e.target.value) })} />
            </label>
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Support escalation SLA (minutes)
              <input className="input-field" type="number" min={1} max={120} disabled={!canEdit} value={form.support_escalation_minutes} onChange={e => setForm({ ...form, support_escalation_minutes: Number(e.target.value) })} />
            </label>
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Emergency escalation email
              <input className="input-field" type="email" disabled={!canEdit} value={form.support_alert_email} onChange={e => setForm({ ...form, support_alert_email: e.target.value })} />
            </label>
          </div>
        </div>

        <div className="card" style={{ display: 'grid', gap: '1rem' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={17} style={{ color: 'var(--warning)' }} /> Emergency &amp; Maintenance Controls
          </h2>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontWeight: 600 }}>
            <input type="checkbox" disabled={!canEdit} checked={form.global_outbound_paused} onChange={e => setForm({ ...form, global_outbound_paused: e.target.checked })} />
            Pause All Outbound WhatsApp Sending Globally
          </label>
          {form.global_outbound_paused && (
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Global outbound pause reason
              <input className="input-field" maxLength={255} disabled={!canEdit} value={form.global_outbound_pause_reason} onChange={e => setForm({ ...form, global_outbound_pause_reason: e.target.value })} placeholder="e.g. Meta webhook maintenance window" />
            </label>
          )}
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontWeight: 600 }}>
            <input type="checkbox" disabled={!canEdit} checked={form.maintenance_mode} onChange={e => setForm({ ...form, maintenance_mode: e.target.checked })} />
            Enable Client Maintenance Mode (returns HTTP 503 to client app while keeping Super Admin Console &amp; /health/ live)
          </label>
          {form.maintenance_mode && (
            <label style={{ display: 'grid', gap: '0.35rem' }}>
              Maintenance notice shown to clients
              <input className="input-field" maxLength={255} disabled={!canEdit} value={form.maintenance_message} onChange={e => setForm({ ...form, maintenance_message: e.target.value })} />
            </label>
          )}
          {canEdit && (
            <div>
              <button type="submit" className="btn btn-primary" disabled={saving || loading} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem' }}>
                <Save size={15} /> {saving ? 'Saving...' : 'Save System Settings'}
              </button>
            </div>
          )}
        </div>
      </form>

      <div className="card" style={{ display: 'grid', gap: '0.85rem' }}>
        <h2 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Database size={17} style={{ color: 'var(--primary)' }} /> Backup Verification Log
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Last verified check: <strong>{form.last_backup_verified_at ? new Date(form.last_backup_verified_at).toLocaleString() : 'Not recorded'}</strong>
          {form.last_backup_note ? ` — ${form.last_backup_note}` : ''}
        </p>
        {canEdit && (
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <input className="input-field" style={{ flex: 1, minWidth: '16rem' }} placeholder="Backup artifact or restore test reference..." value={backupNote} onChange={e => setBackupNote(e.target.value)} />
            <button type="button" className="btn btn-secondary" disabled={saving} onClick={handleRecordBackup}>
              Record Backup Verification
            </button>
          </div>
        )}
      </div>
    </section>
  );
};
