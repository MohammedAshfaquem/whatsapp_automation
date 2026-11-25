import React, { useEffect, useRef, useState } from 'react';
import { fetchApi } from '../api/client';
const softwareGroups = [{title:'Software accounts',resources:['users']}];
const clientGroups = [{title:'WhatsApp diagnostics',resources:['deliveries','webhooks','templates']}];
type Row = Record<string, any>;
type Result = { items: Row[]; total: number; page: number; page_size: number };
const label = (s: string) => s.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
const display = (v: any): string => v == null ? '—' : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : typeof v === 'object' ? JSON.stringify(v) : String(v);
const errorText = (e: any) => e?.error || e?.message || 'Unable to load operations.';
export const PlatformOperationsPage: React.FC = () => <OperationsTable />;
export const ClientDiagnostics: React.FC = () => <OperationsTable client />;
const OperationsTable: React.FC<{client?:boolean}> = ({client=false}) => {
  const groups=client ? clientGroups : softwareGroups;
  const base=client ? '/api/client/operations' : '/api/platform/operations';
  const detailVersion = useRef(0);
  const [resource, setResource] = useState(client ? 'deliveries' : 'users');
  const [draft, setDraft] = useState({ tenant_id: '', status: '', q: '' });
  const [filters, setFilters] = useState(draft);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Result>({ items: [], total: 0, page: 1, page_size: 25 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<Row | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [saving, setSaving] = useState(false);
  const saveUser = async (event: React.FormEvent) => {
    event.preventDefault(); if (!editing) return;
    setSaving(true); setError('');
    try {
      const payload: any = { full_name: editing.full_name, email: editing.email };
      if (editing.platform_role !== undefined) payload.platform_role = editing.platform_role;
      await fetchApi('/api/platform/operations/users/' + editing.id + '/', { method: 'PATCH', body: JSON.stringify(payload) });
      setEditing(null); setRevision(v => v + 1);
    } catch (e) { setError(errorText(e)); }
    finally { setSaving(false); }
  };
  const revokeUserSessions = async (userId: number) => {
    setSaving(true); setError('');
    try {
      await fetchApi('/api/platform/operations/users/' + userId + '/revoke-sessions/', { method: 'POST' });
      setRevision(v => v + 1);
    } catch (e) { setError(errorText(e)); }
    finally { setSaving(false); }
  };
  useEffect(() => {
    let active = true;
    detailVersion.current += 1; setDetailLoading(false);
    setLoading(true); setError(''); setDetail(null); setEditing(null);
    const params = new URLSearchParams({ ...filters, page: String(page) });
    fetchApi<Result>(`${base}/${resource}/?${params}`).then(result => { if (active) setData(result); }).catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; detailVersion.current += 1; };
  }, [resource, filters, page, revision]);
  const inspect = async (row: Row) => {
    const version = ++detailVersion.current;
    setDetail(null); setDetailLoading(true); setError('');
    try { const result = await fetchApi<{ item: Row }>(`${base}/${resource}/${row.id}/`); if (version === detailVersion.current) setDetail(result.item); }
    catch (e) { if (version === detailVersion.current) setError(errorText(e)); }
    finally { if (version === detailVersion.current) setDetailLoading(false); }
  };
  const columns = Array.from(new Set(data.items.flatMap(row => Object.keys(row)))).filter(key => key !== 'tenant_url');
  return <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '90rem', margin: '0 auto' }}>
    <div><h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>{client ? 'WhatsApp Diagnostics' : 'Users'}</h1><p style={{ color: "var(--text-muted)" }}>{client ? 'Review delivery failures, webhook activity and templates for this workspace.' : 'Manage software user accounts and workspace membership.'}</p></div>
    <nav aria-label="Operations resources" style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>{groups.map(group => <div key={group.title}><h2 style={{ fontSize: '.8rem', color: "var(--text-muted)", marginBottom: '.5rem' }}>{group.title}</h2><div role="tablist" aria-label={group.title} style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem' }}>{group.resources.map(name => <button key={name} role="tab" aria-selected={resource === name} className={`btn btn-sm ${resource === name ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setResource(name); setPage(1); setDraft(v => ({ ...v, status: '' })); setFilters(v => ({ ...v, status: '' })); }}>{label(name)}</button>)}</div></div>)}</nav>
    <form onSubmit={e => { e.preventDefault(); setFilters({ ...draft }); setPage(1); }} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: '.75rem' }}>
      {((client ? ['status', 'q'] : ['tenant_id', 'q']) as Array<'tenant_id'|'status'|'q'>).map(key => <label key={key} style={{ display: 'grid', gap: '.35rem', color: "var(--text-main)" }}>{key === 'tenant_id' ? 'Tenant ID' : key === 'q' ? 'Search' : 'Status'}<input className="form-input" type={key === 'tenant_id' ? 'number' : 'text'} min={key === 'tenant_id' ? 1 : undefined} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })} placeholder={key === 'status' ? 'All statuses' : ''} /></label>)}
      <button className="btn btn-primary" type="submit">Apply filters</button><button className="btn btn-secondary" type="button" onClick={() => setRevision(v => v + 1)}>Refresh</button>
    </form>
    {error && <div role="alert" style={{ color: "var(--danger)" }}>{error}</div>}
    <div className="table-container"><table className="custom-table"><caption style={{ textAlign: 'left', padding: '.75rem', color: "var(--text-muted)" }}>{label(resource)} · {data.total} records</caption><thead><tr>{columns.map(key => <th key={key}>{label(key)}</th>)}{resource === 'deliveries' && <th>Investigation</th>}{resource === 'users' && <th>Account</th>}</tr></thead><tbody>{loading ? <tr><td colSpan={columns.length + 1}>Loading operations...</td></tr> : error ? null : data.items.length === 0 ? <tr><td colSpan={columns.length + 1}>No records found.</td></tr> : data.items.map((row, index) => <tr key={row.id ?? index}>{columns.map(key => <td key={key} style={{ maxWidth: '24rem', overflowWrap: 'anywhere' }}>{!client && key === 'tenant_name' && row.tenant_id ? <a href={'/app/platform/tenants?tenant_id=' + encodeURIComponent(row.tenant_id)}>{display(row[key])}</a> : display(row[key])}</td>)}{resource === 'deliveries' && <td><button className="btn btn-sm btn-secondary" onClick={() => inspect(row)}>Inspect {row.id}</button></td>}{resource === 'users' && <td><button className="btn btn-sm btn-secondary" onClick={() => setEditing({ ...row })}>Edit user {row.id}</button></td>}</tr>)}</tbody></table></div>
    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}><button className="btn btn-secondary" disabled={loading || page <= 1} onClick={() => setPage(v => v - 1)}>Previous</button><span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span><button className="btn btn-secondary" disabled={loading || page * data.page_size >= data.total} onClick={() => setPage(v => v + 1)}>Next</button></div>
    {editing && <form aria-label="Edit user" onSubmit={saveUser} style={{ display: 'flex', gap: '.75rem', flexWrap: 'wrap', alignItems: 'end' }}><h2>Edit user {editing.username}</h2><label>Full name<input className="form-input" value={editing.full_name || ''} onChange={e => setEditing({ ...editing, full_name: e.target.value })} /></label><label>Email<input className="form-input" type="email" value={editing.email || ''} onChange={e => setEditing({ ...editing, email: e.target.value })} /></label><label>Platform role<select className="form-input" value={editing.platform_role || ''} onChange={e => setEditing({ ...editing, platform_role: e.target.value })}><option value="">Standard User</option><option value="SUPER_ADMIN">SUPER_ADMIN</option><option value="SUPPORT">SUPPORT</option><option value="BILLING">BILLING</option><option value="READ_ONLY">READ_ONLY</option></select></label><button className="btn btn-primary" disabled={saving}>Save user</button><button type="button" className="btn btn-secondary" disabled={saving} onClick={() => revokeUserSessions(editing.id)}>Revoke Sessions</button><button type="button" className="btn btn-secondary" disabled={saving} onClick={() => setEditing(null)}>Cancel</button></form>}
    {detailLoading && <p role="status">Loading delivery details...</p>}
    {detail && <section aria-label="Delivery details" style={{ background: "var(--bg-card)", padding: '1.25rem', border: "1px solid var(--border)", borderRadius: '.5rem' }}><h2>Delivery {detail.id}</h2>{detail.status === 'UNKNOWN' && <p style={{ color: "var(--warning)" }}>Manual inspection required: the provider outcome is unknown. Verify provider delivery before taking further action.</p>}{['FAILED', 'PENDING'].includes(detail.status) && (detail.attempts_exhausted ?? detail.attempts >= (detail.max_attempts ?? 3)) && <p style={{ color: "var(--danger)" }}>Attempts exhausted: this delivery has reached the automatic attempt limit. Review the failure reason and provider record.</p>}{detail.status === 'FAILED' && !(detail.attempts_exhausted ?? detail.attempts >= (detail.max_attempts ?? 3)) && <p style={{ color: "var(--danger)" }}>Delivery failed. Review the failure reason and attempts below.</p>}<dl style={{ display: 'grid', gridTemplateColumns: 'minmax(8rem, 12rem) 1fr', gap: '.6rem' }}>{Object.entries(detail).map(([key, value]) => <React.Fragment key={key}><dt style={{ color: "var(--text-muted)" }}>{label(key)}</dt><dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{display(value)}</dd></React.Fragment>)}</dl><button className="btn btn-secondary" onClick={() => setDetail(null)}>Close details</button></section>}
  </div>;
};

