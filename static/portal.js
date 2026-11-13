(() => {
    'use strict';
    const stream = document.getElementById('chatStream');
    const input = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const error = document.getElementById('chatError');
    let busy = false;
    let retry = null;
    let conversationId = null;
    let supportPoll = null;
    const seenHumanMessages = new Set();
    const scroll = () => { stream.scrollTop = stream.scrollHeight; };
    function append(text, customer = false, options = [], timestamp = null) {
        if (!text) return;
        if (!customer) stream.querySelectorAll('.message-options').forEach(group => {
            group.dataset.stale = 'true'; group.querySelectorAll('button').forEach(button => button.disabled = true);
        });
        const item = document.createElement('div'); item.className = 'message' + (customer ? ' customer' : '');
        const copy = document.createElement('div'); copy.className = 'message-copy';
        // Render only WhatsApp-style emphasis; all content remains plain text nodes.
        text.split(/(\*[^*\n]+\*)/g).forEach(part => {
            if (part.startsWith('*') && part.endsWith('*')) { const strong = document.createElement('strong'); strong.textContent = part.slice(1, -1); copy.append(strong); }
            else copy.append(document.createTextNode(part));
        });
        item.append(copy);
        if (options && options.length) {
            const actions = document.createElement('div'); actions.className = 'message-options';
            options.forEach(option => {
                const button = document.createElement('button'); button.type = 'button';
                const label = document.createElement('span'); label.textContent = option.title;
                if (option.description) { const description = document.createElement('small'); description.textContent = option.description; label.append(description); }
                const arrow = document.createElement('span'); arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true');
                button.append(label, arrow); button.addEventListener('click', () => send(option.id || option.title, option.title)); actions.append(button);
            }); item.append(actions);
        }
        const meta = document.createElement('div'); meta.className = 'message-meta';
        const date = timestamp ? new Date(timestamp) : new Date();
        meta.textContent = (customer ? 'You' : 'Service desk') + ' · ' + date.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        item.append(meta); stream.append(item); scroll();
    }
    function setBusy(value) {
        busy = value; sendButton.disabled = value; input.disabled = value;
        document.querySelectorAll('[data-action], .message-options button, #chatMenu').forEach(button => button.disabled = value || Boolean(button.closest('[data-stale]')));
        document.querySelectorAll('#bookingTools button, #bookingTools input, #bookingTools select').forEach(field => field.disabled = value);
        sendButton.textContent = value ? '·' : '↑';
    }
    function renderState(data) {
        conversationId = data.conversation_id || conversationId;
        if (data.handover_required && !supportPoll) supportPoll = setInterval(refreshSupport, 6000);
        if (!data.handover_required && supportPoll) { clearInterval(supportPoll); supportPoll = null; }
        if (data.bookings?.length) {
            const section = document.getElementById('portal-bookings');
            section.querySelectorAll('.booking-item, .booking-empty').forEach(item => item.remove());
            data.bookings.forEach(booking => {
                const item = document.createElement('div'); item.className = 'booking-item';
                const icon = document.createElement('div'); icon.className = 'booking-icon'; icon.textContent = '▤';
                const details = document.createElement('div'); const title = document.createElement('strong'); title.textContent = booking.service;
                const subtitle = document.createElement('p'); subtitle.textContent = `#${booking.id} · ${booking.date}${booking.time ? ' · ' + booking.time : ''}${booking.recipient_name ? ' · For ' + booking.recipient_name : ''}`; details.append(title, subtitle);
                const status = document.createElement('span'); status.className = 'booking-state state-' + booking.status.toLowerCase(); status.textContent = booking.status_label;
                item.append(icon, details, status); section.append(item);
            });
        }
        const progress = document.getElementById('bookingProgress');
        const step = data.booking_progress?.active ? data.booking_progress.step : null;
        document.getElementById('bookingTools').hidden = data.handover_required || !['AC_DETAILS','SCHEDULE'].includes(step);
        document.getElementById('acDetailsForm').hidden = step !== 'AC_DETAILS';
        document.getElementById('scheduleForm').hidden = step !== 'SCHEDULE';
        if (step === 'AC_DETAILS' && data.booking_progress.ac_type) {
            const type = document.getElementById('acType');
            if ([...type.options].some(option => option.value === data.booking_progress.ac_type)) type.value = data.booking_progress.ac_type;
        }
        if (step === 'SCHEDULE' && data.booking_progress.preferred_date) document.getElementById('visitDate').value = data.booking_progress.preferred_date;
        progress.hidden = !data.booking_progress || !data.booking_progress.active;
        if (!progress.hidden) {
            document.getElementById('progressLabel').textContent = data.booking_progress.label;
            document.getElementById('progressCount').textContent = `${data.booking_progress.current} / ${data.booking_progress.total}`;
            document.getElementById('progressFill').style.width = `${data.booking_progress.current / data.booking_progress.total * 100}%`;
        }
        document.getElementById('chatStatus').textContent = data.handover_required ? 'Waiting for the service team · Your messages are saved' : 'Automated service assistant · Team support available';
        if (data.handover_required) stream.querySelectorAll('.message-options').forEach(group => { group.dataset.stale = 'true'; });
        document.getElementById('composerNote').textContent = data.handover_required ? 'The team has your conversation. Type “resume bot” for automated help.' : 'Appointment requests are confirmed by our team.';
        const suggestions = document.getElementById('suggestions'); suggestions.replaceChildren();
        const choices = data.handover_required ? [{id:'resume bot',title:'Resume assistant'}] : (data.booking_progress?.active ? [] : [{id:'view_services',title:'View services'},{id:'booking status',title:'My bookings'},{id:'talk to agent',title:'Talk to team'}]);
        choices.forEach(choice => { const button = document.createElement('button'); button.type = 'button'; button.textContent = choice.title; button.addEventListener('click', () => send(choice.id, choice.title)); suggestions.append(button); });
    }
    async function refreshSupport() {
        if (busy || !conversationId || document.hidden) return;
        try {
            const response = await fetch(`/conversations/${conversationId}/messages/`);
            if (!response.ok) return;
            const data = await response.json();
            (data.messages || []).filter(message => message.sender_type === 'HUMAN' && !seenHumanMessages.has(message.id)).forEach(message => {
                seenHumanMessages.add(message.id); append(message.text);
            });
            renderState(data);
        } catch (_) { /* Keep the conversation available while a connection recovers. */ }
    }
    async function send(message, title = message, isRetry = false) {
        if (busy || !message.trim()) return;
        error.hidden = true; setBusy(true);
        if (!isRetry) append(title, true);
        input.value = '';
        const typing = document.createElement('div'); typing.className = 'typing-dots'; typing.textContent = 'Preparing your reply…'; stream.append(typing); scroll();
        const requestId = isRetry && retry ? retry.requestId : crypto.randomUUID();
        retry = {message, title, requestId};
        const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 45000);
        try {
            const response = await fetch('/chat/send/', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify({message_text:message, conversation_id:conversationId, request_id:requestId}), signal:controller.signal});
            if (!response.ok) throw new Error(response.status === 403 ? 'Your session has expired. Sign in again to continue.' : 'We couldn’t send that message. Please try again.');
            const data = await response.json();
            append(data.reply, false, data.options); renderState(data); retry = null;
        } catch (cause) {
            document.getElementById('errorText').textContent = cause.name === 'AbortError' ? 'The reply is taking longer than expected. Try again to recover it.' : (cause instanceof TypeError ? 'Connection lost. Check your connection and try again.' : cause.message);
            error.hidden = false;
        } finally { clearTimeout(timeout); typing.remove(); setBusy(false); input.focus(); scroll(); }
    }
    document.getElementById('chatForm').addEventListener('submit', event => { event.preventDefault(); send(input.value.trim()); });
    document.getElementById('acDetailsForm').addEventListener('submit', event => {event.preventDefault();send(document.getElementById('acType').value + ': ' + document.getElementById('acProblem').value.trim());});
    document.getElementById('scheduleForm').addEventListener('submit', event => {event.preventDefault();send(document.getElementById('visitDate').value + ' at ' + document.getElementById('visitTime').value);});
    const today = new Date();
    const localDate = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
    document.getElementById('visitDate').min = localDate(today);
    document.getElementById('visitDate').max = localDate(new Date(today.getFullYear(), today.getMonth(), today.getDate()+180));
    input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(input.value.trim()); } });
    document.getElementById('retrySend').addEventListener('click', () => { if (retry) send(retry.message, retry.title, true); });
    document.getElementById('chatMenu').addEventListener('click', () => send('main menu', 'Main menu'));
    document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => {
        send(button.dataset.action, button.dataset.title);
        if (button.closest('.service-tile')) { document.querySelectorAll('.service-tile').forEach(tile => tile.classList.remove('selected')); button.closest('.service-tile').classList.add('selected'); }
        if (window.innerWidth < 821) document.getElementById('serviceChat').scrollIntoView({behavior:'smooth'});
    }));
    document.getElementById('serviceSearch').addEventListener('input', event => {
        const query = event.target.value.toLocaleLowerCase().trim(); let visible = 0;
        document.querySelectorAll('.service-tile').forEach(tile => { tile.hidden = !tile.dataset.name.toLocaleLowerCase().includes(query); if (!tile.hidden) visible++; });
        document.getElementById('noServiceResults').hidden = visible > 0;
    });
    document.querySelectorAll('.nav-icon-btn[data-tab]').forEach(button => button.addEventListener('click', () => {
        const target = { 'tab-overview':'portal-overview','tab-services':'portal-services','tab-bookings':'portal-bookings' }[button.dataset.tab];
        document.getElementById(target)?.scrollIntoView({behavior:'smooth'});
        document.querySelectorAll('.nav-icon-btn[data-tab]').forEach(nav => nav.classList.toggle('active', nav === button));
    }));
    const history = JSON.parse(document.getElementById('chatHistory').textContent);
    if (history.messages?.length) { document.querySelector('.chat-welcome').remove(); history.messages.forEach(message => {seenHumanMessages.add(message.id);append(message.text, message.direction === 'INBOUND', message.options || [], message.timestamp);}); renderState(history); }
})();
