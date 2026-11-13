
    function switchTab(tabId) {
        document.querySelectorAll('.pill-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
        });
        document.querySelectorAll('.nav-icon-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
        });
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === tabId);
        });
        window.location.hash = tabId.replace('tab-', '');
    }

    document.querySelectorAll('.pill-tab-btn, .nav-icon-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.getAttribute('data-tab');
            if (tab) switchTab(tab);
        });
    });

    window.addEventListener('DOMContentLoaded', () => {
        const hash = window.location.hash.replace('#', '');
        if (hash) {
            const target = 'tab-' + hash;
            if (document.getElementById(target)) {
                switchTab(target);
            }
        }
    });

    function openTagModal(customerId, customerName) {
        document.getElementById('tagModalTitle').textContent = `Tag Services for ${customerName}`;
        document.getElementById('tagServiceForm').action = `/customers/${customerId}/tag/`;
        document.getElementById('tagServiceModal').style.display = 'flex';
    }

    function closeTagModal() {
        document.getElementById('tagServiceModal').style.display = 'none';
    }

    // Lead Funnel 1 Filtering (in Overview Tab)
    function setLeadFilter(category, btnElem) {
        document.querySelectorAll('.lead-filter-btn').forEach(b => b.classList.remove('active'));
        if (btnElem) {
            btnElem.classList.add('active');
        } else {
            const btn = document.querySelector(`.lead-filter-btn[data-category="${category}"]`);
            if (btn) btn.classList.add('active');
        }
        filterLeads();
    }

    function filterLeads() {
        const activeBtn = document.querySelector('.lead-filter-btn.active');
        const selectedCategory = activeBtn ? activeBtn.getAttribute('data-category') : 'ALL';
        const searchInput = document.getElementById('leadSearchInput');
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';

        const rows = document.querySelectorAll('.lead-row');
        rows.forEach(row => {
            const rowCat = row.getAttribute('data-category');
            const searchData = row.getAttribute('data-search').toLowerCase();

            const matchCategory = (selectedCategory === 'ALL' || rowCat === selectedCategory);
            const matchSearch = (!query || searchData.includes(query));

            row.style.display = (matchCategory && matchSearch) ? '' : 'none';
        });
    }

    // Lead Funnel 2 Filtering (in Dedicated Leads Tab)
    function setLeadFilter2(category, btnElem) {
        document.querySelectorAll('.lead-filter-btn2').forEach(b => b.classList.remove('active'));
        if (btnElem) {
            btnElem.classList.add('active');
        } else {
            const btn = document.querySelector(`.lead-filter-btn2[data-category="${category}"]`);
            if (btn) btn.classList.add('active');
        }
        filterLeads2();
    }

    function filterLeads2() {
        const activeBtn = document.querySelector('.lead-filter-btn2.active');
        const selectedCategory = activeBtn ? activeBtn.getAttribute('data-category') : 'ALL';
        const searchInput = document.getElementById('leadSearchInput2');
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';

        const rows = document.querySelectorAll('.lead-row2');
        rows.forEach(row => {
            const rowCat = row.getAttribute('data-category');
            const searchData = row.getAttribute('data-search').toLowerCase();

            const matchCategory = (selectedCategory === 'ALL' || rowCat === selectedCategory);
            const matchSearch = (!query || searchData.includes(query));

            row.style.display = (matchCategory && matchSearch) ? '' : 'none';
        });
    }

    // Quick jump from KPI Cards to Lead Funnel Category
    function jumpToLeadCategory(category) {
        switchTab('tab-overview');
        const section = document.getElementById('leadFunnelSection');
        if (section) {
            section.scrollIntoView({ behavior: 'smooth' });
        }
        setLeadFilter(category);
    }

    // Open Interactive Chat Transcript Modal
    let selectedConversationId = null;
    function openConversationModal(convId) {
        selectedConversationId = convId;
        const modal = document.getElementById('chatTranscriptModal');
        const container = document.getElementById('modalChatMessages');
        container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading chat transcript...</div>';
        modal.style.display = 'flex';

        fetch(`/conversations/${convId}/messages/`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('modalChatTitle').textContent = `${data.customer_phone}`;
                document.getElementById('modalChatSubtitle').textContent = `Customer: ${data.customer_name} • Inquired: ${data.service}`;
                document.getElementById('modalChatStatus').textContent = data.status;
                document.getElementById('supportOwner').textContent = data.handover_required ?
                    (data.assigned_staff ? `Picked up by ${data.assigned_staff.name}` : 'Waiting for team pickup') : 'Assistant is active';
                document.getElementById('claimChatButton').hidden = !data.handover_required || !!data.assigned_staff;
                document.getElementById('releaseChatButton').hidden = !data.assigned_staff || !data.can_manage;
                document.getElementById('pauseBotButton').hidden = data.handover_required;
                document.getElementById('resumeBotButton').disabled = !data.can_manage;
                document.getElementById('staffReply').disabled = !data.can_manage;
                document.querySelector('#staffReplyForm button').disabled = !data.can_manage;
                document.getElementById('handoffSummary').textContent = data.handoff_summary || '';
                document.getElementById('handoffSummary').hidden = !data.handoff_summary;

                const cleanPhone = data.customer_phone.replace(/\D/g, '');
                const fullPhone = cleanPhone.length === 10 ? '91' + cleanPhone : cleanPhone;
                document.getElementById('modalChatWaLink').href = `https://wa.me/${fullPhone}?text=Hello%20${encodeURIComponent(data.customer_name)},%20following%20up%20on%20your%20inquiry%20regarding%20${encodeURIComponent(data.service)}.`;

                if (!data.messages || data.messages.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No messages recorded in this chat yet.</div>';
                    return;
                }

                container.innerHTML = '';
                data.messages.forEach(msg => {
                    const isCustomer = (msg.direction === 'INBOUND' || msg.sender_type === 'CUSTOMER');
                    const bubbleWrap = document.createElement('div');
                    bubbleWrap.style.display = 'flex';
                    bubbleWrap.style.flexDirection = 'column';
                    bubbleWrap.style.alignItems = isCustomer ? 'flex-start' : 'flex-end';
                    bubbleWrap.style.marginBottom = '0.5rem';

                    const meta = document.createElement('div');
                    meta.style.fontSize = '0.7rem';
                    meta.style.color = '#94a3b8';
                    meta.style.marginBottom = '2px';
                    meta.textContent = `${isCustomer ? 'Customer' : (msg.sender_type === 'HUMAN' ? 'Service team' : 'Service assistant')} • ${msg.timestamp}`;

                    const bubble = document.createElement('div');
                    bubble.style.maxWidth = '80%';
                    bubble.style.padding = '0.7rem 1rem';
                    bubble.style.borderRadius = '16px';
                    bubble.style.fontSize = '0.85rem';
                    bubble.style.lineHeight = '1.45';
                    bubble.style.wordBreak = 'break-word';

                    if (isCustomer) {
                        bubble.style.background = '#f1f5f9';
                        bubble.style.color = '#0f172a';
                        bubble.style.borderBottomLeftRadius = '4px';
                    } else {
                        bubble.style.background = '#087f79';
                        bubble.style.color = '#ffffff';
                        bubble.style.borderBottomRightRadius = '4px';
                    }
                    bubble.textContent = msg.text;

                    bubbleWrap.appendChild(meta);
                    bubbleWrap.appendChild(bubble);
                    container.appendChild(bubbleWrap);
                });

                container.scrollTop = container.scrollHeight;
            })
            .catch(err => {
                container.innerHTML = '<div style="text-align: center; color: #e11d48; padding: 2rem;">Failed to load chat history.</div>';
            });
    }

    function closeConversationModal() {
        document.getElementById('chatTranscriptModal').style.display = 'none';
    }
    async function conversationAction(action, text = '') {
        const feedback = document.getElementById('conversationActionFeedback');
        const body = new URLSearchParams({action, text});
        try {
            const response = await fetch(`/conversations/${selectedConversationId}/action/`, {method:'POST',headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not update the conversation.');
            feedback.textContent = data.message || (action === 'resume' ? 'Assistant resumed.' : 'Assistant paused.');
            document.getElementById('staffReply').value = '';
            openConversationModal(selectedConversationId);
        } catch (error) { feedback.textContent = error.message; }
    }
    document.getElementById('resumeBotButton').addEventListener('click', () => conversationAction('resume'));
    document.getElementById('claimChatButton').addEventListener('click', () => conversationAction('claim'));
    document.getElementById('releaseChatButton').addEventListener('click', () => conversationAction('release'));
    document.getElementById('pauseBotButton').addEventListener('click', () => conversationAction('pause'));
    document.getElementById('testAIConnection').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        const message = document.getElementById('aiConnectionMessage');
        message.textContent = 'Testing the configured AI provider…';
        try {
            const response = await fetch('/chatbot/connection/test/', {method:'POST', headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}});
            if (!response.ok) throw new Error('Connection test could not complete. Please retry.');
            const data = await response.json();
            document.getElementById('aiConnectionStatus').textContent = data.status;
            message.textContent = data.message;
            document.getElementById('aiConnectionChecked').textContent = data.checked_at ?
                `Last provider result: ${new Date(data.checked_at).toLocaleString()} · ${data.latency_ms} ms` : 'No provider result recorded.';
        } catch (error) { message.textContent = error.message; }
        finally { button.disabled = false; }
    });
    document.getElementById('staffReplyForm').addEventListener('submit', event => {event.preventDefault();conversationAction('reply', document.getElementById('staffReply').value);});
    document.addEventListener('keydown', event => {if(event.key === 'Escape'){closeConversationModal();closeTagModal();}});
