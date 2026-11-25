import Modal from '../components/Modal';
import React, { useEffect, useState } from 'react';
import { Activity, Contact } from '../types';
import { fetchApi } from '../api/client';
import { Plus, Check } from 'lucide-react';

interface TasksPageProps {
  onNavigate?: (path: string) => void;
}

export const TasksPage: React.FC<TasksPageProps> = () => {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('PENDING');
  const [showAddModal, setShowAddModal] = useState(false);

  // New Activity Form
  const [title, setTitle] = useState('');
  const [type, setType] = useState('TASK');
  const [priority, setPriority] = useState('MEDIUM');
  const [contactId, setContactId] = useState('');
  const [saving, setSaving] = useState(false);

  const loadActivities = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append('status', statusFilter);
      const [actData, contactsData] = await Promise.all([
        fetchApi<{ activities: Activity[] }>(`/api/crm/activities/?${params.toString()}`),
        fetchApi<{ contacts: Contact[] }>('/api/crm/contacts/'),
      ]);
      setActivities(actData.activities || []);
      setContacts(contactsData.contacts || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivities();
  }, [statusFilter]);

  const handleComplete = async (activityId: number) => {
    try {
      await fetchApi(`/api/crm/activities/${activityId}/complete/`, {
        method: 'POST',
      });
      await loadActivities();
    } catch (err: any) {
      alert(err?.error || 'Could not complete activity');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      setSaving(true);
      await fetchApi('/api/crm/activities/', {
        method: 'POST',
        body: JSON.stringify({
          title: title.trim(),
          activity_type: type,
          priority,
          customer_id: contactId ? parseInt(contactId) : null,
        }),
      });
      setShowAddModal(false);
      setTitle('');
      setContactId('');
      await loadActivities();
    } catch (err: any) {
      alert(err?.error || 'Could not create task');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Tasks & Follow-ups</h1>
          <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
            Schedule and track customer calls, consultations, and team reminders.
          </p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
          <Plus size={16} /> New Task
        </button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button
          onClick={() => setStatusFilter('PENDING')}
          className={`btn btn-sm ${statusFilter === 'PENDING' ? 'btn-primary' : 'btn-secondary'}`}
        >
          Pending
        </button>
        <button
          onClick={() => setStatusFilter('COMPLETED')}
          className={`btn btn-sm ${statusFilter === 'COMPLETED' ? 'btn-primary' : 'btn-secondary'}`}
        >
          Completed
        </button>
        <button
          onClick={() => setStatusFilter('')}
          className={`btn btn-sm ${statusFilter === '' ? 'btn-primary' : 'btn-secondary'}`}
        >
          All
        </button>
      </div>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Task Title</th>
              <th>Type</th>
              <th>Priority</th>
              <th>Contact</th>
              <th>Due Date</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {activities.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading tasks...' : 'No tasks matching current filter.'}
                </td>
              </tr>
            ) : (
              activities.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.status === 'COMPLETED' ? (
                      <span className="badge badge-green">Completed</span>
                    ) : a.is_overdue ? (
                      <span className="badge badge-red">Overdue</span>
                    ) : (
                      <span className="badge badge-amber">Pending</span>
                    )}
                  </td>
                  <td style={{ fontWeight: 600 }}>{a.title}</td>
                  <td>
                    <span className="badge badge-gray">{a.activity_type_display}</span>
                  </td>
                  <td>
                    <span className={`badge ${a.priority === 'HIGH' ? 'badge-red' : 'badge-amber'}`}>
                      {a.priority}
                    </span>
                  </td>
                  <td>
                    {a.customer_name ? (
                      <span>
                        {a.customer_name} <span style={{ color: "var(--text-muted)", fontSize: '0.75rem' }}>({a.customer_phone})</span>
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: a.is_overdue ? "var(--danger)" : "var(--text-muted)" }}>
                    {a.due_date ? new Date(a.due_date).toLocaleDateString() : 'No due date'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {a.status === 'PENDING' && (
                      <button onClick={() => handleComplete(a.id)} className="btn btn-sm btn-primary">
                        <Check size={14} /> Complete
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <Modal title={"Add Task"} onClose={() => setShowAddModal(false)}>
            
            <form onSubmit={handleCreate} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Task Title *</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="input-field"
                  placeholder="e.g. Follow up on proposal"
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Activity Type</label>
                <select value={type} onChange={(e) => setType(e.target.value)} className="input-field">
                  <option value="CALL">Phone Call</option>
                  <option value="WHATSAPP_FOLLOWUP">WhatsApp Follow-up</option>
                  <option value="MEETING">Consultation Meeting</option>
                  <option value="TASK">General Task</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Priority</label>
                <select value={priority} onChange={(e) => setPriority(e.target.value)} className="input-field">
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', color: "var(--text-muted)", display: 'block', marginBottom: '0.35rem' }}>Linked Contact</label>
                <select value={contactId} onChange={(e) => setContactId(e.target.value)} className="input-field">
                  <option value="">None</option>
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
                  {saving ? 'Creating...' : 'Create Task'}
                </button>
              </div>
            </form>
          </Modal>
      )}
    </div>
  );
};
