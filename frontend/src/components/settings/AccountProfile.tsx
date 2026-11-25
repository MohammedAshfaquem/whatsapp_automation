import React, { useEffect, useState } from 'react';
import { PasswordInput } from '../PasswordInput';
import { Modal } from '../Modal';
import { fetchApi } from '../../api/client';

type Profile = {
  username: string;
  full_name: string;
  email: string;
  password_change_supported?: boolean;
  email_verification_required?: boolean;
  internal_identifier?: string;
  is_synthetic_identifier?: boolean;
  recovery_email?: string;
  recovery_email_verified?: boolean;
  pending_recovery_email?: string;
};

export const AccountProfile: React.FC = () => {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', new_password_confirmation: '' });
  const [passwordError, setPasswordError] = useState('');
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);

  const [recoveryInput, setRecoveryInput] = useState('');
  const [recoverySaving, setRecoverySaving] = useState(false);
  const [recoveryMessage, setRecoveryMessage] = useState('');
  const [recoveryError, setRecoveryError] = useState('');

  const closePassword = () => {
    setPasswordOpen(false);
    setPasswords({ current_password: '', new_password: '', new_password_confirmation: '' });
    setPasswordError('');
  };

  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (passwordSaving) return;
    setPasswordError('');
    setPasswordSaving(true);
    try {
      await fetchApi('/api/auth/password/', { method: 'POST', body: JSON.stringify(passwords) });
      closePassword();
      setPasswordSaved(true);
    } catch {
      setPasswordError('Unable to change password. Check your current password and use a stronger matching new password.');
    } finally {
      setPasswordSaving(false);
    }
  };

  useEffect(() => {
    let active = true;
    fetchApi<Profile>('/api/auth/profile/')
      .then((data) => {
        if (active) {
          setProfile(data);
          setRecoveryInput(data.pending_recovery_email || data.recovery_email || '');
        }
      })
      .catch((e) => {
        if (active) setError(e?.error || e?.message || 'Unable to load your profile.');
      });
    return () => {
      active = false;
    };
  }, []);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!profile) return;
    setError('');
    setSaved(false);
    setSaving(true);
    try {
      const data = await fetchApi<Profile>('/api/auth/profile/', {
        method: 'POST',
        body: JSON.stringify({ full_name: profile.full_name, email: profile.email }),
      });
      setProfile(data);
      setSaved(true);
    } catch (e: any) {
      setError(e?.error || e?.message || 'Unable to save your profile.');
    } finally {
      setSaving(false);
    }
  };

  const saveRecoveryEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    setRecoveryError('');
    setRecoveryMessage('');
    setRecoverySaving(true);
    try {
      const res = await fetchApi<{ pending_recovery_email: string; message: string }>('/api/auth/recovery-email/', {
        method: 'POST',
        body: JSON.stringify({ recovery_email: recoveryInput }),
      });
      setRecoveryMessage(res.message);
      setProfile((prev) => (prev ? { ...prev, pending_recovery_email: res.pending_recovery_email } : prev));
    } catch (e: any) {
      setRecoveryError(e?.error || 'Could not update recovery email.');
    } finally {
      setRecoverySaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <section
        className="account-profile"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '1.5rem', borderRadius: '.75rem' }}
        aria-label="Your account"
      >
        <h2 style={{ color: 'var(--text-main)', fontSize: '1.1rem', fontWeight: 600 }}>Your account</h2>
        <p style={{ color: 'var(--text-muted)', margin: '.5rem 0 1rem' }}>Update your display name and email address.</p>
        {error && <p role="alert" style={{ color: 'var(--danger)' }}>{error}</p>}
        {profile?.email_verification_required && (
          <div role="alert" style={{ color: 'var(--warning)', marginBottom: '1rem' }}>
            <p>Verify your new email before reopening your workspace</p>
            <a href="/resend-verification/">Resend verification email</a>
          </div>
        )}
        {saved && <p role="status" style={{ color: 'var(--primary)' }}>Profile saved.</p>}
        {profile ? (
          <form onSubmit={save} style={{ display: 'grid', gap: '1rem', maxWidth: '32rem' }}>
            <label>
              Username
              <input className="form-input" value={profile.username} readOnly />
            </label>
            <label>
              Your full name
              <input className="form-input" value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
            </label>
            <label>
              Your email
              <input type="email" className="form-input" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <button className="btn btn-primary" disabled={saving}>Save profile</button>
              {profile.password_change_supported && (
                <button type="button" className="btn btn-secondary" onClick={() => { setPasswordSaved(false); setPasswordOpen(true); }}>
                  Change password
                </button>
              )}
            </div>
          </form>
        ) : (
          !error && <p>Loading profile...</p>
        )}
        {passwordSaved && <p role="status">Password changed.</p>}
        {passwordOpen && (
          <Modal title="Change password" onClose={closePassword}>
            <form onSubmit={changePassword} style={{ display: 'grid', gap: '1rem', padding: '1.25rem' }}>
              {passwordError && <p role="alert">{passwordError}</p>}
              <label>
                Current password
                <PasswordInput visibilityLabel="current password" className="form-input" autoComplete="current-password" required maxLength={1024} value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} />
              </label>
              <label>
                New password
                <PasswordInput visibilityLabel="new password" className="form-input" autoComplete="new-password" required maxLength={1024} value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} />
              </label>
              <label>
                Confirm new password
                <PasswordInput visibilityLabel="confirm new password" className="form-input" autoComplete="new-password" required maxLength={1024} value={passwords.new_password_confirmation} onChange={(e) => setPasswords({ ...passwords, new_password_confirmation: e.target.value })} />
              </label>
              <button type="submit" className="btn btn-primary" disabled={passwordSaving}>Update password</button>
            </form>
          </Modal>
        )}
      </section>

      {profile && (
        <section
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '1.5rem', borderRadius: '.75rem' }}
          aria-label="Recovery email settings"
        >
          <h3 style={{ color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600 }}>Account Recovery Email</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '.35rem 0 1rem' }}>
            Password recovery links are delivered strictly to a verified real mailbox address, separate from any internal login identifier.
          </p>
          {profile.is_synthetic_identifier && (
            <div style={{ padding: '0.65rem 0.85rem', borderRadius: '0.5rem', background: '#f8fafc', border: '1px solid #cbd5e1', fontSize: '0.82rem', color: '#334155', marginBottom: '0.85rem' }}>
              Internal sign-in identifier: <strong>{profile.internal_identifier || profile.username}</strong> (not used for recovery email delivery)
            </div>
          )}
          <div style={{ fontSize: '0.84rem', marginBottom: '0.85rem', color: 'var(--text-main)' }}>
            Current verified recovery email:{' '}
            {profile.recovery_email_verified && profile.recovery_email ? (
              <strong style={{ color: '#047857' }}>{profile.recovery_email} (Verified)</strong>
            ) : (
              <span style={{ color: '#b45309', fontWeight: 600 }}>Not verified yet</span>
            )}
            {profile.pending_recovery_email && (
              <div style={{ color: '#64748b', marginTop: '0.25rem' }}>
                Pending confirmation: <strong>{profile.pending_recovery_email}</strong>
              </div>
            )}
          </div>
          {recoveryMessage && <p role="status" style={{ color: '#047857', fontSize: '0.85rem', marginBottom: '0.65rem' }}>{recoveryMessage}</p>}
          {recoveryError && <p role="alert" style={{ color: 'var(--danger)', fontSize: '0.85rem', marginBottom: '0.65rem' }}>{recoveryError}</p>}
          <form onSubmit={saveRecoveryEmail} style={{ display: 'flex', gap: '0.65rem', maxWidth: '32rem', flexWrap: 'wrap' }}>
            <input
              type="email"
              required
              className="form-input"
              placeholder="recovery-mailbox@company.com"
              value={recoveryInput}
              onChange={(e) => setRecoveryInput(e.target.value)}
              style={{ flex: 1, minWidth: '14rem' }}
            />
            <button type="submit" className="btn btn-secondary" disabled={recoverySaving}>
              {recoverySaving ? 'Sending...' : 'Verify Recovery Email'}
            </button>
          </form>
        </section>
      )}
    </div>
  );
};
