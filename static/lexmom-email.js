/* Email Campaign is a draft/review workspace. It exposes no send activation. */
async function loadLexmomEmailData() {
    state.lexmom.email = state.lexmom.email || {};
    const email = state.lexmom.email;
    if (email.loading) return;
    email.loading = true;
    try {
        const response = await fetch('/api/agents/lexmom_marketing_agent/email/data', {credentials: 'same-origin'});
        if (!response.ok) throw new Error(response.status === 403 ? 'An operator account is required for mailbox access.' : 'Email workspace is unavailable. Refresh to retry.');
        email.data = await response.json(); email.error = '';
    } catch (error) { email.error = error.message; }
    finally { email.loading = false; email.loaded = true; renderMain(); }
}

function renderLexmomEmailWorkspace() {
    const email = state.lexmom.email || {};
    const data = email.data;
    if (!data) return `<section class="lexmom-email"><p role="status">${esc(email.error || 'Loading Email Campaign…')}</p><button class="lexmom-email-button" id="lexmom-email-refresh">Refresh</button></section>`;
    const view = ['launch','manage','both','sent','replies'].includes(email.view) ? email.view : 'launch';
    const mailbox = data.mailbox_status || {};
    const counts = data.delivery_counts || {};
    const accepted = Number.isInteger(data.accepted_count) ? data.accepted_count : 0;
    const placement = data.placement || {};
    const metrics = [['Campaign emails sent',accepted],['Delivered',counts.delivered || 0],['Bounces',counts.bounced || 0],['Complaints',counts.complained || 0]];
    const choices = [['launch','Launch'],['manage','Manage'],['both','Launch + Manage'],['sent','Sent mail'],['replies','Inbox & replies']];
    const campaigns = data.campaigns || [];
    const campaign = campaigns.find(row => row.product === view);
    const messages = (data.messages || []).filter(row => view === 'sent' ? row.direction === 'sent' : row.direction === 'incoming');
    let content = '';
    if (campaign) {
        content = `<div class="lexmom-email-heading"><div><h3>${esc(campaign.name)}</h3><p>Five drafts · No recipients or sending schedule are active</p></div><span class="badge badge-warning">Paused</span></div>
            <details class="lexmom-email-held"><summary>Strategy & response rules</summary><p>Proposed days: 1, 3, 6, 10 and 14. One contact receives one sequence, with five emails maximum. Product clicks focus the remaining messages; opens alone do not change the sequence. Replies pause follow-ups. Demo requests go to a human; signups and purchases stop acquisition. Opt-outs, hard bounces and complaints suppress sending. Automatic product-event branching is deferred; all drafts remain paused.</p></details>
            <div class="lexmom-email-days">${campaign.steps.map(step => `<details class="lexmom-email-day"><summary><span>Email ${step.day}</span><strong>${esc(step.subject)}</strong></summary>
            <div class="lexmom-email-day-content">
            <p class="lexmom-email-note">${esc(step.kind.replaceAll('_',' '))} · Proposed day ${step.offset_days+1}</p>
            <p class="lexmom-email-topic">${esc(step.topic)}</p>${(data.subject_examples || []).filter(sample => sample.product === view && sample.day === step.day).map(sample => `<p class="lexmom-email-note">Subject examples only:<br>Named contact: ${esc(sample.named)}<br>Firm inbox: ${esc(sample.firm)}</p>`).join('')}<div class="lexmom-email-copy">${esc(step.body)}</div><p class="lexmom-email-note">{firm_name} uses a verified firm name. A sourced introductory fact is added when available; missing facts are omitted.</p>
            <a href="/api/agents/lexmom_marketing_agent/email/preview/${esc(view)}/${step.day}" target="_blank" rel="noopener">Open complete email preview</a></div></details>`).join('')}</div>`;
    } else {
        content = `<div class="lexmom-email-heading"><h3>${view === 'sent' ? 'Sent mail' : 'Inbox & replies'}</h3><span>${messages.length} cached messages</span></div>
            ${!messages.length ? `<div class="memory-empty">${mailbox.connected ? 'No messages in this view yet.' : 'Connect the dedicated Gmail authorization to display live messages.'}</div>` : `<div class="lexmom-email-messages">${messages.map((message,index) => `<details class="lexmom-email-message"><summary><strong>${esc(message.subject || '(No subject)')}</strong><span>${esc(view === 'sent' ? message.to : message.from)}</span></summary><div class="lexmom-email-message-body">${esc(message.body || '')}</div>
            ${view === 'replies' && message.interest_eligible ? `<div class="lexmom-email-interest">${message.interest_confirmed ? '<span>Interest confirmed · Hot lead</span>' : `<label>Interested in <select id="lexmom-interest-product-${index}"><option value="manage" ${message.interest_product === 'manage' ? 'selected' : ''}>Manage</option><option value="launch" ${message.interest_product === 'launch' ? 'selected' : ''}>Launch</option></select></label><button type="button" class="lexmom-email-button" data-confirm-interest="${index}" ${email.confirming ? 'disabled' : ''}>Confirm interest · mark Hot</button><small>Use after reading a positive reply or demo request. This does not send an email.</small>`}</div>` : ''}</details>`).join('')}</div>`}`;
        if (view === 'replies' && (data.reply_tasks || []).length) {
            content += `<div class="lexmom-email-heading"><h3>Requests & follow-ups</h3><span>Responses held for review</span></div><div class="lexmom-email-messages">${data.reply_tasks.map(task => `<details class="lexmom-email-message"><summary><strong>${esc(task.subject)}</strong><span>${esc(task.sender)} · ${esc(task.product || 'Product to confirm')}</span></summary><div class="lexmom-email-message-body">${esc(task.suggested_next_step)}</div></details>`).join('')}</div>`;
        }
    }
    return `<section class="lexmom-email"><div class="lexmom-email-heading"><div><h3>Email Campaign</h3><p>${mailbox.connected ? `Connected: ${esc(mailbox.mailbox)} · Last synced ${esc(mailbox.last_synced || '')}` : esc(mailbox.reason || 'Gmail authorization is pending')}</p></div><button class="lexmom-email-button" id="lexmom-email-refresh" ${email.loading ? 'disabled' : ''}>${email.loading ? 'Refreshing…' : 'Refresh'}</button></div>
        ${email.error ? `<p role="alert" class="warning-banner">${esc(email.error)}</p>` : ''}
        <div class="lexmom-email-metrics">${metrics.map(([label,value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>
        <p class="lexmom-email-note">Inbox placement: ${Number.isInteger(placement.inbox) ? `${placement.inbox} Inbox / ${placement.spam || 0} Spam · controlled seed observations only` : 'Unknown for prospects. Delivery events do not reveal their folder placement.'}</p>
        <div class="lexmom-email-nav" aria-label="Email Campaign views">${choices.map(([id,label]) => `<button type="button" class="lexmom-chip" data-email-view="${id}" aria-pressed="${view === id}">${label}</button>`).join('')}</div>${content}
        <details class="lexmom-email-held"><summary>Held contacts (${(data.held_contacts || []).length})</summary>${(data.held_contacts || []).map(row => `<p>${esc(row.email)} · ${esc(JSON.parse(row.hold_reasons).join('; '))}</p>`).join('') || '<p>No contacts have been enrolled. A saved draft is not a send.</p>'}</details>
        <p class="lexmom-email-note">${data.review?.sent ? (data.review.matches_current_drafts ? 'Internal campaign review sent to Sajan. Prospect campaigns remain paused.' : 'Earlier review sent to Sajan. Updated drafts remain paused; no new review has been sent.') : 'Internal review is separate from prospect campaign sending.'}</p></section>`;
}

function bindLexmomEmailWorkspace() {
    state.lexmom.email = state.lexmom.email || {};
    const email = state.lexmom.email;
    if (!email.loaded && !email.loading) loadLexmomEmailData();
    document.getElementById('lexmom-email-refresh')?.addEventListener('click', loadLexmomEmailData);
    document.querySelectorAll('[data-email-view]').forEach(button => button.addEventListener('click', () => {
        email.view = button.dataset.emailView; renderMain();
        document.querySelector(`[data-email-view="${email.view}"]`)?.focus();
    }));
    document.querySelectorAll('[data-confirm-interest]').forEach(button => button.addEventListener('click', async () => {
        if (email.confirming) return;
        const index=Number(button.dataset.confirmInterest);
        const message=(email.data?.messages || []).filter(row=>row.direction==='incoming')[index];
        const product=document.getElementById(`lexmom-interest-product-${index}`)?.value;
        if (!message?.interest_eligible || !['manage','launch'].includes(product)) return;
        email.confirming=true;button.disabled=true;
        try {
            const response=await fetch('/api/agents/lexmom_marketing_agent/email/confirm-interest',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:message.sender_email,message_id:message.message_id,product})});
            if (!response.ok) throw new Error('Interest could not be confirmed. Refresh and select an actual lead reply.');
            await loadLexmomEmailData();
            await loadLexmomDashboardData(state.selectedAgent.module_name);
        } catch(error) { email.error=error.message; }
        finally { email.confirming=false;renderMain(); }
    }));
}
