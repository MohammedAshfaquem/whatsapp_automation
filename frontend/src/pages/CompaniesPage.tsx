import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { Company } from '../types';
import { fetchApi } from '../api/client';
import { Plus, Globe, Users, Kanban } from 'lucide-react';

export const CompaniesPage: React.FC = () => {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [industry, setIndustry] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCompanies = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{ companies: Company[] }>('/api/crm/companies/');
      setCompanies(data.companies || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCompanies();
  }, []);

  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await fetchApi('/api/crm/companies/', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), domain: domain.trim(), industry: industry.trim() }),
      });
      setShowAddModal(false);
      setName('');
      setDomain('');
      setIndustry('');
      await loadCompanies();
    } catch (err: any) {
      setError(err?.error || 'Could not create company');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Companies & Accounts</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Organizational accounts, team contacts, and aggregate pipeline deals.
          </p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
          <Plus size={16} /> Add Company
        </button>
      </div>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Company Name</th>
              <th>Domain</th>
              <th>Industry</th>
              <th>Contacts Linked</th>
              <th>Deals Linked</th>
            </tr>
          </thead>
          <tbody>
            {companies.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading...' : 'No companies recorded yet.'}
                </td>
              </tr>
            ) : (
              companies.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td>
                    {c.domain ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: "var(--text-muted)" }}>
                        <Globe size={13} /> {c.domain}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <span className="badge badge-gray">{c.industry || 'General'}</span>
                  </td>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Users size={13} style={{ color: "var(--primary)" }} /> {c.contact_count} contacts
                    </span>
                  </td>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Kanban size={13} style={{ color: "var(--primary)" }} /> {c.deal_count} deals
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <Modal title={"Add Company"} onClose={() => setShowAddModal(false)}>
            
            <form onSubmit={handleCreateCompany} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{error}</div>}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Company Name *</label>
                <input type="text" required value={name} onChange={(e) => setName(e.target.value)} className="input-field" placeholder="Acme Technologies" />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Website / Domain</label>
                <input type="text" value={domain} onChange={(e) => setDomain(e.target.value)} className="input-field" placeholder="acme.com" />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Industry</label>
                <input type="text" value={industry} onChange={(e) => setIndustry(e.target.value)} className="input-field" placeholder="IT Services, Real Estate..." />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" onClick={() => setShowAddModal(false)} className="btn btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn btn-primary">{saving ? 'Saving...' : 'Create Company'}</button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};
