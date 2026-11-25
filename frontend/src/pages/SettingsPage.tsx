import { PasswordInput } from '../components/PasswordInput';
import { useAuth } from '../context/AuthContext';
import { ClientDiagnostics } from './PlatformOperationsPage';
import { ClientImageUpload } from '../components/settings/ClientImageUpload';
import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import {
  Key,
  ShieldCheck,
  Check,
  X,
  Building,
  RefreshCw,
  MessageSquare,
  Award,
} from 'lucide-react';
import {
  WhatsAppBusinessProfileData,
  WhatsAppMetaInfo,
} from '../types';

interface WorkspaceData {
  id: number;
  name: string;
  slug: string;
  logo_url: string;
  logo_source_url?: string;
  timezone: string;
  contact_email: string;
  contact_phone: string;
  plan_name: string;
  subscription_status: string;
  is_active: boolean;
}

interface WhatsAppSettingsData {
  expected_number?: string;
  whatsapp_number?: string;
  app_id?: string;
  app_secret_present?: boolean;
  webhook_url?: string;
  configured: boolean;
  credentials_present: boolean;
  phone_number_id: string;
  business_account_id: string;
  access_token_masked: string;
  webhook_verify_token: string;
  is_enabled: boolean;
  webhook_verified: boolean;
  live_messaging_tested: boolean;
}

interface VerificationResult {
  status: string;
  provider_status: string;
  message: string;
  webhook_verified?: boolean;
}

interface VerticalChoice {
  value: string;
  label: string;
}

export const SettingsPage: React.FC = () => {
  const {tenant, reloadBootstrap}=useAuth();
  const setupLocked=tenant?.meta_setup_required === true && tenant?.meta_setup_ready !== true;
  const [activeTab, setActiveTab] = useState<'workspace' | 'credentials' | 'profile' | 'diagnostics'>(setupLocked || new URLSearchParams(window.location.search).get('tab') === 'whatsapp' ? 'credentials' : 'workspace');
  const [whatsappNumber,setWhatsappNumber]=useState(tenant?.whatsapp_number || '');

  // Workspace Profile State
  const [wsName, setWsName] = useState('');
  const [wsLogoUrl, setWsLogoUrl] = useState('');
  const [wsTimezone, setWsTimezone] = useState('Asia/Kolkata');
  const [wsEmail, setWsEmail] = useState('');
  const [wsPhone, setWsPhone] = useState('');
  const [savingWs, setSavingWs] = useState(false);
  const [wsSuccess, setWsSuccess] = useState<string | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);

  // WhatsApp Meta Settings State
  const [phoneId, setPhoneId] = useState('');
  const [appId,setAppId] = useState('');
  const [appSecret,setAppSecret] = useState('');
  const [waEnabled,setWaEnabled] = useState(true);
  const [wabaId, setWabaId] = useState('');
  const [token, setToken] = useState('');
  const [verifyToken, setVerifyToken] = useState('');
  const [settings, setSettings] = useState<WhatsAppSettingsData | null>(null);

  const [loading, setLoading] = useState(true);
  const [savingWa, setSavingWa] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [waSuccess, setWaSuccess] = useState<string | null>(null);
  const [waError, setWaError] = useState<string | null>(null);

  // WhatsApp Business Profile State
  const [metaInfo, setMetaInfo] = useState<WhatsAppMetaInfo | null>(null);
  const [verticalChoices, setVerticalChoices] = useState<VerticalChoice[]>([]);
  const [profAbout, setProfAbout] = useState('');
  const [profDesc, setProfDesc] = useState('');
  const [profAddress, setProfAddress] = useState('');
  const [profEmail, setProfEmail] = useState('');
  const [profWebsite1, setProfWebsite1] = useState('');
  const [profWebsite2, setProfWebsite2] = useState('');
  const [profVertical, setProfVertical] = useState('OTHER');
  const [savingProf, setSavingProf] = useState(false);
  const [syncingProf, setSyncingProf] = useState(false);
  const [profSuccess, setProfSuccess] = useState<string | null>(null);
  const [profError, setProfError] = useState<string | null>(null);

  const loadData = async (syncMeta = false) => {
    try {
      setLoading(true);
      const [wsData, waData, profData] = await Promise.all([
        fetchApi<WorkspaceData>('/api/settings/workspace/').catch(() => null),
        fetchApi<WhatsAppSettingsData>('/api/settings/whatsapp/').catch(() => null),
        fetchApi<{
          profile: WhatsAppBusinessProfileData;
          meta_info: WhatsAppMetaInfo;
          vertical_choices: VerticalChoice[];
        }>(`/api/settings/whatsapp/profile/${syncMeta ? '?sync=true' : ''}`).catch((err) => {
          if (syncMeta) throw err;
          setProfError(err?.error || 'Failed to load WhatsApp Business Profile.');
          return null;
        }),
      ]);

      if (wsData) {
        setWsName(wsData.name || '');
        setWsLogoUrl(wsData.logo_source_url ?? wsData.logo_url ?? '');
        setWsTimezone(wsData.timezone || 'Asia/Kolkata');
        setWsEmail(wsData.contact_email || '');
        setWsPhone(wsData.contact_phone || '');
      }

      if (waData) {
        setSettings(waData);
        setWhatsappNumber(waData.expected_number || waData.whatsapp_number || tenant?.whatsapp_number || '');
        setPhoneId(waData.phone_number_id || '');
        setAppId(waData.app_id || '');
        setWaEnabled(waData.is_enabled);
        setWabaId(waData.business_account_id || '');
        setVerifyToken(waData.webhook_verify_token || '');
      }

      if (profData) {
        setMetaInfo(profData.meta_info || null);
        setVerticalChoices(profData.vertical_choices || []);
        if (profData.profile) {
          setProfAbout(profData.profile.about || '');
          setProfDesc(profData.profile.description || '');
          setProfAddress(profData.profile.address || '');
          setProfEmail(profData.profile.email || '');
          setProfVertical(profData.profile.vertical || 'OTHER');
          const sites = profData.profile.websites || [];
          setProfWebsite1(sites[0] || '');
          setProfWebsite2(sites[1] || '');
        }
      }
    } catch (err: any) {
      if (syncMeta) throw err;
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingWs(true);
      setWsSuccess(null);
      setWsError(null);
      await fetchApi('/api/settings/workspace/', {
        method: 'POST',
        body: JSON.stringify({
          name: wsName,
          logo_url: wsLogoUrl,
          timezone: wsTimezone,
          contact_email: wsEmail,
          contact_phone: wsPhone,
        }),
      });
      setWsSuccess('Workspace profile updated successfully.');
    } catch (err: any) {
      setWsError(err?.error || 'Failed to update workspace profile.');
    } finally {
      setSavingWs(false);
    }
  };

  const handleSaveWhatsApp = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingWa(true);
      setWaSuccess(null);
      setWaError(null);
      await fetchApi('/api/settings/whatsapp/', {
        method: 'POST',
        body: JSON.stringify({
          phone_number_id: phoneId,
          app_id: appId,
          app_secret: appSecret,
          is_enabled: waEnabled,
          business_account_id: wabaId,
          access_token: token,
          webhook_verify_token: verifyToken,
        }),
      });
      setWaSuccess('WhatsApp Cloud API credentials saved successfully.');
      setToken('');
      setAppSecret('');
      await loadData();
    } catch (err: any) {
      setWaError(err?.error || 'Failed to save WhatsApp credentials.');
    } finally {
      await reloadBootstrap?.();
      setSavingWa(false);
    }
  };

  const handleVerify = async () => {
    try {
      setVerifying(true);
      setVerifyResult(null);
      const res = await fetchApi<VerificationResult>('/api/settings/whatsapp/verify/', {
        method: 'POST',
      });
      setVerifyResult(res);
      await loadData();
    } catch (err: any) {
      setVerifyResult({
        status: 'error',
        provider_status: 'FAILED',
        message: err?.error || 'Verification request failed.',
      });
    } finally {
      await reloadBootstrap?.();
      setVerifying(false);
    }
  };

  const handleSaveBusinessProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingProf(true);
      setProfSuccess(null);
      setProfError(null);
      const websites = [profWebsite1.trim(), profWebsite2.trim()].filter(Boolean);
      const res = await fetchApi<any>('/api/settings/whatsapp/profile/', {
        method: 'POST',
        body: JSON.stringify({
          about: profAbout.trim(),
          description: profDesc.trim(),
          address: profAddress.trim(),
          email: profEmail.trim(),
          websites: websites,
          vertical: profVertical,
        }),
      });
      setProfSuccess(
        res.meta_synced
          ? 'Business Profile updated and synced to Meta WhatsApp Cloud API.'
          : 'Business Profile updated locally (Meta live sync will apply when live credentials are active).'
      );
      if (res.meta_warning) {
        setProfError(`Meta notice: ${res.meta_warning}`);
      }
      await loadData();
    } catch (err: any) {
      setProfError(err?.error || 'Failed to update WhatsApp Business Profile.');
    } finally {
      setSavingProf(false);
    }
  };

  const handleSyncFromMeta = async () => {
    try {
      setSyncingProf(true);
      setProfSuccess(null);
      setProfError(null);
      await loadData(true);
      setProfSuccess('Synced official profile information from Meta Cloud API.');
    } catch (err: any) {
      setProfError(err?.error || 'Failed to sync with Meta Cloud API.');
    } finally {
      setSyncingProf(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '16rem', color: "var(--text-muted)" }}>
        <RefreshCw size={20} className="animate-spin" style={{ marginRight: '0.5rem' }} /> Loading settings...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '64rem', margin: '0 auto' }}>
      {/* Page Title & Subtitle */}
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)", margin: 0 }}>Workspace Settings</h1>
        <p style={{ color: "var(--text-muted)", fontSize: '0.85rem', marginTop: '0.25rem' }}>
          Configure client branding, official Meta WhatsApp Business Profile, and Cloud API credentials.
        </p>
      </div>

      {/* Settings Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          flexWrap: 'wrap',
          borderBottom: "1px solid var(--border)",
          paddingBottom: '0.5rem',
        }}
      >
        <button
          disabled={setupLocked}
          onClick={() => setActiveTab('workspace')}
          className={`btn btn-sm ${activeTab === 'workspace' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <Building size={14} /> Workspace Profile
        </button>
        <button
          onClick={() => setActiveTab('credentials')}
          className={`btn btn-sm ${activeTab === 'credentials' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <Key size={14} /> Meta API & Connection
        </button>
        <button
          disabled={setupLocked}
          onClick={() => setActiveTab('profile')}
          className={`btn btn-sm ${activeTab === 'profile' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <MessageSquare size={14} /> WhatsApp Business Profile
        </button>
      </div>

      {setupLocked && <section className="card" aria-label="Meta setup guide"><h2>Set up WhatsApp to unlock your workspace</h2><ol><li>Use your dedicated business WhatsApp number in international format.</li><li>In Meta Business, add your app, WhatsApp Business Account and Phone Number ID.</li><li>Save your access token and app credentials below.</li><li>Configure the webhook URL and verification token in Meta, then select Verify and Unlock.</li></ol><p>{tenant?.meta_setup_reason || 'Your connection must be verified with Meta before daily business tools are available.'}</p></section>}
      {activeTab === 'diagnostics' && <ClientDiagnostics />}
      {/* TAB 1: WORKSPACE PROFILE */}
      {activeTab === 'workspace' && <ClientImageUpload kind="workspace_logo" label="Workspace logo" onUploaded={()=>loadData()} />}
      {activeTab === 'profile' && <ClientImageUpload kind="whatsapp_profile" label="WhatsApp profile photo" />}
      {activeTab === 'workspace' && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <Building size={18} style={{ color: "var(--primary)" }} />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>Client Workspace Profile</h2>
          </div>

          {wsSuccess && (
            <div style={{ padding: '0.75rem', backgroundColor: 'rgba(17, 183, 109, 0.15)', border: '1px solid rgba(17, 183, 109, 0.3)', borderRadius: '0.5rem', color: "var(--primary)", fontSize: '0.85rem', marginBottom: '1rem' }}>
              {wsSuccess}
            </div>
          )}
          {wsError && (
            <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem', marginBottom: '1rem' }}>
              {wsError}
            </div>
          )}

          <form onSubmit={handleSaveWorkspace} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Workspace / Business Name *
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={wsName}
                  onChange={(e) => setWsName(e.target.value)}
                  placeholder="e.g. Acme Services Pvt Ltd"
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Timezone *
                </label>
                <select
                  className="input-field"
                  value={wsTimezone}
                  onChange={(e) => setWsTimezone(e.target.value)}
                >
                  <option value="Asia/Kolkata">Asia/Kolkata (IST +5:30)</option>
                  <option value="UTC">UTC (+0:00)</option>
                  <option value="America/New_York">America/New_York (EST -5:00)</option>
                  <option value="Europe/London">Europe/London (GMT +0:00)</option>
                  <option value="Asia/Dubai">Asia/Dubai (GST +4:00)</option>
                  <option value="Asia/Singapore">Asia/Singapore (SGT +8:00)</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                External Logo Image URL (optional)
              </label>
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <input
                  type="url"
                  className="input-field"
                  style={{ flex: 1 }}
                  value={wsLogoUrl}
                  onChange={(e) => setWsLogoUrl(e.target.value)}
                  placeholder="https://example.com/assets/client-logo.png"
                />
                {wsLogoUrl ? (
                  <img
                    src={wsLogoUrl}
                    alt="Client Logo Preview"
                    style={{ width: '2.5rem', height: '2.5rem', objectFit: 'contain', borderRadius: '0.375rem', border: "1px solid var(--border)", backgroundColor: "var(--bg-card)" }}
                    onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
                  />
                ) : (
                  <div style={{ width: '2.5rem', height: '2.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '0.375rem', border: "1px dashed var(--border)", color: "var(--text-muted)", fontSize: '0.7rem' }}>
                    No Logo
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Contact Email
                </label>
                <input
                  type="email"
                  className="input-field"
                  value={wsEmail}
                  onChange={(e) => setWsEmail(e.target.value)}
                  placeholder="admin@clientbiz.com"
                />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Contact Phone
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={wsPhone}
                  onChange={(e) => setWsPhone(e.target.value)}
                  placeholder="+919876543210"
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
              <button type="submit" className="btn btn-primary" disabled={savingWs}>
                {savingWs ? 'Saving...' : 'Save Workspace Profile'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* TAB 2: META CREDENTIALS & CONNECTION */}
      {activeTab === 'credentials' && (
        <>
          {/* Operational Status */}
          <div className="card">
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '1rem' }}>
              Meta Operational Connection Status
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(11rem, 1fr))', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>Configuration Saved</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                  {settings?.configured ? (
                    <span style={{ color: "var(--primary)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Check size={14} /> Saved
                    </span>
                  ) : (
                    <span style={{ color: "var(--warning)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <X size={14} /> Not Saved
                    </span>
                  )}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>Credentials Present</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                  {settings?.credentials_present ? (
                    <span style={{ color: "var(--primary)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Check size={14} /> Present
                    </span>
                  ) : (
                    <span style={{ color: "var(--warning)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <X size={14} /> Missing
                    </span>
                  )}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>Webhook Traffic</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                  {settings?.webhook_verified ? (
                    <span style={{ color: "var(--primary)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Check size={14} /> Observed
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-muted)" }}>Awaiting Events</span>
                  )}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>Live Delivery</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                  {settings?.live_messaging_tested ? (
                    <span style={{ color: "var(--primary)", display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Check size={14} /> Active
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-muted)" }}>Not Tested</span>
                  )}
                </div>
              </div>
            </div>

            <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={handleVerify}
                className="btn btn-secondary"
                disabled={verifying || !settings?.credentials_present}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <ShieldCheck size={16} />
                {verifying ? 'Checking Connectivity...' : 'Verify and Unlock'}
              </button>
              <span style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                Checks credentials and the assigned business number directly with Meta without sending customer messages.
              </span>
            </div>

            {verifyResult && (
              <div
                style={{
                  marginTop: '0.75rem',
                  padding: '0.75rem',
                  borderRadius: '0.5rem',
                  backgroundColor: verifyResult.status === 'ok' ? 'rgba(17, 183, 109, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                  border: `1px solid ${verifyResult.status === 'ok' ? 'rgba(17, 183, 109, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                  color: verifyResult.status === 'ok' ? "var(--primary)" : "var(--danger)",
                  fontSize: '0.85rem',
                }}
              >
                <strong>Status: [{verifyResult.provider_status}]</strong> — {verifyResult.message}
              </div>
            )}
          </div>

          {/* Credentials Form */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
              <Key size={18} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>Meta Cloud API Credentials</h2>
            </div>

            {waSuccess && (
              <div style={{ padding: '0.75rem', backgroundColor: 'rgba(17, 183, 109, 0.15)', border: '1px solid rgba(17, 183, 109, 0.3)', borderRadius: '0.5rem', color: "var(--primary)", fontSize: '0.85rem', marginBottom: '1rem' }}>
                {waSuccess}
              </div>
            )}
            {waError && (
              <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem', marginBottom: '1rem' }}>
                {waError}
              </div>
            )}

            <form onSubmit={handleSaveWhatsApp} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <label>Meta App ID<input aria-label="Meta App ID" className="input-field" value={appId} onChange={e=>setAppId(e.target.value)} placeholder="Your Meta app ID" /></label>
              <label>Meta App Secret<PasswordInput visibilityLabel="Meta App Secret" aria-label="Meta App Secret" className="input-field" autoComplete="new-password" value={appSecret} onChange={e=>setAppSecret(e.target.value)} placeholder={settings?.app_secret_present?'Saved — leave blank to keep':'App secret for webhook signature verification'} /></label>
              <label style={{display:'flex',gap:8}}><input type="checkbox" checked={waEnabled} onChange={e=>setWaEnabled(e.target.checked)} />Enable WhatsApp messaging for this workspace</label>
              <p style={{fontSize:13,color:"var(--text-muted)",overflowWrap:'anywhere'}}>Meta callback URL: {settings?.webhook_url || window.location.origin+'/api/whatsapp/webhook/'}<br/>Subscribe your Meta app to WhatsApp messages, configure this callback and the verification token below, and use an access token belonging to this client account. Saving credentials does not complete Meta business verification or approve templates.</p>

              <div style={{marginBottom:'1rem'}}><label htmlFor="business-whatsapp-number">Business WhatsApp number *</label><input id="business-whatsapp-number" className="form-input" type="tel" value={whatsappNumber} readOnly placeholder="Assigned by Super Admin" /><p style={{color:"var(--text-muted)"}}>The actual business number is separate from the Meta Phone Number ID.</p></div>
                <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  WhatsApp Phone Number ID *
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={phoneId}
                  onChange={(e) => setPhoneId(e.target.value)}
                  placeholder="e.g. 109876543210123"
                  required
                />
                <p style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                  Found in Meta Developer Portal under WhatsApp &gt; API Setup &gt; Phone number ID. Must be unique across all clients.
                </p>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  WhatsApp Business Account ID (WABA ID)
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={wabaId}
                  onChange={(e) => setWabaId(e.target.value)}
                  placeholder="e.g. 209876543210123"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Permanent Meta System User Access Token
                </label>
                <PasswordInput
                  visibilityLabel="Meta access token"
                  className="input-field"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder={settings?.access_token_masked || 'Enter new access token (leave blank to keep current)'}
                />
                {settings?.access_token_masked && (
                  <p style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                    Current token: {settings.access_token_masked} (masked for security)
                  </p>
                )}
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Webhook Verification Secret Token
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={verifyToken}
                  onChange={(e) => setVerifyToken(e.target.value)}
                  placeholder="e.g. your_custom_verify_token"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                <button type="submit" className="btn btn-primary" disabled={savingWa}>
                  {savingWa ? 'Saving...' : 'Save Meta Credentials'}
                </button>
              </div>
            </form>
          </div>
        </>
      )}

      {/* TAB 3: WHATSAPP BUSINESS PROFILE */}
      {activeTab === 'profile' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Read-Only Official Meta Status Cards */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Award size={18} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)", margin: 0 }}>
                  Official Meta Verified Phone & Account Status
                </h2>
              </div>
              <button
                type="button"
                onClick={handleSyncFromMeta}
                disabled={syncingProf || !metaInfo?.is_live}
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                title="Fetch live phone number attributes from Meta Cloud API"
              >
                <RefreshCw size={13} className={syncingProf ? 'animate-spin' : ''} />
                {syncingProf ? 'Syncing...' : 'Sync from Meta'}
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(11rem, 1fr))', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.2rem' }}>Verified Display Name</div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: "var(--text-main)" }}>
                  {metaInfo?.verified_name && metaInfo.verified_name !== 'UNAVAILABLE'
                    ? metaInfo.verified_name
                    : 'Not configured'}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.2rem' }}>Display Phone Number</div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: "var(--text-main)" }}>
                  {metaInfo?.display_phone_number && metaInfo.display_phone_number !== 'UNAVAILABLE'
                    ? metaInfo.display_phone_number
                    : 'Not connected'}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.2rem' }}>Quality Rating</div>
                <div>
                  {metaInfo?.quality_rating && metaInfo.quality_rating !== 'UNKNOWN' ? (
                    <span
                      className={`badge ${
                        metaInfo.quality_rating === 'GREEN'
                          ? 'badge-green'
                          : metaInfo.quality_rating === 'YELLOW'
                          ? 'badge-amber'
                          : 'badge-red'
                      }`}
                      style={{ fontSize: '0.7rem' }}
                    >
                      ● {metaInfo.quality_rating}
                    </span>
                  ) : (
                    <span className="badge badge-gray" style={{ fontSize: '0.7rem' }}>
                      ● UNKNOWN
                    </span>
                  )}
                </div>
              </div>

              <div style={{ padding: '0.75rem', backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '0.5rem' }}>
                <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.2rem' }}>Messaging Limit Tier</div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: "var(--primary)" }}>
                  {metaInfo?.messaging_limit_tier && metaInfo.messaging_limit_tier !== 'UNKNOWN'
                    ? metaInfo.messaging_limit_tier
                    : 'UNKNOWN'}
                </div>
              </div>
            </div>
          </div>

          {/* Business Profile Editor Form */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
              <MessageSquare size={18} style={{ color: "var(--primary)" }} />
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)", margin: 0 }}>
                  Public WhatsApp Business Profile Details
                </h2>
                <p style={{ fontSize: '0.75rem', color: "var(--text-muted)", margin: '0.2rem 0 0 0' }}>
                  These profile details are displayed to customers inside their WhatsApp app when viewing your business info.
                </p>
              </div>
            </div>

            {profSuccess && (
              <div style={{ padding: '0.75rem', backgroundColor: 'rgba(17, 183, 109, 0.15)', border: '1px solid rgba(17, 183, 109, 0.3)', borderRadius: '0.5rem', color: "var(--primary)", fontSize: '0.85rem', marginBottom: '1rem' }}>
                {profSuccess}
              </div>
            )}
            {profError && (
              <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem', marginBottom: '1rem' }}>
                {profError}
              </div>
            )}

            <form onSubmit={handleSaveBusinessProfile} style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
              {/* About / Status */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>About / Bio (Status)</label>
                  <span style={{ fontSize: '0.72rem', color: profAbout.length > 130 ? "var(--warning)" : "var(--text-muted)" }}>
                    {profAbout.length}/139 chars
                  </span>
                </div>
                <input
                  type="text"
                  maxLength={139}
                  className="input-field"
                  value={profAbout}
                  onChange={(e) => setProfAbout(e.target.value)}
                  placeholder="e.g. Always here to help with your service and appointment needs."
                />
                <p style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                  Shown under the business title on customer mobile screens (maximum 139 characters).
                </p>
              </div>

              {/* Description */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Business Description</label>
                  <span style={{ fontSize: '0.72rem', color: profDesc.length > 500 ? "var(--warning)" : "var(--text-muted)" }}>
                    {profDesc.length}/512 chars
                  </span>
                </div>
                <textarea
                  rows={3}
                  maxLength={512}
                  className="input-field"
                  style={{ resize: 'none' }}
                  value={profDesc}
                  onChange={(e) => setProfDesc(e.target.value)}
                  placeholder="Describe your company, key offerings, and business hours..."
                />
                <p style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                  Detailed overview of your services in WhatsApp profile (maximum 512 characters).
                </p>
              </div>

              {/* Category / Vertical */}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Business Category / Vertical *
                </label>
                <select
                  className="input-field"
                  value={profVertical}
                  onChange={(e) => setProfVertical(e.target.value)}
                >
                  {verticalChoices.map((v) => (
                    <option key={v.value} value={v.value}>
                      {v.label}
                    </option>
                  ))}
                </select>
                <p style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                  Official Meta industry classification category.
                </p>
              </div>

              {/* Address & Email */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <label style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Business Physical Address</label>
                    <span style={{ fontSize: '0.72rem', color: profAddress.length > 250 ? "var(--warning)" : "var(--text-muted)" }}>
                      {profAddress.length}/256 chars
                    </span>
                  </div>
                  <input
                    type="text"
                    maxLength={256}
                    className="input-field"
                    value={profAddress}
                    onChange={(e) => setProfAddress(e.target.value)}
                    placeholder="e.g. 104 Business Bay, Main Ring Road, Mumbai"
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <label style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>Public Contact Email</label>
                    <span style={{ fontSize: '0.72rem', color: profEmail.length > 120 ? "var(--warning)" : "var(--text-muted)" }}>
                      {profEmail.length}/128 chars
                    </span>
                  </div>
                  <input
                    type="email"
                    maxLength={128}
                    className="input-field"
                    value={profEmail}
                    onChange={(e) => setProfEmail(e.target.value)}
                    placeholder="contact@yourbusiness.com"
                  />
                </div>
              </div>

              {/* Websites */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                    Primary Website URL
                  </label>
                  <input
                    type="url"
                    className="input-field"
                    value={profWebsite1}
                    onChange={(e) => setProfWebsite1(e.target.value)}
                    placeholder="https://yourbusiness.com"
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                    Secondary Website / Booking URL
                  </label>
                  <input
                    type="url"
                    className="input-field"
                    value={profWebsite2}
                    onChange={(e) => setProfWebsite2(e.target.value)}
                    placeholder="https://book.yourbusiness.com"
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                <button type="submit" className="btn btn-primary" disabled={savingProf}>
                  {savingProf ? 'Saving Profile...' : 'Save WhatsApp Business Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};