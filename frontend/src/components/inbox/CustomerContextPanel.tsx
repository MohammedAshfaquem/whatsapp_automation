import { Modal } from '../Modal';
import React, { useEffect, useState, useRef } from 'react';
import { ContactDetailResponse } from '../../types';
import { fetchApi } from '../../api/client';
import {
  User,
  Phone,
  Mail,
  Building,
  UserCheck,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Plus,
  RefreshCw,
  X,
  Check,
  Send,
  Sparkles,
} from 'lucide-react';

interface CustomerContextPanelProps {
  customerId: number | null;
  conversationId?: number;
  handoffSummary?: string;
  onNavigate?: (path: string) => void;
  onClose?: () => void;
  isMobile?: boolean;
}

export const CustomerContextPanel: React.FC<CustomerContextPanelProps> = ({
  customerId,
  handoffSummary,
  onNavigate,
  onClose,
  isMobile,
}) => {
  const [data, setData] = useState<ContactDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isForbidden, setIsForbidden] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'notes' | 'deals' | 'tasks' | 'timeline'>('overview');

  // Internal Note form
  const [noteContent, setNoteContent] = useState('');
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);

  // New Task form
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskType, setTaskType] = useState('FOLLOW_UP');
  const [taskPriority, setTaskPriority] = useState('MEDIUM');
  const [taskDueDate, setTaskDueDate] = useState('');
  const [taskNotes, setTaskNotes] = useState('');
  const [isSubmittingTask, setIsSubmittingTask] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);

  // Task completing status
  const [completingTaskId, setCompletingTaskId] = useState<number | null>(null);

  // Race-condition & stale guards
  const activeCustomerIdRef = useRef<number | null>(null);
  activeCustomerIdRef.current = customerId;
  const requestIdRef = useRef(0);

  const loadCustomerDetail = async (targetId: number, quiet = false) => {
    if (activeCustomerIdRef.current !== targetId) return;
    const reqId = ++requestIdRef.current;

    if (!quiet) {
      setLoading(true);
      setError(null);
      setIsForbidden(false);
    }

    try {
      const res = await fetchApi<ContactDetailResponse>(`/api/crm/contacts/${targetId}/`);
      if (activeCustomerIdRef.current !== targetId || reqId !== requestIdRef.current) return;
      setData(res);
      setError(null);
      setIsForbidden(false);
    } catch (err: any) {
      if (activeCustomerIdRef.current !== targetId || reqId !== requestIdRef.current) return;
      if (err?.status === 403) {
        setIsForbidden(true);
        setError('You do not have permission to view contact details.');
      } else if (err?.status === 404) {
        setError('Contact record not found.');
      } else {
        setError(err?.error || 'Failed to load customer context.');
      }
    } finally {
      if (activeCustomerIdRef.current === targetId && reqId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    setData(null);
    setError(null);
    setIsForbidden(false);
    setNoteContent('');
    setNoteError(null);
    setShowTaskModal(false);

    if (customerId) {
      loadCustomerDetail(customerId);
    }
  }, [customerId]);

  // Handle Add Note
  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId || !noteContent.trim() || isSubmittingNote) return;

    try {
      setIsSubmittingNote(true);
      setNoteError(null);
      await fetchApi(`/api/crm/contacts/${customerId}/notes/`, {
        method: 'POST',
        body: JSON.stringify({ content: noteContent.trim() }),
      });
      setNoteContent('');
      await loadCustomerDetail(customerId, true);
    } catch (err: any) {
      setNoteError(err?.error || 'Failed to add internal note.');
    } finally {
      setIsSubmittingNote(false);
    }
  };

  // Handle Complete Task
  const handleCompleteTask = async (taskId: number) => {
    if (!customerId || completingTaskId === taskId) return;

    try {
      setCompletingTaskId(taskId);
      await fetchApi(`/api/crm/activities/${taskId}/complete/`, {
        method: 'POST',
      });
      await loadCustomerDetail(customerId, true);
    } catch (err: any) {
      alert(err?.error || 'Failed to mark task as completed.');
    } finally {
      setCompletingTaskId(null);
    }
  };

  // Handle Add Follow-up Task
  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId || !taskTitle.trim() || isSubmittingTask) return;

    try {
      setIsSubmittingTask(true);
      setTaskError(null);
      await fetchApi('/api/crm/activities/', {
        method: 'POST',
        body: JSON.stringify({
          contact_id: customerId,
          title: taskTitle.trim(),
          activity_type: taskType,
          priority: taskPriority,
          due_date: taskDueDate ? new Date(taskDueDate).toISOString() : undefined,
          notes: taskNotes.trim(),
        }),
      });
      setShowTaskModal(false);
      setTaskTitle('');
      setTaskNotes('');
      setTaskDueDate('');
      await loadCustomerDetail(customerId, true);
    } catch (err: any) {
      setTaskError(err?.error || 'Failed to create follow-up task.');
    } finally {
      setIsSubmittingTask(false);
    }
  };

  // Helper for lifecycle badge color
  const getLifecycleColor = (stage: string) => {
    switch (stage?.toUpperCase()) {
      case 'LEAD':
        return 'bg-blue-500/10 text-emerald-700 border-blue-500/20';
      case 'PROSPECT':
      case 'QUALIFIED':
        return 'bg-amber-500/10 text-amber-800 border-amber-500/20';
      case 'CUSTOMER':
        return 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20';
      case 'CHURNED':
        return 'bg-rose-500/10 text-rose-700 border-rose-500/20';
      default:
        return "bg-slate-500/10 text-slate-600 border-slate-500/20";
    }
  };

  // Helper for lead score badge color
  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-emerald-700 border-emerald-500/30 bg-emerald-500/10';
    if (score >= 40) return 'text-amber-800 border-amber-500/30 bg-amber-500/10';
    return "text-slate-600 border-slate-500/30 bg-slate-500/10";
  };

  const contact = data?.contact;
  const notes = data?.notes || [];
  const deals = data?.deals || [];
  const activities = data?.activities || [];

  const openTasks = activities.filter((a) => a.status !== 'COMPLETED');
  const completedTasks = activities.filter((a) => a.status === 'COMPLETED');

  // Render content
  return (
    <div
      className={`customer-context-panel flex flex-col h-full bg-white border-l border-emerald-100 text-emerald-950 select-text ${
        isMobile ? 'fixed inset-0 z-50 overflow-y-auto' : 'w-80 xl:w-96 flex-shrink-0'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-emerald-100 bg-white">
        <div className="flex items-center gap-2">
          <UserCheck size={18} className="text-emerald-700" />
          <h3 className="font-semibold text-sm text-emerald-950">Customer Context</h3>
        </div>
        <div className="flex items-center gap-1">
          {customerId && (
            <button
              onClick={() => loadCustomerDetail(customerId)}
              disabled={loading}
              className="p-1.5 text-slate-600 hover:text-emerald-950 rounded hover:bg-white transition"
              title="Refresh Context"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 text-slate-600 hover:text-emerald-950 rounded hover:bg-white transition"
              title="Close Panel"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Main Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Loading state */}
        {loading && !data && (
          <div className="flex flex-col items-center justify-center py-12 text-slate-600 space-y-2">
            <RefreshCw size={24} className="animate-spin text-emerald-700" />
            <span className="text-xs">Loading customer context...</span>
          </div>
        )}

        {/* Empty state: No customer linked */}
        {!customerId && !loading && (
          <div className="text-center py-12 px-4 text-slate-600">
            <User size={32} className="mx-auto text-slate-600 mb-2" />
            <p className="text-sm font-medium text-emerald-950">No Contact Linked</p>
            <p className="text-xs text-slate-600 mt-1">
              This conversation does not have a linked CRM contact record.
            </p>
          </div>
        )}

        {/* Permission Denied (403) state */}
        {isForbidden && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-800 text-xs">
            <div className="flex items-center gap-1.5 font-semibold mb-1">
              <AlertCircle size={14} className="text-amber-800" />
              <span>Permission Denied</span>
            </div>
            <p className="text-amber-800">
              Your staff role does not have permission to view contact details for this customer.
            </p>
          </div>
        )}

        {/* Generic Error state */}
        {error && !isForbidden && (
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-rose-700 text-xs">
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-rose-700">Error loading customer</span>
              {customerId && (
                <button
                  onClick={() => loadCustomerDetail(customerId)}
                  className="text-xs underline hover:text-rose-700"
                >
                  Retry
                </button>
              )}
            </div>
            <p className="text-rose-700">{error}</p>
          </div>
        )}

        {/* Content loaded successfully */}
        {contact && (
          <>
            {/* Handoff Summary Card (Prominent Callout) */}
            {handoffSummary && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-amber-800 shadow-sm">
                <div className="flex items-center gap-1.5 font-semibold text-xs text-amber-800 mb-1">
                  <Sparkles size={14} className="text-amber-800" />
                  <span>Handoff Summary</span>
                </div>
                <p className="text-xs text-amber-800 leading-relaxed whitespace-pre-wrap">
                  {handoffSummary}
                </p>
              </div>
            )}

            {/* Profile Summary Card */}
            <div className="rounded-lg border border-emerald-100 bg-white p-3.5 space-y-2.5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h4 className="font-bold text-emerald-950 text-sm leading-tight">
                    {contact.name || 'Unnamed Contact'}
                  </h4>
                  {contact.company && (
                    <div className="flex items-center gap-1 text-xs text-slate-600 mt-0.5">
                      <Building size={12} className="text-slate-600" />
                      <span>{contact.company.name}</span>
                    </div>
                  )}
                </div>

                {/* Lead Score & Lifecycle Badges */}
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded border ${getLifecycleColor(
                      contact.lifecycle_stage
                    )}`}
                  >
                    {contact.lifecycle_stage || 'LEAD'}
                  </span>
                  {typeof contact.lead_score === 'number' && (
                    <span
                      className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${getScoreColor(
                        contact.lead_score
                      )}`}
                    >
                      {`Score: ${contact.lead_score}`}
                    </span>
                  )}
                </div>
              </div>

              {/* Contact Information */}
              <div className="space-y-1 text-xs text-emerald-950 pt-1 border-t border-emerald-100/80">
                <div className="flex items-center gap-2">
                  <Phone size={12} className="text-slate-600" />
                  <span className="font-mono">{contact.phone_number}</span>
                </div>
                {contact.email && (
                  <div className="flex items-center gap-2">
                    <Mail size={12} className="text-slate-600" />
                    <span className="truncate">{contact.email}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <User size={12} className="text-slate-600" />
                  <span className="text-slate-600">
                    Owner:{' '}
                    <strong className="text-emerald-950">
                      {contact.owner?.name || contact.owner?.username || 'Unassigned'}
                    </strong>
                  </span>
                </div>
              </div>

              {/* View in Contacts deep link button */}
              {onNavigate && (
                <button
                  onClick={() => onNavigate(`/app/contacts?id=${contact.id}`)}
                  className="w-full mt-2 flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-emerald-950 bg-white hover:bg-emerald-50 rounded transition border border-emerald-100"
                >
                  <ExternalLink size={12} />
                  <span>View in Contacts</span>
                </button>
              )}
            </div>

            {/* Navigation Tabs */}
            <div className="flex border-b border-emerald-100 text-xs font-medium">
              <button
                onClick={() => setActiveTab('overview')}
                className={`flex-1 py-1.5 text-center border-b-2 transition ${
                  activeTab === 'overview'
                    ? 'border-emerald-500 text-emerald-700 font-semibold'
                    : "border-transparent text-slate-600 hover:text-emerald-950"
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('notes')}
                className={`flex-1 py-1.5 text-center border-b-2 transition ${
                  activeTab === 'notes'
                    ? 'border-emerald-500 text-emerald-700 font-semibold'
                    : "border-transparent text-slate-600 hover:text-emerald-950"
                }`}
              >
                Notes ({notes.length})
              </button>
              <button
                onClick={() => setActiveTab('tasks')}
                className={`flex-1 py-1.5 text-center border-b-2 transition ${
                  activeTab === 'tasks'
                    ? 'border-emerald-500 text-emerald-700 font-semibold'
                    : "border-transparent text-slate-600 hover:text-emerald-950"
                }`}
              >
                Tasks ({openTasks.length})
              </button>
              <button
                onClick={() => setActiveTab('deals')}
                className={`flex-1 py-1.5 text-center border-b-2 transition ${
                  activeTab === 'deals'
                    ? 'border-emerald-500 text-emerald-700 font-semibold'
                    : "border-transparent text-slate-600 hover:text-emerald-950"
                }`}
              >
                Deals ({deals.length})
              </button>
            </div>

            {/* TAB: OVERVIEW */}
            {activeTab === 'overview' && (
              <div className="space-y-3">
                {/* Next pending task */}
                <div className="rounded-lg border border-emerald-100 bg-white p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-emerald-950">Next Action</span>
                    <button
                      onClick={() => setShowTaskModal(true)}
                      className="text-[11px] text-emerald-700 hover:text-emerald-700 flex items-center gap-1"
                    >
                      <Plus size={12} /> Add
                    </button>
                  </div>
                  {openTasks.length > 0 ? (
                    <div className="flex items-start justify-between gap-2 p-2 rounded bg-white border border-emerald-100">
                      <div className="text-xs">
                        <p className="font-medium text-emerald-950">{openTasks[0].title}</p>
                        <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-600">
                          {openTasks[0].due_date && (
                            <span className={openTasks[0].is_overdue ? 'text-rose-700 font-semibold' : ''}>
                              Due: {new Date(openTasks[0].due_date).toLocaleDateString()}
                            </span>
                          )}
                          <span className="px-1.5 py-0.2 rounded bg-white text-[10px]">
                            {openTasks[0].priority}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleCompleteTask(openTasks[0].id)}
                        disabled={completingTaskId === openTasks[0].id}
                        className="p-1 text-slate-600 hover:text-emerald-700 rounded hover:bg-white transition"
                        title="Mark Complete"
                      >
                        <Check size={14} />
                      </button>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-600 italic">No pending follow-up tasks scheduled.</p>
                  )}
                </div>

                {/* Quick Add Internal Note Form */}
                <form onSubmit={handleAddNote} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-emerald-950">Add Internal Note</label>
                    <span className="text-[10px] text-slate-600">Internal staff only</span>
                  </div>
                  <textarea
                    value={noteContent}
                    onChange={(e) => setNoteContent(e.target.value)}
                    placeholder="Add internal note (visible only to your team)..."
                    rows={2}
                    className="w-full text-xs rounded border border-emerald-100 bg-white px-2.5 py-1.5 text-emerald-950 placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
                    disabled={isSubmittingNote}
                  />
                  {noteError && <p className="text-[11px] text-rose-700">{noteError}</p>}
                  <button
                    type="submit"
                    disabled={!noteContent.trim() || isSubmittingNote}
                    className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white rounded text-xs font-semibold transition"
                  >
                    {isSubmittingNote ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
                    <span>Save Note</span>
                  </button>
                </form>

                {/* Recent notes preview */}
                {notes.length > 0 && (
                  <div className="space-y-1.5 pt-2">
                    <span className="text-xs font-semibold text-slate-600">Recent Notes</span>
                    <div className="space-y-1.5">
                      {notes.slice(0, 2).map((n) => (
                        <div key={n.id} className="p-2 rounded bg-white border border-emerald-100 text-xs">
                          <p className="text-emerald-950">{n.content}</p>
                          <div className="flex items-center justify-between text-[10px] text-slate-600 mt-1">
                            <span>@{n.author__username || 'staff'}</span>
                            <span>{new Date(n.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB: NOTES */}
            {activeTab === 'notes' && (
              <div className="space-y-3">
                {/* Add Note Form */}
                <form onSubmit={handleAddNote} className="space-y-1.5">
                  <textarea
                    value={noteContent}
                    onChange={(e) => setNoteContent(e.target.value)}
                    placeholder="Write a note about this customer..."
                    rows={3}
                    className="w-full text-xs rounded border border-emerald-100 bg-white px-2.5 py-1.5 text-emerald-950 placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
                    disabled={isSubmittingNote}
                  />
                  {noteError && <p className="text-[11px] text-rose-700">{noteError}</p>}
                  <button
                    type="submit"
                    disabled={!noteContent.trim() || isSubmittingNote}
                    className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white rounded text-xs font-semibold transition"
                  >
                    {isSubmittingNote ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
                    <span>Save Internal Note</span>
                  </button>
                </form>

                {/* Notes List */}
                <div className="space-y-2">
                  {notes.length === 0 ? (
                    <p className="text-xs text-slate-600 text-center py-4">No internal notes recorded yet.</p>
                  ) : (
                    notes.map((n) => (
                      <div key={n.id} className="p-2.5 rounded-lg bg-white border border-emerald-100 text-xs space-y-1">
                        <p className="text-emerald-950 whitespace-pre-wrap">{n.content}</p>
                        <div className="flex items-center justify-between text-[10px] text-slate-600 pt-1 border-t border-emerald-100/60">
                          <span className="font-semibold text-slate-600">@{n.author__username || 'staff'}</span>
                          <span>{new Date(n.created_at).toLocaleString()}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* TAB: TASKS */}
            {activeTab === 'tasks' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-emerald-950">Actionable Tasks</span>
                  <button
                    onClick={() => setShowTaskModal(true)}
                    className="flex items-center gap-1 text-xs text-emerald-700 hover:text-emerald-700 font-medium"
                  >
                    <Plus size={12} /> Schedule Task
                  </button>
                </div>

                {/* Open Tasks List */}
                <div className="space-y-2">
                  {openTasks.length === 0 ? (
                    <p className="text-xs text-slate-600 text-center py-4">No open tasks for this customer.</p>
                  ) : (
                    openTasks.map((act) => (
                      <div
                        key={act.id}
                        className="flex items-start justify-between gap-2 p-2.5 rounded-lg bg-white border border-emerald-100"
                      >
                        <div className="text-xs space-y-1 flex-1">
                          <p className="font-medium text-emerald-950">{act.title}</p>
                          <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                            <span className="px-1.5 py-0.2 rounded bg-white text-slate-600">
                              {act.activity_type_display || act.activity_type}
                            </span>
                            <span
                              className={`px-1.5 py-0.2 rounded ${
                                act.priority === 'HIGH'
                                  ? 'bg-rose-500/10 text-rose-700'
                                  : "bg-white text-slate-600"
                              }`}
                            >
                              {act.priority}
                            </span>
                            {act.due_date && (
                              <span
                                className={
                                  act.is_overdue
                                    ? 'text-rose-700 font-semibold'
                                    : "text-slate-600"
                                }
                              >
                                {new Date(act.due_date).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>

                        <button
                          onClick={() => handleCompleteTask(act.id)}
                          disabled={completingTaskId === act.id}
                          className="flex items-center gap-1 px-2 py-1 text-[11px] rounded bg-emerald-600/20 text-emerald-700 hover:bg-emerald-600/30 transition border border-emerald-500/30"
                          title="Mark Complete"
                        >
                          {completingTaskId === act.id ? (
                            <RefreshCw size={12} className="animate-spin" />
                          ) : (
                            <Check size={12} />
                          )}
                          <span>Done</span>
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Completed Tasks section */}
                {completedTasks.length > 0 && (
                  <div className="pt-2 border-t border-emerald-100">
                    <span className="text-[11px] text-slate-600 font-semibold uppercase tracking-wider">
                      Completed ({completedTasks.length})
                    </span>
                    <div className="space-y-1.5 mt-1.5">
                      {completedTasks.map((act) => (
                        <div
                          key={act.id}
                          className="p-2 rounded bg-white border border-emerald-100/60 text-xs text-slate-600 flex items-center justify-between"
                        >
                          <span className="line-through">{act.title}</span>
                          <CheckCircle2 size={12} className="text-emerald-500/60" />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB: DEALS */}
            {activeTab === 'deals' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-emerald-950">Linked Deals</span>
                  {onNavigate && (
                    <button
                      onClick={() => onNavigate('/app/deals')}
                      className="text-xs text-emerald-700 hover:text-emerald-700 flex items-center gap-1"
                    >
                      <ExternalLink size={12} /> Pipeline
                    </button>
                  )}
                </div>

                {deals.length === 0 ? (
                  <p className="text-xs text-slate-600 text-center py-4">No active deals found for this customer.</p>
                ) : (
                  deals.map((d) => (
                    <div
                      key={d.id}
                      onClick={() => onNavigate?.(`/app/deals?id=${d.id}`)}
                      className="p-2.5 rounded-lg bg-white border border-emerald-100 hover:border-emerald-100 cursor-pointer transition space-y-1.5"
                    >
                      <div className="flex items-start justify-between gap-1">
                        <p className="font-semibold text-xs text-emerald-950">{d.title}</p>
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                            d.status === 'WON'
                              ? 'bg-emerald-500/20 text-emerald-700'
                              : d.status === 'LOST'
                              ? 'bg-rose-500/20 text-rose-700'
                              : 'bg-blue-500/20 text-emerald-700'
                          }`}
                        >
                          {d.status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-xs text-slate-600">
                        <span className="font-mono text-emerald-700 font-medium">
                          {d.currency || 'INR'} {d.amount?.toLocaleString() || d.value?.toLocaleString() || '0'}
                        </span>
                        <span>{d.stage_name}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* SCHEDULE TASK MODAL */}
      {showTaskModal && (
        <Modal title="Schedule Follow-up Task" onClose={() => setShowTaskModal(false)} maxWidth="24rem" zIndex={50} className="w-full max-w-sm rounded-xl border border-emerald-100 bg-white p-5 shadow-2xl text-emerald-950 space-y-4">

            <form onSubmit={handleCreateTask} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-emerald-950 mb-1">Title *</label>
                <input
                  type="text"
                  required
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="e.g. Call customer with revised quotation"
                  className="w-full text-xs rounded border border-emerald-100 bg-white px-3 py-2 text-emerald-950 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-medium text-emerald-950 mb-1">Type</label>
                  <select
                    value={taskType}
                    onChange={(e) => setTaskType(e.target.value)}
                    className="w-full text-xs rounded border border-emerald-100 bg-white px-2 py-1.5 text-emerald-950 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="FOLLOW_UP">Follow Up</option>
                    <option value="CALL">Phone Call</option>
                    <option value="MEETING">Meeting</option>
                    <option value="DEMO">Demo</option>
                    <option value="TASK">General Task</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-emerald-950 mb-1">Priority</label>
                  <select
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    className="w-full text-xs rounded border border-emerald-100 bg-white px-2 py-1.5 text-emerald-950 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-emerald-950 mb-1">Due Date</label>
                <input
                  type="date"
                  value={taskDueDate}
                  onChange={(e) => setTaskDueDate(e.target.value)}
                  className="w-full text-xs rounded border border-emerald-100 bg-white px-3 py-1.5 text-emerald-950 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-emerald-950 mb-1">Notes (Optional)</label>
                <textarea
                  value={taskNotes}
                  onChange={(e) => setTaskNotes(e.target.value)}
                  rows={2}
                  placeholder="Notes or agenda..."
                  className="w-full text-xs rounded border border-emerald-100 bg-white px-3 py-1.5 text-emerald-950 focus:outline-none focus:border-emerald-500 resize-none"
                />
              </div>

              {taskError && <p className="text-xs text-rose-700">{taskError}</p>}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-emerald-100">
                <button
                  type="button"
                  onClick={() => setShowTaskModal(false)}
                  className="px-3 py-1.5 rounded text-xs text-slate-600 hover:text-emerald-950"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!taskTitle.trim() || isSubmittingTask}
                  className="px-4 py-1.5 rounded bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5"
                >
                  {isSubmittingTask && <RefreshCw size={12} className="animate-spin" />}
                  <span>Schedule Task</span>
                </button>
              </div>
            </form>

        </Modal>
      )}
    </div>
  );
};
