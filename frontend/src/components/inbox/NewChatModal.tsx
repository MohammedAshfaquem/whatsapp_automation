import { Modal } from '../Modal';
import React, { useState, useEffect } from 'react';
import { fetchApi } from '../../api/client';
import { WhatsAppTemplateItem } from '../../types';
import {
  Search,
  UserPlus,
  Users,
  Send,
  AlertCircle,
  FileText,
  ShieldAlert,
} from 'lucide-react';

interface ContactOption {
  id: number;
  name: string;
  phone_number: string;
  lifecycle_stage?: string;
}

interface NewChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConversationCreated: (conversationId: number) => void;
}

export const NewChatModal: React.FC<NewChatModalProps> = ({
  isOpen,
  onClose,
  onConversationCreated,
}) => {
  const [tab, setTab] = useState<'existing' | 'new'>('existing');
  const [contacts, setContacts] = useState<ContactOption[]>([]);
  const [searchContact, setSearchContact] = useState('');
  const [selectedContact, setSelectedContact] = useState<ContactOption | null>(null);

  // New contact fields
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');

  // Template fields
  const [templates, setTemplates] = useState<WhatsAppTemplateItem[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<WhatsAppTemplateItem | null>(null);
  const [templateVars, setTemplateVars] = useState<string[]>([]);
  const [useTemplate, setUseTemplate] = useState(true);
  const [freeformMessage, setFreeformMessage] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setSelectedContact(null);
      setNewName('');
      setNewPhone('');
      setSelectedTemplate(null);
      setTemplateVars([]);
      setError(null);
      return;
    }

    const loadInitialData = async () => {
      setError(null);
      try {
        const [contactRes, tplRes] = await Promise.all([
          fetchApi<{ contacts: ContactOption[] }>('/api/crm/contacts/').catch(() => ({ contacts: [] })),
          fetchApi<{ templates: WhatsAppTemplateItem[] }>('/api/whatsapp/templates/').catch(() => ({ templates: [] })),
        ]);
        setContacts(contactRes.contacts || []);
        const tpls = tplRes.templates || [];
        setTemplates(tpls);
        const initialTemplate = tpls.find(t => t.status === 'APPROVED');
        setSelectedTemplate(initialTemplate || null);
        setTemplateVars([]);
        if (initialTemplate) {
          const varCount = new Set(initialTemplate.body_text.match(/\{\{\d+\}\}/g) || []).size;
          setTemplateVars(new Array(varCount).fill(''));
        }
      } catch (err: any) {
        setError(err?.error || 'Failed to load contacts or templates.');
      }
    };

    loadInitialData();
  }, [isOpen]);

  const handleTemplateChange = (templateId: string) => {
    const found = templates.find((t) => String(t.id) === templateId) || null;
    setSelectedTemplate(found);
    if (found) {
      const varCount = new Set(found.body_text.match(/\{\{\d+\}\}/g) || []).size;
      setTemplateVars(new Array(varCount).fill(''));
    } else {
      setTemplateVars([]);
    }
  };

  const handleVarChange = (index: number, value: string) => {
    const updated = [...templateVars];
    updated[index] = value;
    setTemplateVars(updated);
  };

  const renderPreviewText = () => {
    if (!selectedTemplate) return '';
    let text = selectedTemplate.body_text;
    templateVars.forEach((v, idx) => {
      const placeholder = `{{${idx + 1}}}`;
      text = text.split(placeholder).join(v || `[Variable ${idx + 1}]`);
    });
    return text;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    let contactId: number | undefined;
    let phoneNumber: string | undefined;
    let contactName: string | undefined;

    if (tab === 'existing') {
      if (!selectedContact) {
        setError('Please select an existing contact to message.');
        return;
      }
      contactId = selectedContact.id;
    } else {
      if (!newPhone.trim()) {
        setError('Please enter a valid international phone number.');
        return;
      }
      const cleaned = newPhone.trim().replace(/\s+/g, '');
      if (!/^\+?[1-9]\d{7,14}$/.test(cleaned.replace(/\s+/g, ''))) {
        setError('Please enter a valid E.164 phone number (e.g. +14155552671 or +919876543210).');
        return;
      }
      phoneNumber = cleaned.startsWith('+') ? cleaned : `+${cleaned}`;
      contactName = newName.trim();
    }

    if (useTemplate && (!selectedTemplate || selectedTemplate.status !== 'APPROVED')) {
      setError('Please select a Meta-approved template.');
      return;
    }
    if (useTemplate && templateVars.some(value => !value.trim())) {
      setError('Template variables cannot be empty.');
      return;
    }
    if (!useTemplate && !freeformMessage.trim()) {
      setError('Please enter a message.');
      return;
    }
    try {
      setSubmitting(true);
      const payload: any = {
        contact_id: contactId,
        phone_number: phoneNumber,
        name: contactName,
      };

      if (useTemplate && selectedTemplate) {
        payload.template_name = selectedTemplate.name;
        payload.template_language = selectedTemplate.language;
        payload.template_variables = templateVars.map(value => value.trim());
      } else {
        payload.message_text = freeformMessage.trim();
      }

      const res = await fetchApi<{ conversation_id: number; message?: string }>('/api/inbox/conversations/start/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (res.conversation_id) {
        onConversationCreated(res.conversation_id);
        onClose();
      }
    } catch (err: any) {
      setError(err?.error || 'Failed to start conversation.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const filteredContacts = contacts.filter((c) => {
    const q = searchContact.toLowerCase();
    return (
      (c.name && c.name.toLowerCase().includes(q)) ||
      (c.phone_number && c.phone_number.includes(q))
    );
  });

  return (
    <Modal title="New WhatsApp Conversation" onClose={onClose} maxWidth="38rem" zIndex={50} style={{
          width: '100%',
          padding: '1.25rem',
          maxWidth: '38rem',
          maxHeight: '90vh',
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: '0.75rem',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
        }}>

        {/* Form Body */}
        <form
          onSubmit={handleSubmit}
          style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}
        >
          {error && (
            <div
              style={{
                padding: '0.65rem 0.85rem',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: '0.5rem',
                color: "var(--danger)",
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.45rem',
              }}
            >
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          {/* Contact Selection Tabs */}
          <div>
            <label style={{ fontSize: '0.78rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.4rem' }}>
              Select Recipient
            </label>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <button
                type="button"
                onClick={() => setTab('existing')}
                className={`btn btn-sm ${tab === 'existing' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1, fontSize: '0.78rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem' }}
              >
                <Users size={13} /> Existing CRM Contact
              </button>
              <button
                type="button"
                onClick={() => setTab('new')}
                className={`btn btn-sm ${tab === 'new' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1, fontSize: '0.78rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem' }}
              >
                <UserPlus size={13} /> New Contact Number
              </button>
            </div>

            {tab === 'existing' ? (
              <div>
                <div style={{ position: 'relative', marginBottom: '0.5rem' }}>
                  <Search size={13} style={{ position: 'absolute', left: '0.75rem', top: '0.65rem', color: "var(--text-muted)" }} />
                  <input
                    type="text"
                    placeholder="Search contact by name or phone..."
                    value={searchContact}
                    onChange={(e) => setSearchContact(e.target.value)}
                    className="input-field"
                    style={{ paddingLeft: '2.1rem', fontSize: '0.8rem' }}
                  />
                </div>
                <div
                  style={{
                    maxHeight: '8rem',
                    overflowY: 'auto',
                    border: "1px solid var(--border)",
                    borderRadius: '0.5rem',
                    backgroundColor: "var(--bg-card)",
                  }}
                >
                  {filteredContacts.length === 0 ? (
                    <div style={{ padding: '1rem', textAlign: 'center', color: "var(--text-muted)", fontSize: '0.78rem' }}>
                      No contacts found matching search.
                    </div>
                  ) : (
                    filteredContacts.map((c) => {
                      const isSelected = selectedContact?.id === c.id;
                      return (
                        <div
                          key={c.id}
                          onClick={() => setSelectedContact(c)}
                          style={{
                            padding: '0.5rem 0.75rem',
                            borderBottom: "1px solid var(--border)",
                            backgroundColor: isSelected ? 'rgba(17, 183, 109, 0.15)' : 'transparent',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div>
                            <div style={{ fontSize: '0.82rem', fontWeight: 600, color: isSelected ? "var(--primary)" : "var(--text-main)" }}>
                              {c.name || 'Unnamed Contact'}
                            </div>
                            <div style={{ fontSize: '0.72rem', color: "var(--text-muted)" }}>{c.phone_number}</div>
                          </div>
                          {c.lifecycle_stage && (
                            <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                              {c.lifecycle_stage}
                            </span>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.25rem' }}>
                    Customer Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Rahul Sharma"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="input-field"
                    style={{ fontSize: '0.8rem' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.75rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.25rem' }}>
                    Phone Number (E.164 with Country Code) *
                  </label>
                  <input
                    type="tel"
                    placeholder="+919876543210 or +14155552671"
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value)}
                    className="input-field"
                    style={{ fontSize: '0.8rem' }}
                    required={tab === 'new'}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Meta 24-Hour Customer Service Window Gate */}
          <div
            style={{
              padding: '0.75rem 0.9rem',
              backgroundColor: 'var(--primary-light)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              borderRadius: '0.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
              <FileText size={14} style={{ color: "var(--primary)" }} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: "var(--primary)" }}>
                Meta 24-Hour Customer Service Window Rule
              </span>
            </div>
            <p style={{ fontSize: '0.72rem', color: "var(--text-muted)", margin: 0, lineHeight: 1.4 }}>
              Business-initiated messages outside the 24-hour service window must use a Meta-approved template.
            </p>
          </div>

          {/* Template Selection & Variables */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <label style={{ fontSize: '0.78rem', color: "var(--text-muted)", margin: 0 }}>
                Meta Approved Template
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input
                  type="checkbox"
                  id="useTemplateCheck"
                  checked={useTemplate}
                  onChange={(e) => setUseTemplate(e.target.checked)}
                />
                <label htmlFor="useTemplateCheck" style={{ fontSize: '0.72rem', color: "var(--text-main)", cursor: 'pointer' }}>
                  Use Approved Template (Recommended)
                </label>
              </div>
            </div>

            {useTemplate ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                <select
                  value={selectedTemplate?.id || ''}
                  onChange={(e) => handleTemplateChange(e.target.value)}
                  className="input-field"
                  style={{ fontSize: '0.8rem' }}
                >
                  <option value="" disabled>Select an approved template</option>
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id} disabled={tpl.status !== 'APPROVED'}>
                      {tpl.name} {tpl.status !== 'APPROVED' ? `[${tpl.status} - Not Approved]` : ''} ({tpl.category}) [{tpl.language}]
                    </option>
                  ))}
                </select>

                {templateVars.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.25rem' }}>
                    <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", fontWeight: 600 }}>
                      Template Variables ({templateVars.length}):
                    </div>
                    {templateVars.map((v, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '0.72rem', color: "var(--primary)", minWidth: '4.5rem' }}>
                          Variable &#123;&#123;{idx + 1}&#125;&#125;:
                        </span>
                        <input
                          type="text"
                          placeholder={`Value for {{${idx + 1}}}`}
                          value={v}
                          onChange={(e) => handleVarChange(idx, e.target.value)}
                          className="input-field"
                          style={{ flex: 1, fontSize: '0.78rem', padding: '0.35rem 0.55rem' }}
                        />
                      </div>
                    ))}
                  </div>
                )}

                {/* Live Preview Box */}
                <div
                  style={{
                    marginTop: '0.4rem',
                    padding: '0.65rem 0.85rem',
                    backgroundColor: "var(--bg-card)",
                    border: "1px dashed var(--border)",
                    borderRadius: '0.5rem',
                  }}
                >
                  <div style={{ fontSize: '0.68rem', color: "var(--primary)", fontWeight: 600, marginBottom: '0.25rem' }}>
                    Live Template Preview:
                  </div>
                  <div style={{ fontSize: '0.78rem', color: "var(--text-main)", whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>
                    {renderPreviewText() || 'Select a template to view preview.'}
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <textarea
                  rows={3}
                  placeholder="Free-form message (only works if 24-hour service window is open)..."
                  value={freeformMessage}
                  onChange={(e) => setFreeformMessage(e.target.value)}
                  className="input-field"
                  style={{ resize: 'none', fontSize: '0.8rem' }}
                />
                <p style={{ fontSize: '0.7rem', color: "var(--warning)", marginTop: '0.25rem' }}>
                  Caution: Meta Cloud API rejects free-form outbound messages if customer has not messaged in the last 24 hours.
                </p>
              </div>
            )}
          </div>

          {/* Opt-in & Consent Disclaimer */}
          <div
            style={{
              padding: '0.65rem 0.85rem',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              borderRadius: '0.5rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.45rem',
            }}
          >
            <ShieldAlert size={14} style={{ color: "var(--warning)", marginTop: '2px', flexShrink: 0 }} />
            <span style={{ fontSize: '0.72rem', color: "var(--text-main)", lineHeight: 1.35 }}>
              <strong>Notice:</strong> Saving a contact does not automatically grant permission or consent to message them.
              Ensure the recipient has explicitly opted in to receive WhatsApp communications from your business.
            </span>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={onClose}
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.45rem 0.85rem' }}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ fontSize: '0.8rem', padding: '0.45rem 1rem' }}
              disabled={submitting || (tab === 'existing' && !selectedContact)}
            >
              <Send size={13} /> {submitting ? 'Sending...' : 'Send Message & Start Chat'}
            </button>
          </div>
        </form>

    </Modal>
  );
};
