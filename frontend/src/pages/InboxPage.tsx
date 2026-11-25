import React, { useEffect, useState, useRef } from 'react';
import { useVisibleAutoSync } from '../hooks/useVisibleAutoSync';
import { Conversation, MessageItem } from '../types';
import { fetchApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { CustomerContextPanel } from '../components/inbox/CustomerContextPanel';
import { NewChatModal } from '../components/inbox/NewChatModal';
import {
  Search,
  UserCheck,
  PlayCircle,
  Send,
  Sparkles,
  Bot,
  User,
  ArrowLeft,
  X,
  Plus,
  Check,
  CheckCheck,
  Clock,
  AlertCircle,
} from 'lucide-react';

interface InboxPageProps {
  onNavigate?: (path: string) => void;
}

export const InboxPage: React.FC<InboxPageProps> = ({ onNavigate }) => {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'mine' | 'unassigned' | 'bot' | 'human'>('all');
  const [replyText, setReplyText] = useState('');
  const [savedReplies,setSavedReplies]=useState<{id:number;title:string;body:string}[]>([]);
  const [teamMembers, setTeamMembers] = useState<{ user_id: number; username: string; full_name: string }[]>([]);
  const [transferTarget, setTransferTarget] = useState('');
  const [uploadingMedia, setUploadingMedia] = useState(false);
  useEffect(()=>{
    fetchApi<{results:{id:number;title:string;body:string}[]}>('/api/workspace/tools/replies/').then(r=>setSavedReplies(Array.isArray(r.results)?r.results:[])).catch(()=>setSavedReplies([]));
    fetchApi<{members:{user_id:number;username:string;full_name:string}[]}>('/api/team/').then(r=>setTeamMembers(Array.isArray(r.members)?r.members:[])).catch(()=>setTeamMembers([]));
  },[]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [isSending, setIsSending] = useState(false);
  const [simText, setSimText] = useState('');
  const [simLoading, setSimLoading] = useState(false);
  const [showSimulator, setShowSimulator] = useState(false);
  const [showNewChatModal, setShowNewChatModal] = useState(false);
  const [showContext, setShowContext] = useState(window.innerWidth >= 1440);
  const [contextAsDrawer, setContextAsDrawer] = useState(window.innerWidth < 1440);
  const [mobileView, setMobileView] = useState<'list' | 'chat'>('list');
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(0);
  const selectedIdRef = useRef<number | null>(null);
  selectedIdRef.current = selectedConv?.id ?? null;
  const draftsRef = useRef<Record<number, string>>({});
  draftsRef.current = drafts;
  const messagesRequestRef = useRef(0);
  const listRequestRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      messagesRequestRef.current++;
      listRequestRef.current++;
    };
  }, []);

  // Monitor screen resize for responsive controls
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      setContextAsDrawer(window.innerWidth < 1440);
      if (!mobile && mobileView === 'list' && selectedConv) {
        setMobileView('chat');
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [mobileView, selectedConv]);

  // Load conversations
  const loadConversations = async (quiet = false, preferredId?: number) => {
    const requestId = ++listRequestRef.current;
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('q', searchQuery);
      if (activeTab !== 'all') params.append('tab', activeTab);
      const data = await fetchApi<{ conversations: Conversation[] }>(`/api/inbox/conversations/?${params.toString()}`);
      if (!mountedRef.current || requestId !== listRequestRef.current) return;
      const list = data.conversations || [];
      setConversations(list);

      // Check query param or preferredId for initial conversation selection
      const urlParams = new URLSearchParams(window.location.search);
      const targetId = preferredId || (urlParams.get('conversation_id') ? parseInt(urlParams.get('conversation_id')!) : null);

      if (!quiet) {
        if (targetId) {
          const match = list.find((c) => c.id === targetId);
          if (match) {
            handleSelectConversation(match);
            if (isMobile) setMobileView('chat');
            return;
          }
        }
        if (!selectedConv && list.length > 0) {
          handleSelectConversation(list[0]);
        }
      } else if (selectedConv) {
        // Sync selected conversation state quietly from list
        const latest = list.find((c) => c.id === selectedConv.id);
        if (latest) {
          setSelectedConv((prev) => (prev?.id === latest.id ? { ...prev, ...latest } : prev));
        }
      }
    } catch (err) {
      if (!quiet) console.error(err);
    }
  };

  // Safe switching of conversation preserving per-chat drafts
  const handleSelectConversation = (conv: Conversation) => {
    if (selectedConv) {
      // Save draft for previous conversation
      setDrafts((prev) => ({
        ...prev,
        [selectedConv.id]: replyText,
      }));
    }
    setSelectedConv(conv);
    // Restore draft for new conversation
    setReplyText(draftsRef.current[conv.id] || '');
    if (isMobile) setMobileView('chat');
    if (conv.unread_count && conv.unread_count > 0) {
      setConversations((prev) => prev.map((c) => (c.id === conv.id ? { ...c, unread_count: 0 } : c)));
      fetchApi(`/api/inbox/conversations/${conv.id}/mark-read/`, { method: 'POST' }).catch(() => {});
    }
  };

  const handleTransferChat = async (targetUserId: string) => {
    if (!selectedConv || !targetUserId) return;
    try {
      const res = await fetchApi<any>(`/api/inbox/conversations/${selectedConv.id}/transfer/`, {
        method: 'POST',
        body: JSON.stringify({ target_user_id: Number(targetUserId) }),
      });
      setSelectedConv((prev) => prev ? { ...prev, ...res, status: res.status || 'HUMAN_HANDOVER' } : prev);
      setTransferTarget('');
      await loadConversations(true);
    } catch (err: any) {
      alert(err?.error || 'Could not transfer conversation.');
    }
  };

  const handleUploadMedia = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !selectedConv) return;
    try {
      setUploadingMedia(true);
      const fd = new FormData();
      fd.append('file', file);
      if (replyText.trim()) fd.append('caption', replyText.trim());
      await fetchApi(`/api/inbox/conversations/${selectedConv.id}/media/`, { method: 'POST', body: fd });
      setReplyText('');
      await loadMessages(selectedConv.id);
      await loadConversations(true);
    } catch (err: any) {
      alert(err?.error || 'Failed to upload media attachment.');
    } finally {
      setUploadingMedia(false);
    }
  };

  // Load messages for a conversation
  const loadMessages = async (convId: number, quiet = false) => {
    if (selectedIdRef.current !== convId) return;
    const requestId = ++messagesRequestRef.current;
    try {
      const data = await fetchApi<{ messages: MessageItem[]; status?: string; conversation_status?: string }>(
        `/conversations/${convId}/messages/`
      );
      if (!mountedRef.current || selectedIdRef.current !== convId || requestId !== messagesRequestRef.current) return;
      const newMessages = data.messages || [];
      setMessages(newMessages);

      if (data.conversation_status && selectedConv && selectedConv.status !== data.conversation_status) {
        setSelectedConv((prev) => (prev ? { ...prev, status: data.conversation_status!, handover_required: data.conversation_status === 'HUMAN_HANDOVER' } : prev));
      }

      // Scroll to bottom if new messages arrived
      if (!quiet || newMessages.length > prevMessageCountRef.current) {
        setTimeout(() => {
          if (mountedRef.current && selectedIdRef.current === convId) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          }
        }, 80);
      }
      prevMessageCountRef.current = newMessages.length;
    } catch (err) {
      if (!quiet) console.error(err);
    }
  };

  // Initial load on tab / query changes
  useEffect(() => {
    loadConversations();
  }, [searchQuery, activeTab]);

  // Load messages whenever selected conversation changes
  useEffect(() => {
    if (selectedConv) {
      prevMessageCountRef.current = 0;
      setMessages([]);
      loadMessages(selectedConv.id);
    }
  }, [selectedConv?.id]);

  // Single-flight reads on a fixed cadence, with immediate focus/visibility wakeup.
  useVisibleAutoSync(async () => {
    const reads = await Promise.allSettled([
      selectedIdRef.current ? loadMessages(selectedIdRef.current, true) : Promise.resolve(),
      loadConversations(true),
    ]);
    if (reads.some(result => result.status === 'rejected')) throw new Error('Sync interrupted');
  });

  // Claim, Release, Switch to Human, Resume Bot action handler
  const handleAction = async (action: 'claim' | 'release' | 'pause' | 'resume' | 'switch_to_human') => {
    if (!selectedConv) return;
    try {
      const formData = new FormData();
      formData.append('action', action);
      const res = await fetchApi<any>(`/conversations/${selectedConv.id}/action/`, {
        method: 'POST',
        body: formData,
      });

      // Update ownership and status immediately in local state
      setSelectedConv((prev) => {
        if (!prev || prev.id !== selectedConv.id) return prev;
        if (action === 'claim' || action === 'switch_to_human') {
          return {
            ...prev,
            assigned_staff: res.assigned_staff || user?.username || 'You',
            status: res.status || 'HUMAN_HANDOVER',
            status_display: res.status_display || 'Human Handover',
            handover_required: true,
          };
        } else if (action === 'release') {
          return {
            ...prev,
            assigned_staff: null,
            status: res.status || prev.status,
            status_display: res.status_display || prev.status_display,
          };
        } else if (action === 'pause') {
          return {
            ...prev,
            status: 'HUMAN_HANDOVER',
            status_display: 'Human Handover',
            handover_required: true,
            assigned_staff: res.assigned_staff === undefined ? prev.assigned_staff : res.assigned_staff,
          };
        } else if (action === 'resume') {
          return {
            ...prev,
            status: 'BOT_ACTIVE',
            status_display: 'Bot Active',
            handover_required: false,
            assigned_staff: null,
          };
        }
        return prev;
      });

      await loadConversations(true);
      await loadMessages(selectedConv.id, true);
    } catch (err: any) {
      alert(err?.error || `Failed to perform action '${action}'`);
    }
  };

  // Outbound message sending
  const handleSendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConv || !replyText.trim() || isSending) return;
    const submittedId = selectedConv.id;
    const submittedText = replyText;
    try {
      setIsSending(true);
      const formData = new FormData();
      formData.append('action', 'reply');
      formData.append('text', replyText.trim());
      await fetchApi(`/conversations/${selectedConv.id}/action/`, {
        method: 'POST',
        body: formData,
      });
      if (selectedIdRef.current === submittedId) {
        setReplyText(current => current === submittedText ? '' : current);
      }
      setDrafts(prev => prev[submittedId] === submittedText ? { ...prev, [submittedId]: '' } : prev);
      await loadMessages(submittedId);
      await loadConversations(true);
    } catch (err: any) {
      alert(err?.error || 'Could not deliver outbound message');
    } finally {
      setIsSending(false);
    }
  };

  // Retry delivery handler
  const handleRetryDelivery = async (deliveryId: number) => {
    try {
      await fetchApi(`/api/inbox/delivery/${deliveryId}/retry/`, {
        method: 'POST',
      });
      if (selectedConv) {
        await loadMessages(selectedConv.id);
      }
    } catch (err: any) {
      alert(err?.error || 'Failed to retry delivery');
    }
  };

  // AI chat simulator
  const handleSendSimulated = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simText.trim() || simLoading) return;
    const submittedId = selectedConv?.id ?? null;
    const submittedText = simText;
    try {
      setSimLoading(true);
      await fetchApi('/chat/send/', {
        method: 'POST',
        body: JSON.stringify({
          message_text: simText.trim(),
          conversation_id: selectedConv?.id,
          phone_number: selectedConv?.customer_phone || '+919999900001',
        }),
      });
      if (selectedIdRef.current === submittedId) {
        setSimText((current) => (current === submittedText ? '' : current));
      }
      await loadConversations(true);
      if (selectedConv) {
        await loadMessages(selectedConv.id);
      }
    } catch (err: any) {
      alert(err?.error || 'Error processing simulated message');
    } finally {
      setSimLoading(false);
    }
  };

  // Check composer lock state
  const isBotMode = selectedConv?.status === 'BOT_ACTIVE';
  const isClaimedByOther = Boolean(
    selectedConv?.assigned_staff &&
    selectedConv.assigned_staff !== user?.username &&
    !user?.is_superuser
  );

  return (
    <div
      style={{
        display: 'flex',
        height: 'calc(100vh - 6.75rem)',
        gap: '0.75rem',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* 1. Conversations List Panel */}
      <div
        style={{
          width: isMobile ? '100%' : '22rem',
          minWidth: isMobile ? '100%' : '19rem',
          maxWidth: isMobile ? '100%' : '24rem',
          display: isMobile && mobileView === 'chat' ? 'none' : 'flex',
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: '0.75rem',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '0.85rem 1rem', borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
            <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: "var(--text-main)", margin: 0 }}>
              WhatsApp Workspace
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <button
                onClick={() => setShowNewChatModal(true)}
                className="btn btn-primary btn-sm"
                style={{ padding: '0.25rem 0.55rem', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                title="Start a new WhatsApp conversation"
              >
                <Plus size={13} /> New Chat
              </button>
              <button
                onClick={() => setShowSimulator(!showSimulator)}
                className={`btn btn-sm ${showSimulator ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                title="Toggle AI Chat Simulator"
              >
                <Sparkles size={12} /> Sim
              </button>
            </div>
          </div>

          {/* Search Field */}
          <div style={{ position: 'relative', marginBottom: '0.5rem' }}>
            <Search size={13} style={{ position: 'absolute', left: '0.75rem', top: '0.65rem', color: "var(--text-muted)" }} />
            <input
              type="text"
              placeholder="Search phone, name, or message..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input-field"
              style={{ paddingLeft: '2.1rem', fontSize: '0.78rem', padding: '0.45rem 0.65rem 0.45rem 2.1rem' }}
            />
          </div>

          {/* Filter Tabs: All, Mine, Unassigned, Bot Active, Human Support */}
          <div style={{ display: 'flex', gap: '0.2rem', overflowX: 'auto', paddingBottom: '2px' }}>
            {[
              { id: 'all', label: 'All' },
              { id: 'mine', label: 'Mine' },
              { id: 'unassigned', label: 'Unassigned' },
              { id: 'bot', label: 'Bot Active' },
              { id: 'human', label: 'Human' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`btn btn-sm ${activeTab === tab.id ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: '0.66rem', padding: '0.2rem 0.45rem', whiteSpace: 'nowrap' }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Conversation List */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: '2rem 1rem', textAlign: 'center', color: "var(--text-muted)", fontSize: '0.82rem' }}>
              No conversations found.
            </div>
          ) : (
            conversations.map((c) => {
              const isSelected = selectedConv?.id === c.id;
              const isBot = c.status === 'BOT_ACTIVE';
              return (
                <div
                  key={c.id}
                  onClick={() => handleSelectConversation(c)}
                  style={{
                    padding: '0.75rem 1rem',
                    borderBottom: "1px solid var(--border)",
                    backgroundColor: isSelected ? 'rgba(17, 183, 109, 0.12)' : 'transparent',
                    borderLeft: isSelected ? '3px solid #11B76D' : '3px solid transparent',
                    cursor: 'pointer',
                    transition: 'background 0.1s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem', color: isSelected ? "var(--primary)" : "var(--text-main)" }}>
                      {c.customer_name || 'Customer'}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.68rem', color: "var(--text-muted)" }}>
                      {(c.unread_count || 0) > 0 && (
                        <span aria-label={`${c.unread_count} unread`} style={{ background: 'var(--primary)', color: '#fff', borderRadius: '999px', padding: '1px 6px', fontSize: '0.65rem', fontWeight: 700 }}>
                          {c.unread_count}
                        </span>
                      )}
                      {c.last_message_at
                        ? new Date(c.last_message_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : ''}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.25rem' }}>
                    {c.customer_phone}
                    {c.assigned_staff ? ` • @${c.assigned_staff}` : ' • Unassigned'}
                  </div>

                  <div
                    style={{
                      fontSize: '0.78rem',
                      color: "var(--text-main)",
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {c.last_message_text || 'No messages yet'}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '0.35rem' }}>
                    <span
                      className={`badge ${isBot ? 'badge-blue' : 'badge-amber'}`}
                      style={{ fontSize: '0.62rem', padding: '1px 6px' }}
                    >
                      {isBot ? '🤖 Bot Active' : '👤 Human Support'}
                    </span>
                    {c.channel && (
                      <span className="badge badge-gray" style={{ fontSize: '0.6rem', padding: '1px 5px' }}>
                        {c.channel_display || c.channel}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 2. Main Conversation Thread */}
      {selectedConv ? (
        <div
          style={{
            flex: 1,
            display: isMobile && mobileView === 'list' ? 'none' : 'flex',
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: '0.75rem',
            flexDirection: 'column',
            overflow: 'hidden',
            minWidth: 0,
          }}
        >
          {/* Conversation Header */}
          <div
            style={{
              padding: '0.75rem 1rem',
              borderBottom: "1px solid var(--border)",
              backgroundColor: "var(--bg-card)",
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
              {isMobile && (
                <button
                  onClick={() => setMobileView('list')}
                  className="btn btn-secondary btn-sm"
                  style={{ padding: '0.35rem 0.5rem', marginRight: '0.25rem' }}
                  title="Back to inbox list"
                >
                  <ArrowLeft size={14} /> Back
                </button>
              )}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
                  <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: "var(--text-main)", margin: 0 }}>
                    {selectedConv.customer_name || 'Customer'}
                  </h3>
                  <span className="badge badge-gray" style={{ fontSize: '0.7rem' }}>
                    {selectedConv.customer_phone}
                  </span>
                  <span
                    className={`badge ${selectedConv.status === 'HUMAN_HANDOVER' ? 'badge-amber' : 'badge-green'}`}
                    style={{ fontSize: '0.7rem' }}
                  >
                    {selectedConv.status === 'HUMAN_HANDOVER' ? 'Human Mode' : 'Bot Active'}
                  </span>
                </div>
                <div style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginTop: '0.15rem' }}>
                  {selectedConv.assigned_staff ? (
                    <span style={{ color: "var(--primary)", fontWeight: 600 }}>
                      Assigned to: @{selectedConv.assigned_staff}
                    </span>
                  ) : (
                    <span style={{ color: "var(--warning)" }}>Unassigned (Queue)</span>
                  )}
                  {selectedConv.service_name && ` • ${selectedConv.service_name}`}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
              {isBotMode ? (
                <button
                  onClick={() => handleAction('switch_to_human')}
                  className="btn btn-primary btn-sm"
                  style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                  title="Switch conversation to Human Mode to pause bot and take over"
                >
                  <UserCheck size={13} /> Switch to Human
                </button>
              ) : (
                <>
                  {!selectedConv.assigned_staff ? (
                    <button
                      onClick={() => handleAction('claim')}
                      className="btn btn-primary btn-sm"
                      style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                      title="Claim this conversation and assign to yourself"
                    >
                      <UserCheck size={13} /> Claim Chat
                    </button>
                  ) : selectedConv.assigned_staff === user?.username ? (
                    <button
                      onClick={() => handleAction('release')}
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                      title="Release chat back to unassigned queue"
                    >
                      Release Chat
                    </button>
                  ) : null}

                  <button
                    onClick={() => handleAction('resume')}
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                    title="Resume automated bot replies"
                  >
                    <PlayCircle size={13} style={{ color: "var(--primary)" }} /> Resume Bot
                  </button>
                  {teamMembers.length > 0 && (
                    <select
                      aria-label="Transfer chat"
                      className="input-field"
                      style={{ width: 'auto', fontSize: '0.75rem', padding: '0.3rem 0.5rem' }}
                      value={transferTarget}
                      onChange={(e) => {
                        setTransferTarget(e.target.value);
                        if (e.target.value) handleTransferChat(e.target.value);
                      }}
                    >
                      <option value="">Transfer to…</option>
                      {teamMembers.map((tm) => (
                        <option key={tm.user_id} value={tm.user_id}>
                          {tm.full_name} (@{tm.username})
                        </option>
                      ))}
                    </select>
                  )}
                </>
              )}

              <button
                onClick={() => setShowContext(!showContext)}
                className={`btn btn-sm ${showContext ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                title={showContext ? 'Hide Customer Context Panel' : 'Show Customer Context Panel'}
              >
                <UserCheck size={13} />
                <span>Context</span>
              </button>
            </div>
          </div>

          {/* Mode Banner */}
          <div
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: isBotMode ? 'var(--primary-light)' : 'rgba(245, 158, 11, 0.08)',
              borderBottom: `1px solid ${isBotMode ? 'rgba(56, 189, 248, 0.25)' : 'rgba(245, 158, 11, 0.25)'}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.76rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              {isBotMode ? (
                <>
                  <Bot size={15} style={{ color: "var(--primary)" }} />
                  <span style={{ color: "var(--primary)" }}>
                    <strong>Bot Mode Active:</strong> Automated AI assistant handles inbound customer messages. Staff composer is locked.
                  </span>
                </>
              ) : (
                <>
                  <User size={15} style={{ color: "var(--warning)" }} />
                  <span style={{ color: "var(--warning)" }}>
                    <strong>Human Support Mode:</strong> Bot replies paused. Handled by{' '}
                    {selectedConv.assigned_staff ? `@${selectedConv.assigned_staff}` : 'unassigned team queue'}.
                  </span>
                </>
              )}
            </div>

            <div>
              {isBotMode ? (
                <button
                  onClick={() => handleAction('switch_to_human')}
                  className="btn btn-sm btn-primary"
                  style={{ fontSize: '0.68rem', padding: '0.2rem 0.5rem' }}
                >
                  Take Over
                </button>
              ) : (
                <button
                  onClick={() => handleAction('resume')}
                  className="btn btn-sm btn-secondary"
                  style={{ fontSize: '0.68rem', padding: '0.2rem 0.5rem' }}
                >
                  Resume Bot
                </button>
              )}
            </div>
          </div>

          {/* Messages Scroll View */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            {messages.length === 0 ? (
              <div style={{ textAlign: 'center', margin: 'auto', color: "var(--text-muted)", fontSize: '0.82rem' }}>
                No messages recorded in this conversation yet.
              </div>
            ) : (
              messages.map((m) => {
                const isInbound = m.direction === 'INBOUND';
                const isBotMsg = m.sender_type === 'BOT';

                // Delivery Status Icon helper
                const renderDeliveryIcon = () => {
                  if (isInbound) return null;
                  const st = m.delivery_status;
                  if (!st || st === 'PENDING' || st === 'SENDING') {
                    return (
                      <span title="Pending delivery">
                        <Clock size={12} color="var(--text-muted)" />
                      </span>
                    );
                  }
                  if (st === 'SENT') {
                    return (
                      <span title="Sent to Meta WhatsApp">
                        <Check size={13} color="var(--text-muted)" />
                      </span>
                    );
                  }
                  if (st === 'DELIVERED') {
                    return (
                      <span title="Delivered to recipient">
                        <CheckCheck size={14} color="var(--text-muted)" />
                      </span>
                    );
                  }
                  if (st === 'READ') {
                    return (
                      <span title="Read by recipient">
                        <CheckCheck size={14} color="#38bdf8" />
                      </span>
                    );
                  }
                  if (st === 'FAILED' || st === 'BLOCKED') {
                    return (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                        <span title={m.delivery_error || 'Delivery failed'}>
                          <AlertCircle size={13} color="#ef4444" />
                        </span>
                        {m.delivery_id && (
                          <button
                            type="button"
                            onClick={() => handleRetryDelivery(m.delivery_id!)}
                            className="btn btn-sm btn-secondary"
                            style={{ padding: '1px 5px', fontSize: '0.62rem', height: '1.2rem', color: "var(--danger)" }}
                            title="Retry sending message"
                          >
                            Retry
                          </button>
                        )}
                      </span>
                    );
                  }
                  return null;
                };

                const authorDisplay = isInbound
                  ? selectedConv.customer_name || 'Customer'
                  : isBotMsg
                  ? 'AI Assistant'
                  : m.author_name || (selectedConv.assigned_staff ? `@${selectedConv.assigned_staff}` : 'Staff');

                return (
                  <div
                    key={m.id}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: isInbound ? 'flex-start' : 'flex-end',
                    }}
                  >
                    <div
                      style={{
                        maxWidth: isMobile ? '88%' : '72%',
                        padding: '0.65rem 0.85rem',
                        borderRadius: '0.65rem',
                        backgroundColor: isInbound ? "var(--bg-card-hover)" : isBotMsg ? 'var(--primary-light)' : 'rgba(17, 183, 109, 0.18)',
                        border: isInbound
                          ? "1px solid var(--border)"
                          : isBotMsg
                          ? '1px solid rgba(56, 189, 248, 0.35)'
                          : '1px solid rgba(17, 183, 109, 0.4)',
                        color: "var(--text-main)",
                        fontSize: '0.84rem',
                        lineHeight: 1.4,
                      }}
                    >
                      <div
                        style={{
                          fontSize: '0.68rem',
                          color: isInbound ? "var(--text-muted)" : isBotMsg ? "var(--primary)" : "var(--primary)",
                          marginBottom: '0.2rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                        }}
                      >
                        {isInbound ? <User size={11} /> : isBotMsg ? <Bot size={11} /> : <UserCheck size={11} />}
                        <span style={{ fontWeight: 600 }}>{authorDisplay}</span>
                        <span>•</span>
                        <span>{m.timestamp}</span>
                        {!isInbound && renderDeliveryIcon()}
                      </div>
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.text}</div>
                      {m.media_url && (
                        <div style={{ marginTop: '0.45rem' }}>
                          {m.media_type === 'image' ? (
                            <img src={m.media_url} alt={m.media_name || 'Attachment'} style={{ maxWidth: '16rem', borderRadius: '0.45rem', display: 'block' }} />
                          ) : m.media_type === 'audio' ? (
                            <audio controls src={m.media_url} style={{ maxWidth: '100%' }} />
                          ) : m.media_type === 'video' ? (
                            <video controls src={m.media_url} style={{ maxWidth: '16rem', borderRadius: '0.45rem' }} />
                          ) : (
                            <a href={m.media_url} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '0.78rem' }}>
                              Download {m.media_name || 'Attachment'}
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {savedReplies.length>0&&<label style={{padding:'.5rem 1rem'}}>Saved reply<select aria-label="Insert saved reply" value="" disabled={isBotMode||isClaimedByOther} onChange={e=>{const reply=savedReplies.find(r=>String(r.id)===e.target.value);if(reply&&selectedConv){setReplyText(reply.body);setDrafts(prev=>({...prev,[selectedConv.id]:reply.body}));}}}><option value="">Choose a reply to review</option>{savedReplies.map(r=><option key={r.id} value={r.id}>{r.title}</option>)}</select></label>}
          {/* Outbound Reply Composer */}
          <form
            onSubmit={handleSendReply}
            style={{
              padding: '0.75rem 1rem',
              borderTop: "1px solid var(--border)",
              backgroundColor: "var(--bg-card)",
              display: 'flex',
              flexDirection: 'column',
              gap: '0.4rem',
            }}
          >
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                placeholder={
                  isBotMode
                    ? 'Bot Mode active. Switch to Human mode to send staff replies...'
                    : isClaimedByOther
                    ? `Claimed by @${selectedConv.assigned_staff}. Ask them to release chat...`
                    : 'Type WhatsApp reply to customer (Enter to send)...'
                }
                value={replyText}
                onChange={(e) => {
                  const val = e.target.value;
                  setReplyText(val);
                  if (selectedConv) {
                    setDrafts((prev) => ({ ...prev, [selectedConv.id]: val }));
                  }
                }}
                maxLength={2000}
                disabled={isBotMode || isClaimedByOther}
                className="input-field"
                style={{
                  flex: 1,
                  fontSize: '0.84rem',
                  opacity: isBotMode || isClaimedByOther ? 0.6 : 1,
                }}
              />
              <label className="btn btn-secondary" style={{ padding: '0.5rem 0.7rem', fontSize: '0.78rem', cursor: (isBotMode || isClaimedByOther || uploadingMedia) ? 'not-allowed' : 'pointer', opacity: (isBotMode || isClaimedByOther) ? 0.5 : 1 }}>
                {uploadingMedia ? 'Uploading…' : 'Attach'}
                <input
                  type="file"
                  aria-label="Attach media file"
                  accept="image/*,application/pdf,text/plain,audio/*,video/mp4"
                  disabled={isBotMode || isClaimedByOther || uploadingMedia}
                  style={{ display: 'none' }}
                  onChange={handleUploadMedia}
                />
              </label>
              <button
                type="submit"
                disabled={isSending || !replyText.trim() || isBotMode || isClaimedByOther}
                className="btn btn-primary"
                style={{ padding: '0.5rem 0.9rem', fontSize: '0.84rem' }}
              >
                <Send size={14} /> Send
              </button>
            </div>

            {isBotMode && (
              <div style={{ fontSize: '0.72rem', color: "var(--text-muted)" }}>
                Composer locked: Click <strong>"Switch to Human"</strong> above to take over conversation.
              </div>
            )}
          </form>
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: '0.75rem',
            display: isMobile && mobileView === 'list' ? 'none' : 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: "var(--text-muted)",
            fontSize: '0.875rem',
          }}
        >
          Select a conversation from the list to view chat transcript.
        </div>
      )}

      {/* 3. Customer Context Panel (Desktop Sidebar / Mobile Drawer) */}
      {showContext && selectedConv && (
        <CustomerContextPanel
          customerId={selectedConv.customer_id ?? null}
          conversationId={selectedConv.id}
          handoffSummary={selectedConv.handoff_summary}
          onNavigate={onNavigate}
          onClose={() => setShowContext(false)}
          isMobile={contextAsDrawer}
        />
      )}

      {/* 4. Collapsible AI Simulator Drawer/Sidebar (Desktop / Laptop Friendly) */}
      {showSimulator && (
        <div
          style={{
            width: isMobile ? '100%' : '19rem',
            position: isMobile ? 'absolute' : 'relative',
            right: 0,
            top: 0,
            bottom: 0,
            zIndex: 20,
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: '0.75rem',
            display: 'flex',
            flexDirection: 'column',
            padding: '1rem',
            boxShadow: isMobile ? '0 10px 25px rgba(0,0,0,0.5)' : 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sparkles size={15} style={{ color: "var(--primary)" }} />
              <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: "var(--text-main)", margin: 0 }}>AI Simulator</h3>
            </div>
            <button
              onClick={() => setShowSimulator(false)}
              className="btn btn-secondary btn-sm"
              style={{ padding: '2px 6px', fontSize: '0.7rem' }}
            >
              <X size={13} />
            </button>
          </div>
          <p style={{ fontSize: '0.72rem', color: "var(--text-muted)", marginBottom: '0.85rem' }}>
            Test customer messages directly against your knowledge base and services without Meta API credentials.
          </p>

          <form onSubmit={handleSendSimulated} style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', flex: 1 }}>
            <textarea
              rows={4}
              placeholder="Simulate customer message (e.g. 'What services do you provide?')"
              value={simText}
              onChange={(e) => setSimText(e.target.value)}
              className="input-field"
              style={{ resize: 'none', fontSize: '0.78rem' }}
            />
            <button type="submit" disabled={simLoading || !simText.trim()} className="btn btn-primary btn-sm">
              <Send size={13} /> {simLoading ? 'Simulating...' : 'Test AI Bot Response'}
            </button>
          </form>
        </div>
      )}

      {/* 5. New Chat Modal */}
      <NewChatModal
        isOpen={showNewChatModal}
        onClose={() => setShowNewChatModal(false)}
        onConversationCreated={(newConvId) => {
          loadConversations(false, newConvId);
        }}
      />
    </div>
  );
};