import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { Contact, Company } from '../types';
import { fetchApi } from '../api/client';
import {
  Search,
  Plus,
  Phone,
  Mail,
  Clock,
  GitMerge,
  ShieldAlert,
  Send,
} from 'lucide-react';

interface ContactsPageProps {
  onNavigate?: (path: string) => void;
}

export const ContactsPage: React.FC<ContactsPageProps> = () => {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedContact, setSelectedContact] = useState<any | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'notes' | 'deals'>('timeline');
  const [showImportModal, setShowImportModal] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [csvPreview, setCsvPreview] = useState<any | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [dupStrategy, setDupStrategy] = useState<'skip' | 'update'>('skip');
  const [editTagsText, setEditTagsText] = useState('');
  const [editCustomKey, setEditCustomKey] = useState('');
  const [editCustomVal, setEditCustomVal] = useState('');
  const [savingFields, setSavingFields] = useState(false);

  // New Note State
  const [newNoteContent, setNewNoteContent] = useState('');
  const [savingNote, setSavingNote] = useState(false);

  // Merge Modal State
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeDuplicateId, setMergeDuplicateId] = useState<string>('');
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  // New Contact Form
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newCompanyId, setNewCompanyId] = useState('');
  const [newStage, setNewStage] = useState('LEAD');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (search) params.append('q', search);
      if (tagFilter.trim()) params.append('tag', tagFilter.trim());
      const [contactsData, companiesData] = await Promise.all([
        fetchApi<{ contacts: Contact[] }>(`/api/crm/contacts/?${params.toString()}`),
        fetchApi<{ companies: Company[] }>('/api/crm/companies/'),
      ]);
      setContacts(contactsData.contacts || []);
      setCompanies(companiesData.companies || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [search, tagFilter]);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const targetId = urlParams.get('id') || urlParams.get('contact_id');
    if (targetId) {
      const parsed = parseInt(targetId, 10);
      if (!isNaN(parsed)) {
        loadContactDetail(parsed);
      }
    }
  }, []);

  const loadContactDetail = async (contactId: number) => {
    try {
      const data = await fetchApi<any>(`/api/crm/contacts/${contactId}/`);
      setSelectedContact(data);
      setEditTagsText(Array.isArray(data?.contact?.tags) ? data.contact.tags.join(', ') : '');
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveTagsAndField = async () => {
    if (!selectedContact) return;
    try {
      setSavingFields(true);
      const tags = editTagsText.split(',').map((t) => t.trim()).filter(Boolean);
      const nextCustom = { ...(selectedContact.contact.custom_fields || {}) };
      if (editCustomKey.trim()) {
        nextCustom[editCustomKey.trim()] = editCustomVal.trim();
      }
      await fetchApi(`/api/crm/contacts/${selectedContact.contact.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ tags, custom_fields: nextCustom }),
      });
      setEditCustomKey('');
      setEditCustomVal('');
      await loadContactDetail(selectedContact.contact.id);
      await loadData();
    } catch (err: any) {
      alert(err?.error || 'Could not update tags or custom fields.');
    } finally {
      setSavingFields(false);
    }
  };

  const handleCsvPreview = async () => {
    try {
      setImportBusy(true);
      setImportError(null);
      const res = await fetchApi<any>('/api/crm/contacts/import-preview/', {
        method: 'POST',
        body: JSON.stringify({ csv_text: csvText }),
      });
      setCsvPreview(res);
    } catch (err: any) {
      setImportError(err?.error || 'Could not parse CSV.');
    } finally {
      setImportBusy(false);
    }
  };

  const handleCsvExecute = async () => {
    try {
      setImportBusy(true);
      setImportError(null);
      await fetchApi('/api/crm/contacts/import/', {
        method: 'POST',
        body: JSON.stringify({ csv_text: csvText, duplicate_strategy: dupStrategy }),
      });
      setShowImportModal(false);
      setCsvText('');
      setCsvPreview(null);
      await loadData();
    } catch (err: any) {
      setImportError(err?.error || 'CSV import failed.');
    } finally {
      setImportBusy(false);
    }
  };

  const handleCreateContact = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!newPhone.trim()) {
      setError('Phone number is required.');
      return;
    }

    try {
      setSaving(true);
      await fetchApi('/api/crm/contacts/', {
        method: 'POST',
        body: JSON.stringify({
          name: newName.trim(),
          phone_number: newPhone.trim(),
          email: newEmail.trim(),
          company_id: newCompanyId ? parseInt(newCompanyId) : null,
          lifecycle_stage: newStage,
        }),
      });
      setShowAddModal(false);
      setNewName('');
      setNewPhone('');
      setNewEmail('');
      setNewCompanyId('');
      await loadData();
    } catch (err: any) {
      setError(err?.error || 'Could not register contact');
    } finally {
      setSaving(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNoteContent.trim() || !selectedContact) return;
    try {
      setSavingNote(true);
      await fetchApi(`/api/crm/contacts/${selectedContact.contact.id}/notes/`, {
        method: 'POST',
        body: JSON.stringify({ content: newNoteContent.trim() }),
      });
      setNewNoteContent('');
      await loadContactDetail(selectedContact.contact.id);
    } catch (err: any) {
      alert(err?.error || 'Could not save internal note.');
    } finally {
      setSavingNote(false);
    }
  };

  const handleMergeContacts = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContact || !mergeDuplicateId) return;
    try {
      setMerging(true);
      setMergeError(null);
      await fetchApi('/api/crm/contacts/merge/', {
        method: 'POST',
        body: JSON.stringify({
          primary_id: selectedContact.contact.id,
          duplicate_id: parseInt(mergeDuplicateId),
        }),
      });
      setShowMergeModal(false);
      setMergeDuplicateId('');
      await loadContactDetail(selectedContact.contact.id);
      await loadData();
    } catch (err: any) {
      setMergeError(err?.error || 'Failed to merge contacts');
    } finally {
      setMerging(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Customer Contacts</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Unified directory of WhatsApp customers, company affiliations, internal notes, and activity timelines.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button onClick={() => { setShowImportModal(true); setImportError(null); setCsvPreview(null); }} className="btn btn-secondary">
            Import CSV
          </button>
          <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
            <Plus size={16} /> Add Contact
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="card" style={{ padding: '0.875rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 18rem', maxWidth: '24rem' }}>
          <Search size={15} style={{ position: 'absolute', left: '0.75rem', top: '0.75rem', color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search by contact name, phone, or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field"
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>
        <input
          type="text"
          aria-label="Filter by tag"
          placeholder="Filter by tag (e.g. vip)..."
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
          className="input-field"
          style={{ width: '14rem' }}
        />
      </div>

      {/* Main Table */}
      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Contact Name</th>
              <th>WhatsApp Phone</th>
              <th>Email</th>
              <th>Company</th>
              <th>Lifecycle Stage</th>
              <th>Registered</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {contacts.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading contacts...' : 'No contacts found.'}
                </td>
              </tr>
            ) : (
              contacts.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Phone size={13} style={{ color: "var(--primary)" }} /> {c.phone_number}
                    </span>
                  </td>
                  <td>
                    {c.email ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: "var(--text-muted)" }}>
                        <Mail size={13} /> {c.email}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td>
                    {c.company ? (
                      <span className="badge badge-gray">{c.company.name}</span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>Individual</span>
                    )}
                  </td>
                  <td>
                    <span className={`badge ${c.lifecycle_stage === 'CUSTOMER' ? 'badge-green' : 'badge-blue'}`}>
                      {c.lifecycle_stage}
                    </span>
                    {Array.isArray(c.tags) && c.tags.slice(0, 3).map((t) => (
                      <span key={t} className="badge badge-gray" style={{ marginLeft: '0.25rem', fontSize: '0.68rem' }}>
                        #{t}
                      </span>
                    ))}
                  </td>
                  <td style={{ color: "var(--text-muted)", fontSize: '0.8rem' }}>
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      onClick={() => {
                        setActiveTab('timeline');
                        loadContactDetail(c.id);
                      }}
                      className="btn btn-sm btn-secondary"
                    >
                      View Details
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Contact Details Modal */}
      {selectedContact && (
        <Modal title={selectedContact.contact.name} onClose={() => setSelectedContact(null)} style={{ maxWidth: '48rem', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
            {/* Header */}
            <div
              style={{
                padding: '1.25rem',
                borderBottom: "1px solid var(--border)",
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                
                <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.2rem' }}>
                  <span>{selectedContact.contact.phone_number}</span>
                  <span>•</span>
                  <span>{selectedContact.contact.email || 'No email'}</span>
                  <span>•</span>
                  <span className="badge badge-green" style={{ fontSize: '0.7rem' }}>{selectedContact.contact.lifecycle_status}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  onClick={() => setShowMergeModal(true)}
                  className="btn btn-sm btn-secondary"
                  title="Merge duplicate contact"
                >
                  <GitMerge size={14} /> Merge Duplicate
                </button>
                
              </div>
            </div>

            {/* Navigation Tabs */}
            <div style={{ display: 'flex', borderBottom: "1px solid var(--border)", padding: '0 1.25rem', backgroundColor: "var(--bg-card)" }}>
              <button
                onClick={() => setActiveTab('timeline')}
                style={{
                  padding: '0.75rem 1rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: activeTab === 'timeline' ? "var(--primary)" : "var(--text-muted)",
                  borderBottom: activeTab === 'timeline' ? '2px solid #11B76D' : '2px solid transparent',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Activity Timeline ({Array.isArray(selectedContact.timeline) ? selectedContact.timeline.length : (selectedContact.timeline?.items?.length || 0)})
              </button>
              <button
                onClick={() => setActiveTab('notes')}
                style={{
                  padding: '0.75rem 1rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: activeTab === 'notes' ? "var(--primary)" : "var(--text-muted)",
                  borderBottom: activeTab === 'notes' ? '2px solid #11B76D' : '2px solid transparent',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Internal Staff Notes ({selectedContact.notes?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab('deals')}
                style={{
                  padding: '0.75rem 1rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: activeTab === 'deals' ? "var(--primary)" : "var(--text-muted)",
                  borderBottom: activeTab === 'deals' ? '2px solid #11B76D' : '2px solid transparent',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Deals ({selectedContact.deals?.length || 0})
              </button>
            </div>

            {/* Tab Contents */}
            <div style={{ padding: '1.25rem', overflowY: 'auto', flex: 1 }}>
              {activeTab === 'timeline' && (() => {
                const timelineEvents = Array.isArray(selectedContact.timeline)
                  ? selectedContact.timeline
                  : (selectedContact.timeline?.items || selectedContact.timeline_data?.items || []);
                return (
                  <div>
                    <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.75rem' }}>
                      Tags &amp; Custom Fields
                    </h3>
                    <div style={{ display: 'grid', gap: '0.65rem', padding: '0.85rem', border: '1px solid var(--border)', borderRadius: '0.5rem', marginBottom: '1rem' }}>
                      <label style={{ fontSize: '0.8rem', display: 'grid', gap: '0.25rem' }}>
                        Tags (comma-separated)
                        <input className="input-field" value={editTagsText} onChange={(e) => setEditTagsText(e.target.value)} placeholder="vip, enterprise" />
                      </label>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'end' }}>
                        <label style={{ fontSize: '0.8rem', flex: 1 }}>
                          Custom Field Key
                          <input className="input-field" value={editCustomKey} onChange={(e) => setEditCustomKey(e.target.value)} placeholder="e.g. city" />
                        </label>
                        <label style={{ fontSize: '0.8rem', flex: 1 }}>
                          Value
                          <input className="input-field" value={editCustomVal} onChange={(e) => setEditCustomVal(e.target.value)} placeholder="e.g. Mumbai" />
                        </label>
                        <button type="button" className="btn btn-sm btn-primary" disabled={savingFields} onClick={handleSaveTagsAndField}>
                          {savingFields ? 'Saving...' : 'Save Tags & Fields'}
                        </button>
                      </div>
                      {selectedContact.contact.custom_fields && Object.keys(selectedContact.contact.custom_fields).length > 0 && (
                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', fontSize: '0.75rem' }}>
                          {Object.entries(selectedContact.contact.custom_fields).map(([k, v]) => (
                            <span key={k} className="badge badge-gray">{k}: {String(v)}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.75rem' }}>
                      Customer Activity Timeline
                    </h3>
                    {timelineEvents.length === 0 ? (
                      <div style={{ color: "var(--text-muted)", fontSize: '0.85rem' }}>No activity timeline records.</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        {timelineEvents.map((event: any, i: number) => (
                          <div
                            key={i}
                            style={{
                              padding: '0.75rem 1rem',
                              backgroundColor: "var(--bg-card)",
                              border: "1px solid var(--border)",
                              borderRadius: '0.5rem',
                              display: 'flex',
                              alignItems: 'flex-start',
                              gap: '0.75rem',
                            }}
                          >
                            <Clock size={16} style={{ color: "var(--primary)", marginTop: '0.2rem' }} />
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: "var(--text-main)" }}>
                                {event.title}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.15rem' }}>
                                {event.text || event.description || ''}
                              </div>
                              <div style={{ fontSize: '0.7rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                                {event.timestamp ? new Date(event.timestamp).toLocaleString() : ''}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {activeTab === 'notes' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ padding: '0.75rem', backgroundColor: 'var(--primary-light)', border: '1px solid var(--primary-border)', borderRadius: '0.5rem', color: "var(--primary)", fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <ShieldAlert size={16} />
                    <span>Internal Staff Notes are confidential and kept strictly separate from WhatsApp messages sent to customers.</span>
                  </div>

                  {/* Add Note Form */}
                  <form onSubmit={handleAddNote} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <textarea
                      value={newNoteContent}
                      onChange={(e) => setNewNoteContent(e.target.value)}
                      placeholder="Add an internal note about this contact (customer preferences, discussion summary, etc.)..."
                      className="input-field"
                      rows={3}
                      required
                    />
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button type="submit" disabled={savingNote || !newNoteContent.trim()} className="btn btn-primary btn-sm">
                        <Send size={14} /> {savingNote ? 'Saving...' : 'Add Internal Note'}
                      </button>
                    </div>
                  </form>

                  {/* Notes List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                    {(!selectedContact.notes || selectedContact.notes.length === 0) ? (
                      <div style={{ color: "var(--text-muted)", fontSize: '0.85rem' }}>No internal notes recorded yet.</div>
                    ) : (
                      selectedContact.notes.map((n: any) => (
                        <div
                          key={n.id}
                          style={{
                            padding: '0.75rem 1rem',
                            backgroundColor: "var(--bg-card)",
                            border: "1px solid var(--border)",
                            borderRadius: '0.5rem',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <strong style={{ fontSize: '0.8rem', color: "var(--primary)" }}>@{n.author__username || 'Staff'}</strong>
                            <span style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>
                              {new Date(n.created_at).toLocaleString()}
                            </span>
                          </div>
                          <p style={{ fontSize: '0.85rem', color: "var(--text-main)", whiteSpace: 'pre-wrap' }}>
                            {n.content}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'deals' && (
                <div>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: "var(--text-main)", marginBottom: '0.75rem' }}>
                    Linked Sales Deals
                  </h3>
                  {(!selectedContact.deals || selectedContact.deals.length === 0) ? (
                    <div style={{ color: "var(--text-muted)", fontSize: '0.85rem' }}>No linked deals found.</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {selectedContact.deals.map((d: any) => (
                        <div
                          key={d.id}
                          style={{
                            padding: '0.75rem 1rem',
                            backgroundColor: "var(--bg-card)",
                            border: "1px solid var(--border)",
                            borderRadius: '0.5rem',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem', color: "var(--text-main)" }}>{d.title}</div>
                            <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>
                              Stage: {d.stage_name} • {d.currency} {d.amount?.toLocaleString()}
                            </div>
                          </div>
                          <span className={`badge ${d.status === 'WON' ? 'badge-green' : d.status === 'LOST' ? 'badge-red' : 'badge-blue'}`}>
                            {d.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </Modal>
      )}

      {/* Merge Duplicate Contact Modal */}
      {showMergeModal && selectedContact && (
        <Modal title={"Merge Duplicate Contact"} onClose={() => setShowMergeModal(false)}>
            
            <form onSubmit={handleMergeContacts} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {mergeError && (
                <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{mergeError}</div>
              )}
              <p style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>
                Primary Record to Keep:{' '}
                <strong style={{ color: "var(--text-main)" }}>{selectedContact.contact.name}</strong> ({selectedContact.contact.phone_number}).
                All conversations, messages, notes, and deals from the duplicate will be safely consolidated into this record.
              </p>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Select Duplicate Contact to Merge *
                </label>
                <select
                  value={mergeDuplicateId}
                  onChange={(e) => setMergeDuplicateId(e.target.value)}
                  className="input-field"
                  required
                >
                  <option value="">-- Choose duplicate contact --</option>
                  {contacts
                    .filter((c) => c.id !== selectedContact.contact.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.phone_number}) {c.email ? `• ${c.email}` : ''}
                      </option>
                    ))}
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowMergeModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={merging || !mergeDuplicateId} className="btn btn-primary">
                  {merging ? 'Merging...' : 'Confirm & Merge Records'}
                </button>
              </div>
            </form>
          </Modal>
      )}

      {/* CSV Import Modal */}
      {showImportModal && (
        <Modal title="Import Contacts from CSV" onClose={() => setShowImportModal(false)} maxWidth="42rem">
          <div style={{ padding: '1.25rem', display: 'grid', gap: '0.85rem' }}>
            {importError && <div style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{importError}</div>}
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Include a header row (e.g. <code>phone_number,name,email,tags,city</code>). Importing contacts never grants marketing consent automatically.
            </p>
            <textarea
              rows={5}
              aria-label="CSV content"
              className="input-field"
              placeholder={"phone_number,name,email,tags,city\n+919876543210,Asha Nair,asha@example.com,vip,Kochi"}
              value={csvText}
              onChange={(e) => { setCsvText(e.target.value); setCsvPreview(null); }}
            />
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="input-field" style={{ width: 'auto' }} value={dupStrategy} onChange={(e) => setDupStrategy(e.target.value as any)}>
                <option value="skip">Skip existing contacts</option>
                <option value="update">Merge tags &amp; fields into existing</option>
              </select>
              <button type="button" className="btn btn-secondary" disabled={importBusy || !csvText.trim()} onClick={handleCsvPreview}>
                Preview Mapping
              </button>
              <button type="button" className="btn btn-primary" disabled={importBusy || !csvPreview} onClick={handleCsvExecute}>
                {importBusy ? 'Importing...' : 'Execute Import'}
              </button>
            </div>
            {csvPreview && (
              <div style={{ padding: '0.75rem', border: '1px solid var(--border)', borderRadius: '0.5rem', fontSize: '0.82rem' }}>
                <div><strong>Rows:</strong> {csvPreview.total_rows} · <strong>New:</strong> {csvPreview.valid_new_count} · <strong>Existing:</strong> {csvPreview.existing_count} · <strong>Invalid phone:</strong> {csvPreview.invalid_count} · <strong>Quota remaining:</strong> {csvPreview.quota_remaining}</div>
                <div style={{ color: 'var(--text-muted)', marginTop: '0.25rem' }}>Mapped fields: {JSON.stringify(csvPreview.mapping)}</div>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Add Contact Modal */}
      {showAddModal && (
        <Modal title={"Add New Contact"} onClose={() => setShowAddModal(false)}>
            

            <form onSubmit={handleCreateContact} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && (
                <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.5rem', color: "var(--danger)", fontSize: '0.85rem' }}>
                  {error}
                </div>
              )}

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Full Name</label>
                <input
                  type="text"
                  placeholder="e.g. Rahul Sharma"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  WhatsApp Phone Number <span style={{ color: "var(--danger)" }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="+919876543210"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  className="input-field"
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Email Address</label>
                <input
                  type="email"
                  placeholder="rahul@example.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Associated Company</label>
                <select
                  value={newCompanyId}
                  onChange={(e) => setNewCompanyId(e.target.value)}
                  className="input-field"
                >
                  <option value="">-- No Company (Individual) --</option>
                  {companies.map((comp) => (
                    <option key={comp.id} value={comp.id}>
                      {comp.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Lifecycle Stage</label>
                <select
                  value={newStage}
                  onChange={(e) => setNewStage(e.target.value)}
                  className="input-field"
                >
                  <option value="LEAD">Lead</option>
                  <option value="PROSPECT">Prospect</option>
                  <option value="CUSTOMER">Customer</option>
                  <option value="INACTIVE">Inactive</option>
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowAddModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Register Contact'}
                </button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};
