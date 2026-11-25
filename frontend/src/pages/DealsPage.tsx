import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { DealStageData, Contact } from '../types';
import { fetchApi } from '../api/client';
import {
  Plus,
  User,
  Phone,
  FileText,
  Download,
  Send,
} from 'lucide-react';

interface QuoteItem {
  id: number;
  quote_number: string;
  version: number;
  title: string;
  status: string;
  grand_total: string;
  currency: string;
  valid_until: string;
  created_at: string;
}

interface DealsPageProps {
  onNavigate?: (path: string) => void;
}

export const DealsPage: React.FC<DealsPageProps> = () => {
  const [stages, setStages] = useState<DealStageData[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);

  // New Deal State
  const [dealTitle, setDealTitle] = useState('');
  const [dealValue, setDealValue] = useState('50000');
  const [dealContactId, setDealContactId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lost Reason Modal State
  const [pendingTransition, setPendingTransition] = useState<{
    dealId: number;
    targetStageId: number;
    stageName: string;
  } | null>(null);
  const [lostReason, setLostReason] = useState('');
  const [transitionNotes, setTransitionNotes] = useState('');
  const [transitioning, setTransitioning] = useState(false);

  // Quotations Modal State
  const [selectedDealForQuotes, setSelectedDealForQuotes] = useState<{ id: number; title: string } | null>(null);
  const [quotes, setQuotes] = useState<QuoteItem[]>([]);
  const [quotesLoading, setQuotesLoading] = useState(false);
  const [showCreateQuote, setShowCreateQuote] = useState(false);
  const [quoteTitle, setQuoteTitle] = useState('Custom Solution Proposal');
  const [quoteValidUntil, setQuoteValidUntil] = useState('');
  const [quoteItems, setQuoteItems] = useState([
    { description: 'WhatsApp Business API Integration & Setup', unit_price: 25000, quantity: 1, tax_rate: 18 },
  ]);
  const [creatingQuote, setCreatingQuote] = useState(false);

  const loadDeals = async () => {
    try {
      const [dealsData, contactsData] = await Promise.all([
        fetchApi<{ stages: DealStageData[] }>('/api/crm/deals/'),
        fetchApi<{ contacts: Contact[] }>('/api/crm/contacts/'),
      ]);
      setStages(dealsData.stages || []);
      setContacts(contactsData.contacts || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadDeals();
  }, []);

  const handleStageSelect = (dealId: number, targetStageId: number) => {
    const targetStage = stages.find((s) => s.id === targetStageId);
    if (targetStage && targetStage.is_lost) {
      setPendingTransition({
        dealId,
        targetStageId,
        stageName: targetStage.name,
      });
      setLostReason('');
      setTransitionNotes('');
      return;
    }
    executeStageChange(dealId, targetStageId, '', '');
  };

  const executeStageChange = async (
    dealId: number,
    targetStageId: number,
    reason: string,
    notes: string
  ) => {
    try {
      await fetchApi(`/api/crm/deals/${dealId}/stage/`, {
        method: 'POST',
        body: JSON.stringify({
          stage_id: targetStageId,
          lost_reason: reason,
          notes,
        }),
      });
      setPendingTransition(null);
      await loadDeals();
    } catch (err: any) {
      alert(err?.error || 'Could not transition deal stage');
    }
  };

  const handleConfirmLost = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingTransition) return;
    try {
      setTransitioning(true);
      await executeStageChange(
        pendingTransition.dealId,
        pendingTransition.targetStageId,
        lostReason.trim(),
        transitionNotes.trim()
      );
    } finally {
      setTransitioning(false);
    }
  };

  const handleCreateDeal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dealTitle.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await fetchApi('/api/crm/deals/', {
        method: 'POST',
        body: JSON.stringify({
          title: dealTitle.trim(),
          value: dealValue,
          customer_id: dealContactId ? parseInt(dealContactId) : null,
        }),
      });
      setShowAddModal(false);
      setDealTitle('');
      setDealValue('50000');
      setDealContactId('');
      await loadDeals();
    } catch (err: any) {
      setError(err?.error || 'Could not create deal');
    } finally {
      setSaving(false);
    }
  };

  const loadQuotes = async (dealId: number) => {
    try {
      setQuotesLoading(true);
      const res = await fetchApi<{ quotes: QuoteItem[] }>(`/api/crm/deals/${dealId}/quotes/`);
      setQuotes(res.quotes || []);
    } catch (err) {
      console.error(err);
    } finally {
      setQuotesLoading(false);
    }
  };

  const handleOpenQuotes = (deal: { id: number; title: string }) => {
    setSelectedDealForQuotes(deal);
    loadQuotes(deal.id);
  };

  const handleCreateQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDealForQuotes) return;
    try {
      setCreatingQuote(true);
      await fetchApi(`/api/crm/deals/${selectedDealForQuotes.id}/quotes/`, {
        method: 'POST',
        body: JSON.stringify({
          title: quoteTitle.trim(),
          valid_until: quoteValidUntil || null,
          items: quoteItems,
        }),
      });
      setShowCreateQuote(false);
      await loadQuotes(selectedDealForQuotes.id);
    } catch (err: any) {
      alert(err?.error || 'Failed to create quote');
    } finally {
      setCreatingQuote(false);
    }
  };

  const handleUpdateQuoteStatus = async (quoteId: number, status: string) => {
    if (!selectedDealForQuotes) return;
    try {
      await fetchApi(`/api/crm/quotes/${quoteId}/status/`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      });
      await loadQuotes(selectedDealForQuotes.id);
    } catch (err: any) {
      alert(err?.error || 'Failed to update quote status');
    }
  };

  const handleDownloadPdf = (quoteId: number) => {
    window.open(`/api/crm/quotes/${quoteId}/pdf/`, '_blank');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: 'calc(100vh - 6.75rem)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Deals & Sales Pipeline</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Visual deal stages, conversion probability, and sales revenue pipeline.
          </p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
          <Plus size={16} /> New Deal
        </button>
      </div>

      {/* Kanban Board Container */}
      <div className="kanban-board" style={{ flex: 1 }}>
        {stages.map((stage) => (
          <div key={stage.id} className="kanban-column">
            <div className="kanban-header">
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem', color: "var(--text-main)" }}>
                  {stage.name}
                </div>
                <div style={{ fontSize: '0.725rem', color: "var(--text-muted)", marginTop: '0.15rem' }}>
                  {stage.deal_count} deals • ₹{Number(stage.total_value).toLocaleString()}
                </div>
              </div>
              <span className={`badge ${stage.is_won ? 'badge-green' : stage.is_lost ? 'badge-red' : 'badge-blue'}`}>
                {stage.win_probability}%
              </span>
            </div>

            <div className="kanban-list">
              {stage.deals.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem 1rem', color: "var(--text-muted)", fontSize: '0.75rem' }}>
                  No deals in this stage
                </div>
              ) : (
                stage.deals.map((deal) => (
                  <div key={deal.id} className="deal-card">
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', color: "var(--text-main)", marginBottom: '0.35rem' }}>
                      {deal.title}
                    </div>

                    <div style={{ fontSize: '1rem', fontWeight: 700, color: "var(--primary)", marginBottom: '0.5rem' }}>
                      ₹{Number(deal.value).toLocaleString()}
                    </div>

                    {deal.customer_name && (
                      <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.35rem' }}>
                        <User size={13} /> {deal.customer_name}
                      </div>
                    )}

                    {deal.customer_phone && (
                      <div style={{ fontSize: '0.725rem', color: "var(--text-muted)", display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.5rem' }}>
                        <Phone size={12} /> {deal.customer_phone}
                      </div>
                    )}

                    {/* Quotations Quick Action */}
                    <button
                      onClick={() => handleOpenQuotes({ id: deal.id, title: deal.title })}
                      className="btn btn-secondary"
                      style={{
                        width: '100%',
                        fontSize: '0.725rem',
                        padding: '0.3rem 0.5rem',
                        justifyContent: 'center',
                        marginBottom: '0.5rem',
                        gap: '0.35rem',
                      }}
                    >
                      <FileText size={13} style={{ color: "var(--primary)" }} /> View / Create Quotes
                    </button>

                    {/* Stage Transition Selector */}
                    <div style={{ borderTop: "1px solid var(--border)", paddingTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>Move to:</span>
                      <select
                        value={stage.id}
                        onChange={(e) => handleStageSelect(deal.id, parseInt(e.target.value))}
                        style={{
                          backgroundColor: "var(--bg-card)",
                          border: "1px solid var(--border)",
                          borderRadius: '0.25rem',
                          color: "var(--text-main)",
                          fontSize: '0.7rem',
                          padding: '0.2rem 0.4rem',
                        }}
                      >
                        {stages.map((st) => (
                          <option key={st.id} value={st.id}>
                            {st.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Lost Reason Modal */}
      {pendingTransition && (
        <Modal title={`Mark Deal as ${pendingTransition.stageName}`} onClose={() => setPendingTransition(null)}>
            

            <form onSubmit={handleConfirmLost} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <p style={{ fontSize: '0.85rem', color: "var(--text-muted)" }}>
                Please provide the lost reason and any customer feedback to help analyze sales conversion patterns.
              </p>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Reason for Lost Deal *
                </label>
                <select
                  value={lostReason}
                  onChange={(e) => setLostReason(e.target.value)}
                  className="input-field"
                  required
                >
                  <option value="">-- Select reason --</option>
                  <option value="Competitor chosen">Competitor chosen</option>
                  <option value="Pricing / budget constraints">Pricing / budget constraints</option>
                  <option value="Feature / technical mismatch">Feature / technical mismatch</option>
                  <option value="Project cancelled / timing not right">Project cancelled / timing not right</option>
                  <option value="No response / ghosted">No response / ghosted</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Additional Notes
                </label>
                <textarea
                  value={transitionNotes}
                  onChange={(e) => setTransitionNotes(e.target.value)}
                  className="input-field"
                  rows={2}
                  placeholder="Specific feedback or next follow-up date..."
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setPendingTransition(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={transitioning || !lostReason} className="btn btn-danger">
                  {transitioning ? 'Saving...' : 'Confirm Lost Stage'}
                </button>
              </div>
            </form>
          </Modal>
      )}

      {/* Add Deal Modal */}
      {showAddModal && (
        <Modal title={"Create New Deal"} onClose={() => setShowAddModal(false)}>
            
            <form onSubmit={handleCreateDeal} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{error}</div>}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Deal Title *</label>
                <input
                  type="text"
                  required
                  value={dealTitle}
                  onChange={(e) => setDealTitle(e.target.value)}
                  className="input-field"
                  placeholder="e.g. Enterprise WhatsApp Migration"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Deal Value (INR) *</label>
                <input
                  type="number"
                  required
                  value={dealValue}
                  onChange={(e) => setDealValue(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Associated Contact</label>
                <select
                  value={dealContactId}
                  onChange={(e) => setDealContactId(e.target.value)}
                  className="input-field"
                >
                  <option value="">Select a contact (optional)</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.phone_number})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowAddModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="btn btn-primary">
                  {saving ? 'Creating...' : 'Create Deal'}
                </button>
              </div>
            </form>
          </Modal>
      )}
      {/* Quotations Modal */}
      {selectedDealForQuotes && (
        <Modal title={"Quotations & Proposals"} onClose={() => setSelectedDealForQuotes(null)} style={{ maxWidth: '44rem' }}>
            <div style={{ padding: '1.25rem', borderBottom: "1px solid var(--border)", display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileText size={18} style={{ color: "var(--primary)" }} />
                  
                </div>
                <div style={{ fontSize: '0.75rem', color: "var(--text-muted)", marginTop: '0.2rem' }}>
                  Deal: {selectedDealForQuotes.title}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => setShowCreateQuote(true)} className="btn btn-sm btn-primary">
                  <Plus size={14} /> New Quote
                </button>
                
              </div>
            </div>

            <div style={{ padding: '1.25rem' }}>
              {quotesLoading ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: "var(--text-muted)" }}>Loading quotations...</div>
              ) : quotes.length === 0 ? (
                <div style={{ padding: '2.5rem', textAlign: 'center', color: "var(--text-muted)" }}>
                  <FileText size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.4 }} />
                  <p>No quotes issued for this deal yet.</p>
                  <button onClick={() => setShowCreateQuote(true)} className="btn btn-secondary" style={{ marginTop: '0.75rem' }}>
                    Generate First Quotation
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {quotes.map((q) => (
                    <div
                      key={q.id}
                      style={{
                        backgroundColor: "var(--bg-card)",
                        border: "1px solid var(--border)",
                        borderRadius: '0.375rem',
                        padding: '1rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ fontWeight: 700, color: "var(--text-main)", fontSize: '0.9rem' }}>
                            {q.quote_number} (v{q.version})
                          </span>
                          <span
                            style={{
                              padding: '0.15rem 0.4rem',
                              borderRadius: '0.25rem',
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              backgroundColor:
                                q.status === 'ACCEPTED'
                                  ? 'rgba(17, 183, 109, 0.2)'
                                  : q.status === 'DECLINED'
                                  ? 'rgba(239, 68, 68, 0.2)'
                                  : "var(--bg-card-hover)",
                              color:
                                q.status === 'ACCEPTED'
                                  ? "var(--primary)"
                                  : q.status === 'DECLINED'
                                  ? "var(--danger)"
                                  : "var(--text-main)",
                            }}
                          >
                            {q.status}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.8rem', color: "var(--text-muted)", marginTop: '0.25rem' }}>
                          {q.title} &bull; Total: <strong style={{ color: "var(--primary)" }}>₹{q.grand_total}</strong>
                        </div>
                        {q.valid_until && (
                          <div style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>
                            Valid until: {new Date(q.valid_until).toLocaleDateString()}
                          </div>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <button
                          onClick={() => handleDownloadPdf(q.id)}
                          className="btn btn-sm btn-secondary"
                          title="Download Clean PDF"
                        >
                          <Download size={13} /> PDF
                        </button>
                        {q.status === 'DRAFT' && (
                          <button
                            onClick={() => handleUpdateQuoteStatus(q.id, 'SENT')}
                            className="btn btn-sm btn-secondary"
                            title="Mark as Sent to Client"
                          >
                            <Send size={13} /> Mark Sent
                          </button>
                        )}
                        {q.status !== 'ACCEPTED' && (
                          <button
                            onClick={() => handleUpdateQuoteStatus(q.id, 'ACCEPTED')}
                            className="btn btn-sm btn-primary"
                            title="Mark Accepted / Won"
                          >
                            Accept
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Modal>
      )}

      {/* Create Quote Submodal */}
      {showCreateQuote && (
        <Modal title={"New Versioned Quotation"} onClose={() => setShowCreateQuote(false)} style={{ maxWidth: '36rem' }}>
            

            <form onSubmit={handleCreateQuote} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Quotation Subject / Title *
                </label>
                <input
                  type="text"
                  required
                  value={quoteTitle}
                  onChange={(e) => setQuoteTitle(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Valid Until Date
                </label>
                <input
                  type="date"
                  value={quoteValidUntil}
                  onChange={(e) => setQuoteValidUntil(e.target.value)}
                  className="input-field"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                  Line Item Description
                </label>
                <input
                  type="text"
                  required
                  value={quoteItems[0]?.description || ''}
                  onChange={(e) =>
                    setQuoteItems([{ ...quoteItems[0], description: e.target.value }])
                  }
                  className="input-field"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                    Unit Price (INR)
                  </label>
                  <input
                    type="number"
                    required
                    value={quoteItems[0]?.unit_price || 0}
                    onChange={(e) =>
                      setQuoteItems([{ ...quoteItems[0], unit_price: parseFloat(e.target.value) || 0 }])
                    }
                    className="input-field"
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                    Quantity
                  </label>
                  <input
                    type="number"
                    required
                    value={quoteItems[0]?.quantity || 1}
                    onChange={(e) =>
                      setQuoteItems([{ ...quoteItems[0], quantity: parseInt(e.target.value) || 1 }])
                    }
                    className="input-field"
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>
                    GST Tax (%)
                  </label>
                  <input
                    type="number"
                    required
                    value={quoteItems[0]?.tax_rate || 18}
                    onChange={(e) =>
                      setQuoteItems([{ ...quoteItems[0], tax_rate: parseFloat(e.target.value) || 0 }])
                    }
                    className="input-field"
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button type="button" onClick={() => setShowCreateQuote(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={creatingQuote} className="btn btn-primary">
                  {creatingQuote ? 'Generating...' : 'Save & Issue Quote'}
                </button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};

