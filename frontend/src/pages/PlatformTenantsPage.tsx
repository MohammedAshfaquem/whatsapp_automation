import { Modal } from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Plus,
  Search,
  Eye,
  Check,
  Copy,
  Edit,
} from 'lucide-react';

export const PlatformTenantsPage: React.FC<{ onNavigate: (path: string) => void }> = ({ onNavigate }) => {
  const { inspectTenant } = useAuth();
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [focusedTenant,setFocusedTenant] = useState(new URLSearchParams(window.location.search).get('tenant_id') || '');

  // Provisioning Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Form Fields
  const [name, setName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [whatsappNumber,setWhatsappNumber]=useState('');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [logoUrl, setLogoUrl] = useState('');

  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminUsername, setAdminUsername] = useState('');

  const [plan, setPlan] = useState('GROWTH');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Activation Link Modal after provisioning
  const [createdResult, setCreatedResult] = useState<{
    tenantName: string;
    activationUrl?: string;
    ownerUsername?: string;
  } | null>(null);

  // Edit Workspace Modal
  const [editingTenant, setEditingTenant] = useState<any | null>(null);
  const [editLogoUrl, setEditLogoUrl] = useState('');
  const [editTimezone, setEditTimezone] = useState('');
  const [editContactEmail, setEditContactEmail] = useState('');
  const [editContactPhone, setEditContactPhone] = useState('');
  const [editSaving, setEditSaving] = useState(false);

  const loadTenants = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{ tenants: any[] }>('/api/platform/tenants/');
      setTenants(data.tenants || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTenants();
  }, []);

  const handleActivationLink = async (tenant: any) => {
    try {
      const result = await fetchApi<{activation_url:string;owner_username:string}>(`/api/platform/tenants/${tenant.id}/activation/`, {method:'POST'});
      setCreatedResult({tenantName:tenant.name,activationUrl:result.activation_url,ownerUsername:result.owner_username});
    } catch (error:any) { alert(error.error || 'Could not generate client setup link.'); }
  };

  const handleToggle = async (tenantId: number) => {
    try {
      await fetchApi(`/api/platform/tenants/${tenantId}/toggle/`, { method: 'POST' });
      await loadTenants();
    } catch (err: any) {
      alert(err?.error || 'Could not toggle workspace status');
    }
  };

  const handleOutboundPause = async (t: any) => {
    const nextPaused = !t.outbound_paused;
    const reason = nextPaused ? (window.prompt('Optional reason for pausing outbound WhatsApp:', t.outbound_pause_reason || '') || '') : '';
    try {
      await fetchApi(`/api/platform/tenants/${t.id}/outbound-pause/`, {
        method: 'POST',
        body: JSON.stringify({ paused: nextPaused, reason }),
      });
      await loadTenants();
    } catch (err: any) {
      alert(err?.error || 'Could not update outbound pause state');
    }
  };

  const handleInspect = async (tenantId: number) => {
    await inspectTenant(tenantId);
    onNavigate('/app/dashboard');
  };

  const handleProvision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    if (!/^\+[1-9][0-9]{7,14}$/.test(whatsappNumber.trim())) {setError('Enter a valid business WhatsApp number in international format, e.g. +919876543210.');return;}

    try {
      setSaving(true);
      setError(null);
      const res = await fetchApi<{
        status: string;
        tenant: { id: number; name: string; slug: string; logo_url?: string; owner_username?: string };
        activation_url?: string;
        message: string;
      }>('/api/platform/tenants/', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          contact_email: contactEmail.trim(),
          contact_phone: contactPhone.trim(),
          whatsapp_number: whatsappNumber.trim(),
          timezone,
          logo_url: logoUrl.trim(),
          plan,
          admin_mode: 'new',
          admin_name: adminName.trim(),
          admin_email: adminEmail.trim(),
          admin_username: adminUsername.trim(),
        }),
      });

      setShowAddModal(false);
      setCreatedResult({
        tenantName: res.tenant.name,
        activationUrl: res.activation_url,
        ownerUsername: res.tenant.owner_username,
      });

      // Reset form
      setName('');
      setContactEmail('');
      setContactPhone('');
      setWhatsappNumber('');
      setLogoUrl('');
      setAdminName('');
      setAdminEmail('');
      setAdminUsername('');
      setStep(1);

      await loadTenants();
    } catch (err: any) {
      setError(err?.error || 'Could not provision client workspace');
    } finally {
      setSaving(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTenant) return;

    try {
      setEditSaving(true);
      await fetchApi(`/api/platform/tenants/${editingTenant.id}/update/`, {
        method: 'POST',
        body: JSON.stringify({
          logo_url: editLogoUrl.trim(),
          timezone: editTimezone.trim(),
          contact_email: editContactEmail.trim(),
          contact_phone: editContactPhone.trim(),
        }),
      });
      setEditingTenant(null);
      await loadTenants();
    } catch (err: any) {
      alert(err?.error || 'Could not update workspace details');
    } finally {
      setEditSaving(false);
    }
  };

  const filteredTenants = tenants.filter(t => !focusedTenant || String(t.id) === focusedTenant).filter(
    (t) =>
      t.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.slug?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.owner_username?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '85rem', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: "var(--text-main)" }}>Client Workspaces Directory</h1>
            <span style={{ fontSize: '0.75rem', background: 'var(--primary-light)', color: "var(--primary)", border: '1px solid var(--primary-border)', padding: '0.2rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
              Super Admin Console
            </span>
          </div>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Guided client provisioning, branding logos, plan entitlement bundles, and explicit support inspection.
          </p>
        </div>

        <button onClick={() => { setStep(1); setShowAddModal(true); }} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700 }}>
          <Plus size={16} /> Provision Client Workspace
        </button>
      </div>

      {/* Filter / Search Bar */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', background: "var(--bg-card)", padding: '0.75rem 1rem', borderRadius: '8px', border: "1px solid var(--border)" }}>
        <Search size={18} style={{ color: "var(--text-muted)" }} />
        <input
          type="text"
          placeholder="Search by client name, slug, or administrator..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ background: 'transparent', border: 'none', color: "var(--text-main)", fontSize: '0.9rem', outline: 'none', width: '100%' }}
        />
        <span style={{ fontSize: '0.8rem', color: "var(--text-muted)", whiteSpace: 'nowrap' }}>
          {filteredTenants.length} of {tenants.length} Workspaces {focusedTenant && <button className="btn btn-secondary" onClick={()=>setFocusedTenant('')}>Show all workspaces</button>}
        </span>
      </div>

      {/* Workspaces Table */}
      <div className="table-container" style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '10px', overflow: 'hidden' }}>
        <table className="custom-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-card)" }}>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Client Branding</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Workspace &amp; Slug</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Administrator</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Plan &amp; Capacity</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Status</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'right', fontSize: '0.75rem', fontWeight: 700, color: "var(--text-muted)", textTransform: 'uppercase' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
                  Loading workspaces...
                </td>
              </tr>
            ) : filteredTenants.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
                  No client workspaces found matching your filter.
                </td>
              </tr>
            ) : (
              filteredTenants.map((t) => (
                <tr key={t.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  {/* Logo Column */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      {t.logo_url ? (
                        <img
                          src={t.logo_url}
                          alt={t.name}
                          style={{
                            width: '36px',
                            height: '36px',
                            borderRadius: '8px',
                            objectFit: 'contain',
                            border: "1px solid var(--border)",
                            background: '#ffffff',
                            padding: '2px',
                          }}
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: '36px',
                            height: '36px',
                            borderRadius: '8px',
                            backgroundColor: "var(--primary-light)",
                            color: "var(--primary)",
                            fontWeight: 800,
                            fontSize: '0.85rem',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '1px solid #059669',
                          }}
                        >
                          {t.name.substring(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '0.9rem' }}>{t.name}</div><div style={{fontSize:'.75rem',color:t.meta_setup_required && !t.meta_setup_ready ? "var(--warning)" : "var(--primary)"}}>{t.meta_setup_required ? (t.meta_setup_ready ? 'Meta connected' : 'Meta setup required') : 'Existing workspace'}{t.whatsapp_number ? ' · '+t.whatsapp_number : ''}</div>
                        <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{t.timezone || 'Asia/Kolkata'}</div>
                      </div>
                    </div>
                  </td>

                  {/* Slug & Contact */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: "var(--primary)" }}>{t.slug}</div>
                    {t.contact_email && (
                      <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{t.contact_email}</div>
                    )}
                  </td>

                  {/* Administrator */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ fontWeight: 600, color: "var(--text-main)", fontSize: '0.85rem' }}>@{t.owner_username}</div>
                    {t.owner_email && <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{t.owner_email}</div>}
                    {t.owner_activation_pending && <button className="btn btn-secondary" onClick={()=>handleActivationLink(t)}>Generate setup link</button>}
                  </td>

                  {/* Plan & Capacity */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span className="badge badge-gray" style={{ fontWeight: 700 }}>
                        {t.plan_name || t.plan}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                        {t.staff_count}/{t.max_staff} seats
                      </span>
                    </div>
                  </td>

                  {/* Status */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', alignItems: 'flex-start' }}>
                      <button
                        onClick={() => handleToggle(t.id)}
                        className={`badge ${t.is_active ? 'badge-green' : 'badge-red'}`}
                        style={{ cursor: 'pointer', border: 'none' }}
                        title="Click to toggle Active / Suspended status"
                      >
                        {t.is_active ? 'Active' : 'Suspended'}
                      </button>
                      {t.outbound_paused && (
                        <span className="badge badge-amber" style={{ fontSize: '0.68rem' }}>Outbound Paused</span>
                      )}
                      {t.grace_until && (
                        <span className="badge badge-gray" style={{ fontSize: '0.68rem' }}>Grace: {t.grace_until}</span>
                      )}
                    </div>
                  </td>

                  {/* Actions */}
                  <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => handleOutboundPause(t)}
                        className="btn btn-sm btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                      >
                        {t.outbound_paused ? 'Resume Outbound' : 'Pause Outbound'}
                      </button>
                      <button
                        onClick={() => {
                          setEditingTenant(t);
                          setEditLogoUrl(t.logo_url || '');
                          setEditTimezone(t.timezone || 'Asia/Kolkata');
                          setEditContactEmail(t.contact_email || '');
                          setEditContactPhone(t.contact_phone || '');
                        }}
                        className="btn btn-sm btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                        title="Edit branding and details"
                      >
                        <Edit size={13} /> Edit
                      </button>

                      <button
                        onClick={() => handleInspect(t.id)}
                        className="btn btn-sm btn-secondary"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem', borderColor: '#3b82f6', color: "var(--primary)" }}
                        title="Inspect workspace with Super Admin privileges"
                      >
                        <Eye size={13} /> Inspect
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Guided Client Provisioning Modal */}
      {showAddModal && (
        <Modal title={`Provision Client Workspace (Step ${step} of 4)`} onClose={() => setShowAddModal(false)} maxWidth="640px" zIndex={100} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '12px', padding: '2rem', width: '100%', maxWidth: '640px', boxShadow: '0 25px 60px -12px rgba(15, 58, 38, 0.18)' }}>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', borderBottom: "1px solid var(--border)", paddingBottom: '0.75rem' }}>
              <div>

                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                  {step === 1 && 'Step 1: Client Business & Branding'}
                  {step === 2 && 'Step 2: Client Administrator Provisioning'}
                  {step === 3 && 'Step 3: Subscription Plan & Limits'}
                  {step === 4 && 'Step 4: Review & Transactional Creation'}
                </div>
              </div>

            </div>

            {error && (
              <div style={{ background: '#fff1f2', border: '1px solid #fecdd3', color: '#9f1239', padding: '0.75rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.85rem' }}>
                {error}
              </div>
            )}

            <form onSubmit={handleProvision}>
              {/* Step 1: Business & Branding */}
              {step === 1 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Client Business Name *</label>
                    <input type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Apex Hospital or Horizon Retail" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                  </div>

                  <div><label htmlFor="provision-whatsapp-number">Business WhatsApp number *</label><input id="provision-whatsapp-number" type="tel" required pattern="\+[1-9][0-9]{7,14}" value={whatsappNumber} onChange={e=>setWhatsappNumber(e.target.value)} placeholder="+919876543210" className="form-input" /><p style={{color:"var(--text-muted)",fontSize:'.8rem'}}>Dedicated WhatsApp business number. The client will connect and verify this number with Meta before using daily business tools.</p></div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Primary Contact Email</label>
                      <input type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="admin@client.com" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Contact Phone</label>
                      <input type="text" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="+91 98765 43210" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Client Logo URL (Displayed in Client Navbar &amp; Shell)</label>
                    <input type="url" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://example.com/client-logo.png or /static/..." className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                    <div style={{ fontSize: '0.725rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                      Shown in the client workspace header next to the Neoriz product logo.
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Timezone</label>
                    <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}>
                      <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                      <option value="Asia/Dubai">Asia/Dubai (GST)</option>
                      <option value="Europe/London">Europe/London (GMT/BST)</option>
                      <option value="America/New_York">America/New_York (EST)</option>
                      <option value="UTC">UTC</option>
                    </select>
                  </div>
                </div>
              )}

              {/* Step 2: Administrator */}
              {step === 2 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ background: "var(--bg-card-hover)", padding: '0.75rem', borderRadius: '6px', fontSize: '0.825rem', color: "var(--text-muted)" }}>
                    Super Admin controlled provisioning: A secure single-use expiring activation link will be generated for password setup. Plaintext passwords are not transmitted.
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Administrator Full Name</label>
                    <input type="text" value={adminName} onChange={(e) => setAdminName(e.target.value)} placeholder="e.g. Sarah Jenkins" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Admin Email Address *</label>
                      <input type="email" required value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="sarah@client.com" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Username (Optional)</label>
                      <input type="text" value={adminUsername} onChange={(e) => setAdminUsername(e.target.value)} placeholder="sarah_admin" className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }} />
                    </div>
                  </div>
                </div>
              )}

              {/* Step 3: Plan & Limits */}
              {step === 3 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Subscription Plan Tier</label>
                    <select value={plan} onChange={(e) => setPlan(e.target.value)} className="form-input" style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}>
                      <option value="STARTER">Starter Tier (2 Seats, 1,000 Msg/mo)</option>
                      <option value="GROWTH">Growth Tier (5 Seats, 5,000 Msg/mo, Grounded AI)</option>
                      <option value="PRO">Professional Tier (10 Seats, 15,000 Msg/mo, Multi-Agent)</option>
                      <option value="ENTERPRISE">Enterprise Tier (25+ Seats, Custom Limits)</option>
                    </select>
                  </div>

                  <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", padding: '1rem', borderRadius: '8px', fontSize: '0.825rem', color: "var(--text-muted)" }}>
                    <div style={{ fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Plan Entitlements Included:</div>
                    <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
                      <li>Multi-tenant isolated CRM &amp; contact timeline</li>
                      <li>Shared WhatsApp Inbox &amp; human handover</li>
                      <li>Client-managed Meta Cloud API connection</li>
                      <li>{plan === 'STARTER' ? 'Rule-based bot' : 'Grounded Gemini AI Assistant'}</li>
                    </ul>
                  </div>
                </div>
              )}

              {/* Step 4: Review */}
              {step === 4 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', background: "var(--bg-card)", padding: '1.25rem', borderRadius: '8px', border: "1px solid var(--border)", fontSize: '0.85rem' }}>
                  <div style={{ fontWeight: 700, color: "var(--text-main)", borderBottom: "1px solid var(--border)", paddingBottom: '0.5rem' }}>
                    Confirm Proposed Workspace Configuration:
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '0.5rem' }}>
                    <span style={{ color: "var(--text-muted)" }}>Client Name:</span>
                    <strong style={{ color: "var(--text-main)" }}>{name}</strong>

                    <span style={{ color: "var(--text-muted)" }}>Contact Email:</span>
                    <span style={{ color: "var(--text-main)" }}>{contactEmail || 'None'}</span>

                    <span style={{ color: "var(--text-muted)" }}>WhatsApp Number:</span><strong style={{color:"var(--text-main)"}}>{whatsappNumber}</strong>
                    <span style={{ color: "var(--text-muted)" }}>Client Logo:</span>
                    <span style={{ color: "var(--primary)" }}>{logoUrl || 'Default initials badge'}</span>

                    <span style={{ color: "var(--text-muted)" }}>Administrator:</span>
                    <strong style={{ color: "var(--text-main)" }}>{adminEmail}</strong>

                    <span style={{ color: "var(--text-muted)" }}>Assigned Role:</span>
                    <span className="badge badge-gray">Workspace Owner</span>

                    <span style={{ color: "var(--text-muted)" }}>Plan Tier:</span>
                    <span className="badge badge-green">{plan}</span>
                  </div>

                  <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.5rem' }}>
                    Upon confirmation, the workspace, subscription, and pre-provisioned administrator identity will be committed transactionally. An expiring activation link will be generated.
                  </div>
                </div>
              )}

              {/* Modal Navigation Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1.75rem', borderTop: "1px solid var(--border)", paddingTop: '1rem' }}>
                {step > 1 ? (
                  <button type="button" onClick={() => setStep((s) => (s - 1) as any)} className="btn btn-secondary">
                    &larr; Back
                  </button>
                ) : <div />}

                {step < 4 ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (step === 1 && !name.trim()) {
                        setError('Client business name is required.');
                        return;
                      }
                      if (step === 1 && !/^\+[1-9][0-9]{7,14}$/.test(whatsappNumber.trim())) {setError('Enter a valid business WhatsApp number in international format, e.g. +919876543210.');return;}
                      if (step === 2 && !adminEmail.trim()) {
                        setError('Administrator email is required.');
                        return;
                      }
                      setError(null);
                      setStep((s) => (s + 1) as any);
                    }}
                    className="btn btn-primary"
                  >
                    Next Step &rarr;
                  </button>
                ) : (
                  <button type="submit" disabled={saving} className="btn btn-primary" style={{ fontWeight: 800 }}>
                    {saving ? 'Provisioning...' : 'Confirm & Provision Workspace'}
                  </button>
                )}
              </div>
            </form>

        </Modal>
      )}

      {/* Activation URL Result Modal */}
      {createdResult && (
        <Modal title="Client Access & Activation" onClose={() => setCreatedResult(null)} maxWidth="580px" zIndex={110} style={{ background: "var(--bg-card)", border: '1px solid #10b981', borderRadius: '12px', padding: '2rem', width: '100%', maxWidth: '580px', boxShadow: '0 25px 60px -12px rgba(15, 58, 38, 0.18)' }}>

            <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: "var(--primary-light)", color: "var(--primary)", display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem' }}>
              <Check size={24} />
            </div>

            <p style={{ fontSize: '0.875rem', color: "var(--text-muted)", textAlign: 'center', marginBottom: '1.5rem' }}>
              Workspace <strong>"{createdResult.tenantName}"</strong> has been created with administrator <strong>@{createdResult.ownerUsername}</strong>.
            </p>

            {createdResult.activationUrl && (
              <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '8px', padding: '1rem', marginBottom: '1.5rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: "var(--primary)", marginBottom: '0.35rem' }}>
                  Single-Use Expiring Activation Link (48 hours):
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input
                    type="text"
                    readOnly
                    value={createdResult.activationUrl}
                    style={{ flex: 1, padding: '0.5rem', background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--primary)", fontSize: '0.8rem', fontFamily: 'monospace' }}
                  />
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(createdResult.activationUrl!);
                      alert('Activation URL copied to clipboard!');
                    }}
                    className="btn btn-secondary"
                    style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                    title="Copy Link"
                  >
                    <Copy size={14} /> Copy
                  </button>
                </div>
                <div style={{ fontSize: '0.725rem', color: "var(--text-muted)", marginTop: '0.35rem' }}>
                  Copy and send this full link to the client by email or WhatsApp. It is not emailed automatically. Generating a new link invalidates the previous unused link. The client can open it without an existing login and choose their password.
                </div>
              </div>
            )}

            <button onClick={() => setCreatedResult(null)} className="btn btn-primary" style={{ width: '100%', padding: '0.75rem', fontWeight: 700 }}>
              Close
            </button>

        </Modal>
      )}

      {/* Edit Workspace Modal */}
      {editingTenant && (
        <Modal title={`Edit Workspace: ${editingTenant.name}`} onClose={() => setEditingTenant(null)} maxWidth="540px" zIndex={100} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: '12px', padding: '2rem', width: '100%', maxWidth: '540px' }}>

            <form onSubmit={handleEditSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Client Logo URL</label>
                <input
                  type="url"
                  value={editLogoUrl}
                  onChange={(e) => setEditLogoUrl(e.target.value)}
                  placeholder="https://example.com/logo.png"
                  style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Primary Timezone</label>
                <input
                  type="text"
                  value={editTimezone}
                  onChange={(e) => setEditTimezone(e.target.value)}
                  placeholder="Asia/Kolkata"
                  style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Contact Email</label>
                  <input
                    type="email"
                    value={editContactEmail}
                    onChange={(e) => setEditContactEmail(e.target.value)}
                    style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.35rem' }}>Contact Phone</label>
                  <input
                    type="text"
                    value={editContactPhone}
                    onChange={(e) => setEditContactPhone(e.target.value)}
                    style={{ width: '100%', padding: '0.65rem 0.85rem', background: "var(--bg-card-hover)", border: "1px solid var(--border)", borderRadius: '6px', color: "var(--text-main)" }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem', borderTop: "1px solid var(--border)", paddingTop: '1rem' }}>
                <button type="button" onClick={() => setEditingTenant(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={editSaving} className="btn btn-primary" style={{ fontWeight: 700 }}>
                  {editSaving ? 'Saving...' : 'Save Workspace Changes'}
                </button>
              </div>
            </form>

        </Modal>
      )}
    </div>
  );
};
