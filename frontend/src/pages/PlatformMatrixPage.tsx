import { Modal } from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { fetchApi } from '../api/client';
import {
  Check,
  Sliders,
  Copy,
  Users,
  RefreshCw,
  Save,
  CheckCircle2,
} from 'lucide-react';

interface PlanTierData {
  id: number;
  code: string;
  name: string;
  badge: string;
  monthly_price: string;
  currency: string;
  max_staff: number;
  max_contacts: number;
  max_services: number;
  max_documents: number;
  monthly_message_allowance: number;
  crm_enabled: boolean;
  ai_assistant_enabled: boolean;
  enabled_modules: string[];
  is_published: boolean;
}

interface CapabilityData {
  key: string;
  name: string;
  category: string;
  required_module: string | null;
  min_role: string;
  description: string;
}

interface ModuleData {
  key: string;
  name: string;
  category: string;
  status: string;
  description: string;
}

interface TenantItem {
  id: number;
  name: string;
  slug: string;
  current_plan_code: string;
  current_plan_name: string;
  subscription_status: string;
  is_active: boolean;
  max_staff: number;
  max_services: number;
}

interface OverrideItem {
  feature_key: string;
  name: string;
  category: string;
  override: string;
  reason: string;
  effective_allowed: boolean;
  explanation: string;
}

interface BulkImpactItem {
  tenant_id: number;
  name: string;
  current_plan: string;
  target_plan: string;
  staff_used: number;
  staff_limit_new: number;
  staff_overflow: number;
  contacts_used: number;
  contacts_limit_new: number;
  contacts_overflow: number;
  docs_used: number;
  docs_limit_new: number;
  message_allowance_new: number;
}

export const PlatformMatrixPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'matrix' | 'overrides' | 'bulk'>('matrix');
  const [plans, setPlans] = useState<PlanTierData[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityData[]>([]);
  const [tenants, setTenants] = useState<TenantItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Copy modal state
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copySource, setCopySource] = useState('');
  const [copyTarget, setCopyTarget] = useState('');
  const [copying, setCopying] = useState(false);

  // Overrides tab state
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null);
  const [tenantOverrides, setTenantOverrides] = useState<OverrideItem[]>([]);
  const [loadingOverrides, setLoadingOverrides] = useState(false);
  const [savingOverrides, setSavingOverrides] = useState(false);

  // Bulk assign tab state
  const [bulkTargetPlan, setBulkTargetPlan] = useState('');
  const [selectedTenantIds, setSelectedTenantIds] = useState<number[]>([]);
  const [bulkPreview, setBulkPreview] = useState<BulkImpactItem[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [executingBulk, setExecutingBulk] = useState(false);

  const loadMatrix = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchApi<{
        plans: PlanTierData[];
        capabilities: CapabilityData[];
        modules: ModuleData[];
        tenants: TenantItem[];
      }>('/api/platform/matrix/');
      setPlans(res.plans);
      setCapabilities(res.capabilities);
      setTenants(res.tenants);

      if (res.tenants.length > 0 && !selectedTenantId) {
        setSelectedTenantId(res.tenants[0].id);
      }
      if (res.plans.length > 0 && !bulkTargetPlan) {
        setBulkTargetPlan(res.plans[0].code);
      }
    } catch (err: any) {
      setError(err?.error || 'Failed to load access matrix data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMatrix();
  }, []);

  // Load tenant overrides when selectedTenantId changes
  useEffect(() => {
    if (selectedTenantId && activeTab === 'overrides') {
      loadTenantOverrides(selectedTenantId);
    }
  }, [selectedTenantId, activeTab]);

  const loadTenantOverrides = async (tId: number) => {
    try {
      setLoadingOverrides(true);
      setError(null);
      const res = await fetchApi<{ overrides: OverrideItem[] }>(
        `/api/platform/tenants/${tId}/overrides/`
      );
      setTenantOverrides(res.overrides);
    } catch (err: any) {
      setError(err?.error || 'Failed to load tenant overrides.');
    } finally {
      setLoadingOverrides(false);
    }
  };

  const handleTogglePlanModule = async (planCode: string, moduleKey: string) => {
    const plan = plans.find((p) => p.code === planCode);
    if (!plan) return;

    const currentModules = plan.enabled_modules || [];
    const nextModules = currentModules.includes(moduleKey)
      ? currentModules.filter((m) => m !== moduleKey)
      : [...currentModules, moduleKey];

    // Optimistic UI update
    setPlans((prev) =>
      prev.map((p) => (p.code === planCode ? { ...p, enabled_modules: nextModules } : p))
    );

    try {
      setError(null);
      await fetchApi(`/api/platform/matrix/plan/${planCode}/`, {
        method: 'POST',
        body: JSON.stringify({ enabled_modules: nextModules }),
      });
      setSuccess(`Plan '${plan.name}' updated.`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err?.error || 'Failed to update plan bundle.');
      loadMatrix();
    }
  };

  const handleSavePlanLimits = async (plan: PlanTierData) => {
    try {
      setError(null);
      await fetchApi(`/api/platform/matrix/plan/${plan.code}/`, {
        method: 'POST',
        body: JSON.stringify({
          max_staff: plan.max_staff,
          max_contacts: plan.max_contacts,
          max_services: plan.max_services,
          max_documents: plan.max_documents,
          monthly_message_allowance: plan.monthly_message_allowance,
          monthly_price: plan.monthly_price,
        }),
      });
      setSuccess(`Limits updated for plan '${plan.name}'.`);
      setTimeout(() => setSuccess(null), 3000);
      loadMatrix();
    } catch (err: any) {
      setError(err?.error || 'Failed to save plan limits.');
    }
  };

  const updatePlanField = (code: string, field: keyof PlanTierData, value: any) => {
    setPlans((prev) => prev.map((p) => (p.code === code ? { ...p, [field]: value } : p)));
  };

  const handleCopyBundle = async () => {
    if (!copySource || !copyTarget || copySource === copyTarget) return;
    try {
      setCopying(true);
      setError(null);
      await fetchApi('/api/platform/matrix/copy-bundle/', {
        method: 'POST',
        body: JSON.stringify({
          source_plan_code: copySource,
          target_plan_code: copyTarget,
        }),
      });
      setShowCopyModal(false);
      setSuccess(`Successfully copied bundle from ${copySource} to ${copyTarget}.`);
      loadMatrix();
    } catch (err: any) {
      setError(err?.error || 'Failed to copy bundle.');
    } finally {
      setCopying(false);
    }
  };

  const handleOverrideChange = (key: string, val: string) => {
    setTenantOverrides((prev) =>
      prev.map((o) => (o.feature_key === key ? { ...o, override: val } : o))
    );
  };

  const handleOverrideReasonChange = (key: string, reasonText: string) => {
    setTenantOverrides((prev) =>
      prev.map((o) => (o.feature_key === key ? { ...o, reason: reasonText } : o))
    );
  };

  const handleSaveOverrides = async () => {
    if (!selectedTenantId) return;
    try {
      setSavingOverrides(true);
      setError(null);
      const payload: Record<string, { override: string; reason: string }> = {};
      tenantOverrides.forEach((o) => {
        payload[o.feature_key] = { override: o.override, reason: o.reason };
      });

      await fetchApi(`/api/platform/tenants/${selectedTenantId}/overrides/`, {
        method: 'POST',
        body: JSON.stringify({ overrides: payload }),
      });
      setSuccess('Tenant capability overrides saved successfully.');
      loadTenantOverrides(selectedTenantId);
    } catch (err: any) {
      setError(err?.error || 'Failed to save overrides.');
    } finally {
      setSavingOverrides(false);
    }
  };

  const handlePreviewBulk = async () => {
    if (!bulkTargetPlan || selectedTenantIds.length === 0) return;
    try {
      setPreviewing(true);
      setError(null);
      const res = await fetchApi<{ impact: BulkImpactItem[] }>(
        '/api/platform/matrix/bulk-assign-preview/',
        {
          method: 'POST',
          body: JSON.stringify({
            target_plan_code: bulkTargetPlan,
            tenant_ids: selectedTenantIds,
          }),
        }
      );
      setBulkPreview(res.impact);
    } catch (err: any) {
      setError(err?.error || 'Failed to generate bulk preview.');
    } finally {
      setPreviewing(false);
    }
  };

  const handleExecuteBulk = async () => {
    if (!bulkTargetPlan || selectedTenantIds.length === 0) return;
    try {
      setExecutingBulk(true);
      setError(null);
      const res = await fetchApi<{ status: string; updated_count: number }>(
        '/api/platform/matrix/bulk-assign/',
        {
          method: 'POST',
          body: JSON.stringify({
            target_plan_code: bulkTargetPlan,
            tenant_ids: selectedTenantIds,
            confirm: true,
          }),
        }
      );
      setSuccess(`Successfully migrated ${res.updated_count} workspaces.`);
      setBulkPreview(null);
      setSelectedTenantIds([]);
      loadMatrix();
    } catch (err: any) {
      setError(err?.error || 'Bulk plan assignment failed.');
    } finally {
      setExecutingBulk(false);
    }
  };

  const toggleSelectTenant = (id: number) => {
    setSelectedTenantIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const selectAllTenants = () => {
    if (selectedTenantIds.length === tenants.length) {
      setSelectedTenantIds([]);
    } else {
      setSelectedTenantIds(tenants.map((t) => t.id));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '84rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>
            SaaS Plan Matrix & Entitlements
          </h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Authoritative capability bundles, tenant-specific INHERIT/ALLOW/DENY overrides, and bulk subscription migrations.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => {
              setCopySource(plans[0]?.code || '');
              setCopyTarget(plans[1]?.code || '');
              setShowCopyModal(true);
            }}
            className="btn-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Copy size={14} />
            Copy Plan Bundle
          </button>
          <button onClick={loadMatrix} className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {success && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(17, 183, 109, 0.15)', border: '1px solid rgba(17, 183, 109, 0.3)', borderRadius: '0.5rem', color: "var(--primary)", fontSize: '0.85rem' }}>
          {success}
        </div>
      )}

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', borderBottom: "1px solid var(--border)", paddingBottom: '0.5rem' }}>
        <button
          onClick={() => setActiveTab('matrix')}
          className={`btn-secondary ${activeTab === 'matrix' ? 'btn-primary' : ''}`}
          style={{ padding: '0.5rem 1rem' }}
        >
          Plan Entitlements Matrix
        </button>
        <button
          onClick={() => setActiveTab('overrides')}
          className={`btn-secondary ${activeTab === 'overrides' ? 'btn-primary' : ''}`}
          style={{ padding: '0.5rem 1rem' }}
        >
          Tenant Capability Overrides
        </button>
        <button
          onClick={() => setActiveTab('bulk')}
          className={`btn-secondary ${activeTab === 'bulk' ? 'btn-primary' : ''}`}
          style={{ padding: '0.5rem 1rem' }}
        >
          Bulk Plan Migration
        </button>
      </div>

      {/* TAB 1: Real Plans & Capabilities Matrix */}
      {activeTab === 'matrix' && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>
              Configured Subscription Plans ({plans.length})
            </h2>
            <span style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>
              Check or uncheck capability modules to edit plan bundle in real-time.
            </span>
          </div>

          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Capability / Feature</th>
                  <th>Module Key</th>
                  {plans.map((p) => (
                    <th key={p.code} style={{ textAlign: 'center' }}>
                      <div>{p.name}</div>
                      <div style={{ fontSize: '0.7rem', color: "var(--text-muted)", fontWeight: 400 }}>
                        {p.max_contacts.toLocaleString()} contacts • {p.monthly_message_allowance.toLocaleString()} msgs
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {capabilities.map((cap) => {
                  const reqMod = cap.required_module;
                  return (
                    <tr key={cap.key}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{cap.name}</div>
                        <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{cap.category} • Min role: {cap.min_role}</div>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: "var(--text-muted)", fontFamily: 'monospace' }}>
                        {reqMod || 'Core Base'}
                      </td>
                      {plans.map((p) => {
                        if (!reqMod) {
                          return (
                            <td key={p.code} style={{ textAlign: 'center' }}>
                              <Check size={16} style={{ color: "var(--primary)", margin: '0 auto' }} />
                            </td>
                          );
                        }
                        const isEnabled = (p.enabled_modules || []).includes(reqMod);
                        return (
                          <td key={p.code} style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={isEnabled}
                              onChange={() => handleTogglePlanModule(p.code, reqMod)}
                              style={{ width: '1.1rem', height: '1.1rem', cursor: 'pointer', accentColor: '#11B76D' }}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginTop: '1.5rem', marginBottom: '0.75rem' }}>
            Plan Quotas &amp; Limits Editor
          </h3>
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Plan</th>
                  <th>Max Staff</th>
                  <th>Max Contacts</th>
                  <th>Max Services</th>
                  <th>Max Docs</th>
                  <th>Monthly Msg Allowance</th>
                  <th>Monthly Price</th>
                  <th>Save</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((p) => (
                  <tr key={`limits-${p.code}`}>
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td><input className="input-field" type="number" min={1} max={10000} style={{ width: '5rem' }} value={p.max_staff} onChange={(e) => updatePlanField(p.code, 'max_staff', Number(e.target.value))} /></td>
                    <td><input className="input-field" type="number" min={1} style={{ width: '6.5rem' }} value={p.max_contacts} onChange={(e) => updatePlanField(p.code, 'max_contacts', Number(e.target.value))} /></td>
                    <td><input className="input-field" type="number" min={1} style={{ width: '5rem' }} value={p.max_services} onChange={(e) => updatePlanField(p.code, 'max_services', Number(e.target.value))} /></td>
                    <td><input className="input-field" type="number" min={1} style={{ width: '5rem' }} value={p.max_documents} onChange={(e) => updatePlanField(p.code, 'max_documents', Number(e.target.value))} /></td>
                    <td><input className="input-field" type="number" min={0} style={{ width: '6.5rem' }} value={p.monthly_message_allowance} onChange={(e) => updatePlanField(p.code, 'monthly_message_allowance', Number(e.target.value))} /></td>
                    <td><input className="input-field" type="number" min={0} step="0.01" style={{ width: '6rem' }} value={p.monthly_price ?? ''} onChange={(e) => updatePlanField(p.code, 'monthly_price', e.target.value)} /></td>
                    <td><button type="button" className="btn btn-sm btn-primary" onClick={() => handleSavePlanLimits(p)}>Save Limits</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: Tenant Capability Overrides */}
      {activeTab === 'overrides' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>
                  Tenant-Specific Capability Overrides
                </h2>
                <p style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>
                  Precedence: Explicit <strong>DENY</strong> blocks access regardless of plan. Explicit <strong>ALLOW</strong> unblocks capability for pilots or custom agreements.
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <label style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Select Workspace:</label>
                <select
                  className="input-field"
                  style={{ width: '16rem' }}
                  value={selectedTenantId || ''}
                  onChange={(e) => setSelectedTenantId(Number(e.target.value))}
                >
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.current_plan_name})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {loadingOverrides ? (
              <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading overrides...</div>
            ) : (
              <div className="table-container">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Capability</th>
                      <th>Category</th>
                      <th>Override Policy</th>
                      <th>Effective Status</th>
                      <th>Override Reason / Audit Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tenantOverrides.map((ov) => (
                      <tr key={ov.feature_key}>
                        <td style={{ fontWeight: 600 }}>{ov.name}</td>
                        <td style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>{ov.category}</td>
                        <td>
                          <select
                            className="input-field"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem', width: '9rem' }}
                            value={ov.override}
                            onChange={(e) => handleOverrideChange(ov.feature_key, e.target.value)}
                          >
                            <option value="INHERIT">INHERIT (Plan)</option>
                            <option value="ALLOW">ALLOW (Explicit)</option>
                            <option value="DENY">DENY (Explicit)</option>
                          </select>
                        </td>
                        <td>
                          <span className={`badge ${ov.effective_allowed ? 'badge-green' : 'badge-red'}`}>
                            {ov.effective_allowed ? 'Granted' : 'Blocked'}
                          </span>
                        </td>
                        <td>
                          <input
                            type="text"
                            className="input-field"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
                            placeholder="Add reason for override..."
                            value={ov.reason}
                            onChange={(e) => handleOverrideReasonChange(ov.feature_key, e.target.value)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
              <button
                type="button"
                onClick={handleSaveOverrides}
                className="btn-primary"
                disabled={savingOverrides}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Save size={16} />
                {savingOverrides ? 'Saving Overrides...' : 'Save Overrides'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Bulk Plan Migration */}
      {activeTab === 'bulk' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.5rem' }}>
              Bulk Workspace Plan Migration
            </h2>
            <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", marginBottom: '1.25rem' }}>
              Select target subscription plan, choose tenant workspaces to migrate, and preview concrete resource and seat impacts before executing.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>Target Plan:</label>
                <select
                  className="input-field"
                  style={{ width: '16rem' }}
                  value={bulkTargetPlan}
                  onChange={(e) => setBulkTargetPlan(e.target.value)}
                >
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name} ({p.max_contacts.toLocaleString()} contacts, {p.max_staff} seats)
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                onClick={handlePreviewBulk}
                className="btn-secondary"
                disabled={previewing || selectedTenantIds.length === 0}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Sliders size={16} />
                {previewing ? 'Computing Impact...' : `Preview Impact (${selectedTenantIds.length} Selected)`}
              </button>
            </div>

            {/* Tenant Selection Table */}
            <div className="table-container">
              <table className="custom-table">
                <thead>
                  <tr>
                    <th style={{ width: '3rem', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selectedTenantIds.length === tenants.length && tenants.length > 0}
                        onChange={selectAllTenants}
                        style={{ width: '1rem', height: '1rem', cursor: 'pointer', accentColor: '#11B76D' }}
                      />
                    </th>
                    <th>Workspace</th>
                    <th>Current Plan</th>
                    <th>Status</th>
                    <th>Seats Allocated</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => {
                    const isSelected = selectedTenantIds.includes(t.id);
                    return (
                      <tr key={t.id}>
                        <td style={{ textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectTenant(t.id)}
                            style={{ width: '1rem', height: '1rem', cursor: 'pointer', accentColor: '#11B76D' }}
                          />
                        </td>
                        <td style={{ fontWeight: 600 }}>{t.name}</td>
                        <td>{t.current_plan_name}</td>
                        <td>
                          <span className={`badge ${t.is_active ? 'badge-green' : 'badge-red'}`}>
                            {t.is_active ? 'Active' : 'Suspended'}
                          </span>
                        </td>
                        <td>{t.max_staff} seats</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Concrete Impact Confirmation Modal / Card */}
          {bulkPreview && (
            <div className="card" style={{ border: '1px solid #3b82f6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <Users size={18} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: "var(--text-main)" }}>
                  Migration Impact Preview for {bulkPreview.length} Workspace(s)
                </h2>
              </div>

              <div className="table-container" style={{ marginBottom: '1.25rem' }}>
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Workspace</th>
                      <th>Current → Target</th>
                      <th>Staff Seats Impact</th>
                      <th>Contacts Impact</th>
                      <th>Message Allowance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkPreview.map((imp) => (
                      <tr key={imp.tenant_id}>
                        <td style={{ fontWeight: 600 }}>{imp.name}</td>
                        <td>{imp.current_plan} → <strong>{imp.target_plan}</strong></td>
                        <td>
                          {imp.staff_used} / {imp.staff_limit_new} seats
                          {imp.staff_overflow > 0 && (
                            <span style={{ color: "var(--danger)", marginLeft: '0.5rem', fontWeight: 600 }}>
                              ⚠️ {imp.staff_overflow} seat overflow
                            </span>
                          )}
                        </td>
                        <td>
                          {imp.contacts_used} / {imp.contacts_limit_new}
                          {imp.contacts_overflow > 0 && (
                            <span style={{ color: "var(--danger)", marginLeft: '0.5rem', fontWeight: 600 }}>
                              ⚠️ {imp.contacts_overflow} overflow
                            </span>
                          )}
                        </td>
                        <td>{imp.message_allowance_new.toLocaleString()} msgs/mo</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={() => setBulkPreview(null)}
                  className="btn-secondary"
                >
                  Cancel Preview
                </button>
                <button
                  type="button"
                  onClick={handleExecuteBulk}
                  className="btn-primary"
                  disabled={executingBulk}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  <CheckCircle2 size={16} />
                  {executingBulk ? 'Migrating...' : 'Confirm & Execute Migration'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Copy Plan Bundle Modal */}
      {showCopyModal && (
        <Modal title="Copy Capability Bundle" onClose={() => setShowCopyModal(false)} maxWidth="30rem" zIndex={50} className="card" style={{ width: '30rem', border: "1px solid var(--border)" }}>

            <p style={{ fontSize: '0.85rem', color: "var(--text-muted)", marginBottom: '1.25rem' }}>
              Copy all enabled modules and resource allocations from a source plan to a destination plan.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Source Plan</label>
                <select
                  className="input-field"
                  value={copySource}
                  onChange={(e) => setCopySource(e.target.value)}
                >
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Destination Plan</label>
                <select
                  className="input-field"
                  value={copyTarget}
                  onChange={(e) => setCopyTarget(e.target.value)}
                >
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>{p.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button type="button" onClick={() => setShowCopyModal(false)} className="btn-secondary">
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCopyBundle}
                className="btn-primary"
                disabled={copying || !copySource || !copyTarget || copySource === copyTarget}
              >
                {copying ? 'Copying...' : 'Copy Bundle'}
              </button>
            </div>

        </Modal>
      )}
    </div>
  );
};
