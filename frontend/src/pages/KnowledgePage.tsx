import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { FAQ, KnowledgeDocument } from '../types';
import { fetchApi } from '../api/client';
import { Plus, Trash2 } from 'lucide-react';

export const KnowledgePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'faqs' | 'docs'>('faqs');
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [docAllowance, setDocAllowance] = useState<{ count: number; limit: number }>({ count: 0, limit: 20 });

  // FAQ Modal
  const [showFaqModal, setShowFaqModal] = useState(false);
  const [faqQuestion, setFaqQuestion] = useState('');
  const [faqAnswer, setFaqAnswer] = useState('');
  const [faqCategory, setFaqCategory] = useState('General');

  // Document Modal
  const [showDocModal, setShowDocModal] = useState(false);
  const [docTitle, setDocTitle] = useState('');
  const [docCategory, setDocCategory] = useState('POLICY');
  const [docContent, setDocContent] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const data = await fetchApi<{
        faqs: FAQ[];
        documents: KnowledgeDocument[];
        doc_allowance: { count: number; limit: number };
      }>('/api/knowledge/');
      setFaqs(data.faqs || []);
      setDocuments(data.documents || []);
      if (data.doc_allowance) setDocAllowance(data.doc_allowance);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateFaq = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!faqQuestion.trim() || !faqAnswer.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await fetchApi('/api/knowledge/faqs/', {
        method: 'POST',
        body: JSON.stringify({ question: faqQuestion.trim(), answer: faqAnswer.trim(), category: faqCategory }),
      });
      setShowFaqModal(false);
      setFaqQuestion('');
      setFaqAnswer('');
      await loadData();
    } catch (err: any) {
      setError(err?.error || 'Could not save FAQ');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteFaq = async (id: number) => {
    if (!confirm('Are you sure you want to delete this FAQ?')) return;
    try {
      await fetchApi(`/api/knowledge/faqs/${id}/`, { method: 'DELETE' });
      await loadData();
    } catch (err: any) {
      alert(err?.error || 'Could not delete FAQ');
    }
  };

  const handleCreateDoc = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docTitle.trim() || !docContent.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await fetchApi('/api/knowledge/documents/', {
        method: 'POST',
        body: JSON.stringify({ title: docTitle.trim(), category: docCategory, content: docContent.trim() }),
      });
      setShowDocModal(false);
      setDocTitle('');
      setDocContent('');
      await loadData();
    } catch (err: any) {
      setError(err?.error || 'Could not upload document');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>AI Knowledge Base & Grounding</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Ground customer assistant responses with verified policies, documents, and FAQs.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {activeTab === 'faqs' ? (
            <button onClick={() => setShowFaqModal(true)} className="btn btn-primary">
              <Plus size={16} /> Add FAQ
            </button>
          ) : (
            <button onClick={() => setShowDocModal(true)} className="btn btn-primary">
              <Plus size={16} /> Upload Document
            </button>
          )}
        </div>
      </div>

      {/* Tabs and Allowance Meter */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setActiveTab('faqs')}
            style={{
              padding: '0.75rem 1.25rem',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'faqs' ? '2px solid #11B76D' : '2px solid transparent',
              color: activeTab === 'faqs' ? "var(--primary)" : "var(--text-muted)",
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            Frequently Asked Questions ({faqs.length})
          </button>
          <button
            onClick={() => setActiveTab('docs')}
            style={{
              padding: '0.75rem 1.25rem',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'docs' ? '2px solid #11B76D' : '2px solid transparent',
              color: activeTab === 'docs' ? "var(--primary)" : "var(--text-muted)",
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            Knowledge Documents ({documents.length})
          </button>
        </div>

        <div style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>
          Document Usage: <strong style={{ color: "var(--text-main)" }}>{docAllowance.count}</strong> / {docAllowance.limit} uploaded
        </div>
      </div>

      {/* FAQs Tab */}
      {activeTab === 'faqs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {faqs.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
              No FAQs defined yet. Click "Add FAQ" to ground your bot with common customer questions.
            </div>
          ) : (
            faqs.map((f) => (
              <div key={f.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                    <span className="badge badge-gray">{f.category}</span>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: "var(--text-main)" }}>{f.question}</h3>
                  </div>
                  <p style={{ fontSize: '0.875rem', color: "var(--text-main)", lineHeight: 1.4, whiteSpace: 'pre-wrap' }}>
                    {f.answer}
                  </p>
                </div>
                <button onClick={() => handleDeleteFaq(f.id)} className="btn btn-sm btn-danger" style={{ marginLeft: '1rem' }}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Documents Tab */}
      {activeTab === 'docs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {documents.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3rem', color: "var(--text-muted)" }}>
              No uploaded policy documents. Upload warranty terms or troubleshooting guides to enrich RAG retrieval.
            </div>
          ) : (
            documents.map((d) => (
              <div key={d.id} className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge badge-blue">{d.category}</span>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, color: "var(--text-main)" }}>{d.title}</h3>
                </div>
                <div style={{ fontSize: '0.85rem', color: "var(--text-muted)", maxHeight: '5rem', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {d.content}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Add FAQ Modal */}
      {showFaqModal && (
        <Modal title={"Add FAQ"} onClose={() => setShowFaqModal(false)}>
            
            <form onSubmit={handleCreateFaq} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{error}</div>}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Category</label>
                <input type="text" value={faqCategory} onChange={(e) => setFaqCategory(e.target.value)} className="input-field" placeholder="General, Pricing, Hours..." />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Customer Question *</label>
                <input type="text" required value={faqQuestion} onChange={(e) => setFaqQuestion(e.target.value)} className="input-field" placeholder="What are your working hours?" />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Verified Answer *</label>
                <textarea rows={4} required value={faqAnswer} onChange={(e) => setFaqAnswer(e.target.value)} className="input-field" placeholder="We operate Monday to Friday 9 AM to 6 PM IST." />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" onClick={() => setShowFaqModal(false)} className="btn btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn btn-primary">{saving ? 'Saving...' : 'Save FAQ'}</button>
              </div>
            </form>
          </Modal>
      )}

      {/* Add Document Modal */}
      {showDocModal && (
        <Modal title={"Upload Knowledge Document"} onClose={() => setShowDocModal(false)}>
            
            <form onSubmit={handleCreateDoc} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {error && <div style={{ color: "var(--danger)", fontSize: '0.85rem' }}>{error}</div>}
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Document Title *</label>
                <input type="text" required value={docTitle} onChange={(e) => setDocTitle(e.target.value)} className="input-field" placeholder="e.g. 30-Day Service Warranty Policy" />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Category</label>
                <select value={docCategory} onChange={(e) => setDocCategory(e.target.value)} className="input-field">
                  <option value="POLICY">Service Policy</option>
                  <option value="WARRANTY">Warranty Details</option>
                  <option value="TROUBLESHOOTING">Troubleshooting Guidance</option>
                  <option value="TERMS">Terms & Conditions</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Document Content *</label>
                <textarea rows={6} required value={docContent} onChange={(e) => setDocContent(e.target.value)} className="input-field" placeholder="Full text content for vector store ingestion..." />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" onClick={() => setShowDocModal(false)} className="btn btn-secondary">Cancel</button>
                <button type="submit" disabled={saving} className="btn btn-primary">{saving ? 'Uploading...' : 'Save Document'}</button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};
