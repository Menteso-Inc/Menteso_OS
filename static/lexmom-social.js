/* Dedicated authenticated Lexmom content workspace. No publish action is armed. */
function lexmomSocialConnectionChip(platform, data) {
    const name=platform==='linkedin' ? 'LinkedIn' : 'YouTube';
    const connection=data.connections?.[platform] || {};
    const checked=Date.parse(data.checked_at);
    const age=Date.now()-checked;
    const fresh=Number.isFinite(checked) && age>=-60000 && age<=30*60*1000;
    let status='disconnected', label='Not connected';
    if(state.lexmom.socialLoadError) {status='attention';label='Check connection';}
    else if(!state.lexmom.social) {status='checking';label='Checking';}
    else if(connection.connected===true && data.configured?.[platform]===true && fresh) {status='connected';label='Connected';}
    else if(data.apps_configured?.[platform] && data.connection_readiness?.[platform]?.available===false) {status='attention';label='Approval pending';}
    else if(data.configured?.[platform]===true || connection.connected===true) {status='attention';label='Check connection';}
    const detail=state.lexmom.socialLoadError || (status==='connected' ? `Verified ${formatTimestamp(data.checked_at)}` : connection.connected===true && !fresh ? 'The last check is out of date. Use Check API connections.' : data.connection_readiness?.[platform]?.reason || connection.reason || (status==='checking' ? 'Loading connection status' : 'API authorization has not been verified'));
    const active=state.lexmom.socialPlatformFilter===platform;
    return `<button type="button" class="lexmom-social-connection-chip is-${status}" data-social-filter="${platform}" data-social-platform="${platform}" data-connection-state="${status}" aria-pressed="${active}" aria-controls="lexmom-social-posts" title="${lexmomAttr(detail)}"><span class="lexmom-social-connection-dot" aria-hidden="true"></span><strong>${name}</strong><span>${label}</span></button>`;
}

function lexmomSocialPostDate(value, fallback) {
    return value && Number.isFinite(Date.parse(value)) ? `<time datetime="${lexmomAttr(value)}">${esc(formatTimestamp(value))}</time>` : `<span class="lexmom-social-date-empty">${esc(fallback)}</span>`;
}

function lexmomSocialAttemptNeedsAttention(data) {
    const attempt=data.connection_attempt;
    if(attempt?.outcome!=='connection-needs-attention')return false;
    if(attempt.platform==='linkedin' && data.connection_readiness?.linkedin?.available===false)return false;
    const checked=Date.parse(data.checked_at), attempted=Date.parse(attempt.checked_at), age=Date.now()-checked;
    const recovered=!state.lexmom.socialLoadError && data.configured?.[attempt.platform]===true && data.connections?.[attempt.platform]?.connected===true && Number.isFinite(attempted) && checked>=attempted && age>=-60000 && age<=30*60*1000;
    return !recovered;
}

function renderLexmomSocialPostDetails(row, data) {
    const locked=['publishing','processing','uploaded','published','needs_reconciliation'].includes(row.status);
    return `<article class="lexmom-social-card"><h4 id="lexmom-social-post-title">${esc(row.title)}</h4><p>${row.platform==='linkedin' ? 'LinkedIn' : 'YouTube'} · LexMom ${row.product==='manage' ? 'Manage' : 'Launch'}</p>
        ${row.platform === 'youtube' && row.video ? `<video controls preload="metadata" poster="/api/agents/lexmom_marketing_agent/email-assets/${encodeURIComponent(row.image)}" aria-label="${lexmomAttr(row.title)}" src="/api/agents/lexmom_marketing_agent/social/${encodeURIComponent(row.key)}/media"></video>` : `<img loading="lazy" alt="${lexmomAttr(row.product)} AI campaign illustration" src="/api/agents/lexmom_marketing_agent/social/${encodeURIComponent(row.key)}/media">`}
        <p class="lexmom-social-caption">${esc(row.caption)}</p><small>${row.status==='published' ? 'Posted' : row.status==='uploaded' ? 'Upload processed · '+esc(row.privacy_status || 'private') : row.status==='processing' ? 'Upload accepted · processing' : row.platform==='youtube' ? row.video ? 'Rendered silent vertical promo · not uploaded' : 'Video needs rendering' : 'Private post draft'}</small>${row.platform==='youtube' ? `<p>YouTube visibility: <strong>${esc(({private:'Private',unlisted:'Unlisted',public:'Public'})[row.privacy_status || 'private'])}</strong></p>` : ''}${row.note ? `<p>${esc(row.note)}</p>` : ''}
        <div class="lexmom-social-actions"><button class="secondary-btn" data-social-edit="${lexmomAttr(row.key)}" ${locked ? 'disabled' : ''}>Edit</button>${row.platform==='youtube' ? `<button class="secondary-btn" data-social-render="${lexmomAttr(row.key)}" ${locked ? 'disabled' : ''}>Render video</button>` : ''}<button class="secondary-btn" data-social-approve="${lexmomAttr(row.key)}" ${locked || !data.apps_configured?.[row.platform] || row.status==='approved' || row.platform==='youtube' && !row.video ? 'disabled' : ''}>Approve draft</button><button class="secondary-btn" data-social-pause="${lexmomAttr(row.key)}" ${locked || row.status==='paused' ? 'disabled' : ''}>Pause</button></div>
        <div class="lexmom-social-actions"><label>Publish time (your local time)<input type="datetime-local" data-social-time="${lexmomAttr(row.key)}" ${!data.publishing_enabled || row.status!=='approved' || !data.connections?.[row.platform]?.connected ? 'disabled' : ''}></label><button class="secondary-btn" data-social-schedule="${lexmomAttr(row.key)}" ${!data.publishing_enabled || row.status!=='approved' || !data.connections?.[row.platform]?.connected ? 'disabled' : ''}>Schedule</button>${row.scheduled_at ? `<small>Scheduled: ${esc(formatTimestamp(row.scheduled_at))}</small>` : ''}</div>
        <details><summary>Edit draft</summary><label>Title<input maxlength="100" data-social-title="${lexmomAttr(row.key)}" value="${lexmomAttr(row.title)}" ${locked ? 'disabled' : ''}></label><label>Caption<textarea maxlength="3000" data-social-caption="${lexmomAttr(row.key)}" ${locked ? 'disabled' : ''}>${esc(row.caption)}</textarea></label>${row.platform==='youtube' ? `<label>YouTube visibility<select data-social-privacy="${lexmomAttr(row.key)}" ${locked ? 'disabled' : ''}>${['private','unlisted','public'].map(value=>`<option value="${value}" ${(row.privacy_status || 'private')===value ? 'selected' : ''}>${({private:'Private',unlisted:'Unlisted',public:'Public'})[value]}</option>`).join('')}</select></label><small>Visibility is included in draft approval. Changing it requires approval again.</small>` : ''}<button class="secondary-btn" data-social-save="${lexmomAttr(row.key)}" ${locked ? 'disabled' : ''}>Save changes</button></details></article>`;
}

function renderLexmomSocialWorkspace() {
    const data=state.lexmom.social || {};
    const rows=data.drafts || [];
    const metrics=data.metrics || {};
    const filter=state.lexmom.socialPlatformFilter || 'all';
    const visible=rows.filter(row=>filter==='all' || row.platform===filter).sort((a,b)=>a.proposed_day-b.proposed_day);
    const selected=rows.find(row=>row.key===state.lexmom.socialPostKey);
    const statuses={draft:'Created',approved:'Approved',scheduled:'Scheduled',publishing:'Posting',processing:'Processing',uploaded:'Uploaded',published:'Posted',needs_reconciliation:'Needs review',failed:'Failed',paused:'Paused'};
    return `<section class="lexmom-social"><div class="lexmom-social-heading"><div><h3>Social Media Posting</h3><div class="lexmom-social-connection-chips" role="group" aria-label="Filter posts by connected platform"><button type="button" class="lexmom-social-connection-chip" data-social-filter="all" aria-pressed="${filter==='all'}" aria-controls="lexmom-social-posts">All posts</button>${['linkedin','youtube'].map(platform=>lexmomSocialConnectionChip(platform,data)).join('')}</div><p>LexMom Manage &amp; LexMom Launch · ${data.publishing_enabled ? 'reviewed publishing activated' : 'publishing and uploads disabled'}</p></div>
        <button class="secondary-btn" id="lexmom-social-refresh">Refresh</button><button class="secondary-btn" id="lexmom-social-prepare">Prepare starter week</button><button class="secondary-btn" id="lexmom-social-dispatch" ${!data.publishing_enabled || !rows.some(row=>row.status==='scheduled' && Date.parse(row.scheduled_at)<=Date.now()) ? 'disabled' : ''} title="Publishing must be activated and approved posts must be due">Publish due posts</button></div>
        <p class="lexmom-social-publishing-state">${data.publishing_enabled ? 'Publishing activated · only approved, scheduled content can be submitted.' : 'Publishing is off. Scheduling and uploads remain locked until you approve activation.'}</p>
        ${state.lexmom.socialError ? `<div class="warning-banner">${esc(state.lexmom.socialError)}</div>` : ""}
        ${lexmomSocialAttemptNeedsAttention(data) ? '<div class="warning-banner">The last account connection attempt did not finish. Check the dedicated app permissions and selected LexMom destination before reconnecting.</div>' : ''}
        <div class="lexmom-social-summary"><span>${Number(data.counts?.drafts || 0)} drafts</span><span>${Number(data.counts?.approved || 0)} approved</span><span>${Number(data.counts?.published || 0)} published</span></div>
        <div class="lexmom-social-platforms">${["linkedin","youtube"].map(platform => {
            const connection=data.connections?.[platform] || {};
            const ready=data.connection_readiness?.[platform]?.available!==false;
            const connectionDetail=connection.connected ? (platform==='youtube' ? 'Connected to the existing LexMom channel. AWS renews access automatically.' : 'Connected to the existing LexMom Page.') : (!ready ? data.connection_readiness?.[platform]?.reason : '') || connection.reason || (data.apps_configured?.[platform] ? 'Authorize the dedicated application to connect this account.' : 'Dedicated app credentials and exact LexMom destination need setup.');
            return `<div><strong>${platform === "linkedin" ? "LinkedIn · LexMom Page" : "YouTube · LexMom channel"}</strong><p>${connection.connected ? "API connected" : !ready ? "Waiting for LinkedIn approval" : data.configured?.[platform] ? "Connection needs verification" : "API connection required"}</p><small>${esc(connectionDetail)}</small><div class="lexmom-social-actions"><button class="secondary-btn" data-social-connect="${platform}" ${data.apps_configured?.[platform] && ready ? '' : 'disabled'}>${ready ? `${connection.connected ? 'Reconnect' : 'Connect'} ${platform === 'linkedin' ? 'LinkedIn' : 'YouTube'}` : 'Approval pending'}</button></div>${connection.expires_at ? `<small>Access expires: ${esc(formatTimestamp(connection.expires_at))} · ${connection.renewal_mode==='automatic' ? 'Automatic renewal available' : 'Owner reauthorization required'}</small>` : ''}${platform==='youtube' ? `<details><summary>Account controls</summary><p><a href="/api/agents/lexmom_marketing_agent/social/privacy" target="_blank" rel="noopener">YouTube data privacy</a> · <a href="https://security.google.com/settings/security/permissions" target="_blank" rel="noopener">Google account permissions</a></p><p>Disconnect revokes access and removes stored YouTube API data. Locally authored drafts remain. Videos on YouTube are preserved.</p><button type="button" class="secondary-btn" id="lexmom-youtube-disconnect" ${data.configured?.youtube ? '' : 'disabled'}>Disconnect YouTube and remove data</button></details>` : ''}</div>`;
        }).join("")}</div><button class="secondary-btn" id="lexmom-social-check">Check API connections</button>
        <small class="lexmom-social-checked">${data.checked_at ? `Last account check: ${esc(formatTimestamp(data.checked_at))}` : 'Account monitoring starts after deployment.'}</small>
        <details class="lexmom-log"><summary>Performance</summary>${["linkedin","youtube"].map(platform => `<p><strong>${esc(platform)}:</strong> ${metrics[platform] ? Object.entries(metrics[platform]).map(([key,value]) => `${esc(key)}: ${esc(String(value))}`).join(" · ") : esc(data.connections?.[platform]?.metrics_reason || 'Metrics appear after API connection')}</p>`).join("")}</details>
        <div class="section-title">Posts</div><div class="lexmom-social-table-wrap" tabindex="0" aria-label="Social posts; scroll horizontally on smaller screens"><table class="lexmom-social-posts" id="lexmom-social-posts"><caption>${visible.length} of ${rows.length} posts${filter==='all' ? '' : ` · ${filter==='linkedin' ? 'LinkedIn' : 'YouTube'}`}</caption><thead><tr><th scope="col">Post</th><th scope="col">Platform</th><th scope="col">Product</th><th scope="col">Status</th><th scope="col">Created at</th><th scope="col" title="Time public posting was first confirmed">Posted at</th><th scope="col">Details</th></tr></thead><tbody>${visible.length ? visible.map(row=>`<tr data-social-post="${lexmomAttr(row.key)}"><th scope="row">${esc(row.title)}</th><td>${row.platform==='linkedin' ? 'LinkedIn' : 'YouTube'}</td><td>LexMom ${row.product==='manage' ? 'Manage' : 'Launch'}</td><td><span class="lexmom-social-post-status is-${esc(row.status)}">${esc(statuses[row.status] || row.status)}</span></td><td>${lexmomSocialPostDate(row.created_at,'Not recorded')}</td><td>${lexmomSocialPostDate(row.published_at,row.status==='published' ? 'Not recorded' : ['publishing','processing','needs_reconciliation'].includes(row.status) ? 'Unconfirmed' : 'Not posted')}</td><td><button type="button" class="secondary-btn" data-social-details="${lexmomAttr(row.key)}" aria-label="${lexmomAttr('View '+row.title)}">View</button></td></tr>`).join('') : '<tr><td colspan="7" class="memory-empty">No posts for this platform yet.</td></tr>'}</tbody></table></div>
        ${selected ? `<dialog class="lexmom-social-post-dialog" id="lexmom-social-post-dialog" aria-labelledby="lexmom-social-post-title"><div class="lexmom-social-dialog-heading"><strong>Post details</strong><button type="button" class="secondary-btn" id="lexmom-social-close">Close</button></div>${renderLexmomSocialPostDetails(selected,data)}</dialog>` : ''}</section>`;
}

async function loadLexmomSocial() {
    try {
        const response=await fetch('/api/agents/lexmom_marketing_agent/social/data',{cache:'no-store'});
        if (!response.ok) throw Error('Social workspace is unavailable. Check your operator login.');
        state.lexmom.social=await response.json();state.lexmom.socialError='';state.lexmom.socialLoadError='';
    } catch (error) { state.lexmom.socialError=error.message;state.lexmom.socialLoadError=error.message; }
}

function bindLexmomSocialWorkspace() {
    document.querySelectorAll('[data-social-filter]').forEach(button=>{button.onclick=()=>{state.lexmom.socialPlatformFilter=button.dataset.socialFilter;state.lexmom.socialPostKey=null;renderMain();};});
    document.querySelectorAll('[data-social-details]').forEach(button=>{button.onclick=()=>{state.lexmom.socialPostKey=button.dataset.socialDetails;renderMain();};});
    const dialog=document.getElementById('lexmom-social-post-dialog');
    if(dialog){
        const key=state.lexmom.socialPostKey;
        dialog.addEventListener('close',()=>{state.lexmom.socialPostKey=null;renderMain();document.querySelector(`[data-social-details="${key}"]`)?.focus();});
        document.getElementById('lexmom-social-close').onclick=()=>dialog.close();
        dialog.showModal();
    }
    const action=async (path,payload,button) => {
        if (state.lexmom.socialBusy) return;
        state.lexmom.socialBusy=true;if(button)button.disabled=true;
        try {
            const response=await fetch('/api/agents/lexmom_marketing_agent/social/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
            const result=await response.json();if(!response.ok)throw Error(result.detail || result.error || 'Action could not be completed.');
            if(result.authorization_url){
                const destination=new URL(result.authorization_url);
                if(destination.protocol!=='https:' || !['accounts.google.com','www.linkedin.com'].includes(destination.hostname))throw Error('Invalid authorization destination.');
                location.assign(destination.href);return;
            }
            await loadLexmomSocial();
        } catch(error) {state.lexmom.socialError=error.message;}
        finally {state.lexmom.socialBusy=false;renderMain();}
    };
    document.getElementById('lexmom-social-refresh').onclick=async()=>{await loadLexmomSocial();renderMain();};
    document.getElementById('lexmom-social-prepare').onclick=event=>action('prepare',{},event.currentTarget);
    document.getElementById('lexmom-social-check').onclick=event=>action('connections/check',{},event.currentTarget);
    document.getElementById('lexmom-social-dispatch').onclick=event=>action('dispatch',{},event.currentTarget);
    document.querySelectorAll('[data-social-connect]').forEach(button=>{button.onclick=event=>action('oauth/'+button.dataset.socialConnect+'/begin',{},event.currentTarget);});
    const disconnectYoutube=document.getElementById('lexmom-youtube-disconnect');
    if(disconnectYoutube)disconnectYoutube.onclick=event=>{
        if(window.confirm('Disconnect the LexMom YouTube connection and remove its stored YouTube API data? YouTube-hosted videos and locally authored drafts will be preserved.'))action('youtube/disconnect',{confirm:'disconnect-youtube-and-remove-data'},event.currentTarget);
    };
    document.querySelectorAll('[data-social-render],[data-social-approve],[data-social-save],[data-social-edit],[data-social-pause],[data-social-schedule]').forEach(button=>{
        button.onclick=event=>{
            const kind=['render','approve','save','edit','pause','schedule'].find(name=>button.hasAttribute('data-social-'+name));
            const key=button.getAttribute('data-social-'+kind);const row=(state.lexmom.social?.drafts || []).find(row=>row.key===key);if(!row)return;
            if(kind==='edit'){button.closest('article').querySelector('details').open=true;return;}
            const payload={revision:row.revision};let route=kind;
            if(kind==='schedule'){
                const value=button.closest('article').querySelector('[data-social-time]').value;
                const moment=new Date(value);
                if(!value || !Number.isFinite(moment.getTime()) || moment.getTime()<=Date.now()){
                    state.lexmom.socialError='Choose a future publishing time in your local timezone.';renderMain();return;
                }
                payload.scheduled_at=moment.toISOString();
            }
            if(kind==='save'){
                const card=button.closest('article');payload.title=card.querySelector('[data-social-title]').value;payload.caption=card.querySelector('[data-social-caption]').value;route='edit';
                if(row.platform==='youtube')payload.privacy_status=card.querySelector('[data-social-privacy]').value;
            }
            action(encodeURIComponent(key)+'/'+route,payload,event.currentTarget);
        };
    });
    if(!state.lexmom.social && !state.lexmom.socialLoading){
        state.lexmom.socialLoading=true;
        loadLexmomSocial().finally(()=>{
            state.lexmom.socialLoading=false;
            const view=state.lexmom.view || (location.hash.startsWith('#lexmom/') ? location.hash.slice(8) : 'dashboard');
            if(state.selectedAgent?.ui_type==='lexmom_research' && view==='social_media_posting_agent')renderMain();
        });
    }
}
