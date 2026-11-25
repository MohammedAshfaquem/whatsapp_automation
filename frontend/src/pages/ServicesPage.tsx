import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { Service } from '../types';
import { fetchApi } from '../api/client';
import { Plus, Phone } from 'lucide-react';

export const ServicesPage: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  // New Service Form
  const [name, setName] = useState('');
  const [category, setCategory] = useState('Standard Service');
  const [priceType, setPriceType] = useState('FIXED');
  const [priceAmount, setPriceAmount] = useState('999.00');
  const [contactNumber, setContactNumber] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadServices = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{ services: Service[] }>('/api/services/');
      setServices(data.services || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadServices();
  }, []);

  const handleToggle = async (serviceId: number) => {
    try {
      await fetchApi(`/services/${serviceId}/toggle/`, {
        method: 'POST',
      });
      await loadServices();
    } catch (err: any) {
      alert(err?.error || 'Could not toggle service');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await fetchApi('/api/services/', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          category,
          price_type: priceType,
          price_amount: priceAmount,
          contact_number: contactNumber.trim(),
          description: description.trim(),
        }),
      });
      setShowAddModal(false);
      setName('');
      setContactNumber('');
      setDescription('');
      await loadServices();
    } catch (err: any) {
      setError(err?.error || 'Could not create service');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Services & Catalog</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Offerings automatically grounded in AI bot replies and consultation bookings.
          </p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
          <Plus size={16} /> Add Service
        </button>
      </div>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Service Name</th>
              <th>Category</th>
              <th>Pricing Mode</th>
              <th>Amount</th>
              <th>Assigned WhatsApp Contact</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {services.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading services...' : 'No services in catalog yet.'}
                </td>
              </tr>
            ) : (
              services.map((s) => (
                <tr key={s.id}>
                  <td>
                    <span className={`badge ${s.is_active ? 'badge-green' : 'badge-gray'}`}>
                      {s.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600 }}>{s.name}</td>
                  <td>
                    <span className="badge badge-gray">{s.category}</span>
                  </td>
                  <td>{s.price_type_display}</td>
                  <td style={{ fontWeight: 600, color: "var(--primary)" }}>
                    {s.price_amount ? `₹${Number(s.price_amount).toLocaleString()}` : 'Inspection / Quote'}
                  </td>
                  <td>
                    {s.contact_number ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: "var(--text-muted)" }}>
                        <Phone size={13} style={{ color: "var(--primary)" }} /> {s.contact_number}
                      </span>
                    ) : (
                      'Default Line'
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      onClick={() => handleToggle(s.id)}
                      className={`btn btn-sm ${s.is_active ? 'btn-secondary' : 'btn-primary'}`}
                    >
                      {s.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <Modal title={"Add Catalog Service"} onClose={() => setShowAddModal(false)}>
            
            <form onSubmit={handleCreate} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{error}</div>}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Service Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-field"
                  placeholder="e.g. AC Deep Cleaning Service"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Category</label>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="input-field"
                  placeholder="Maintenance, Repair, Installation..."
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Price Type</label>
                <select value={priceType} onChange={(e) => setPriceType(e.target.value)} className="input-field">
                  <option value="FIXED">Fixed Price</option>
                  <option value="STARTING_FROM">Starting From</option>
                  <option value="INSPECTION_REQUIRED">Inspection Required</option>
                  <option value="CUSTOM_QUOTE">Custom Quote</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Price Amount (INR)</label>
                <input
                  type="number"
                  value={priceAmount}
                  onChange={(e) => setPriceAmount(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Direct WhatsApp Number</label>
                <input
                  type="text"
                  value={contactNumber}
                  onChange={(e) => setContactNumber(e.target.value)}
                  className="input-field"
                  placeholder="+919876543210 (Optional specialized line)"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowAddModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Add Service'}
                </button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};
