/* ============================================================
   Menteso Virtual Office — Dashboard Frontend
   ============================================================ */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
    theme: localStorage.getItem("menteso-theme") || "dark",
    agents: [],
    selectedAgent: null,
    isRunning: false,
    stopRequested: false,
    agentRunStatus: "idle",
    inputMode: "upload",
    executionLog: [],
    lastResult: null,
    startTime: null,
    uploadedFilePath: null,
    wipoGazettes: [],
    wipoGazettesLoaded: false,
    wipoGazettesLoading: false,
    wipoGazettesError: "",
    selectedGazette: "",
    seo: {
        topicOverride: "",
        publishOverride: "draft",
        enableFeaturedImage: true,
        dryRun: false,
        google: {
            clientId: "",
            clientSecret: "",
            property: "sc-domain:patentzoom.us",
            clientConfigured: false,
            connected: false,
            redirectUri: "http://127.0.0.1:8000/api/google/search-console/callback",
        },
    },
    seoDashboard: {
        loading: false,
        error: "",
        snapshot: null,
        workflow: {
            currentStage: "",
            currentMessage: "",
            stages: [],
        },
        previewArticle: null,
        historyEntry: null,
    },
    pipelineMode: false,
    pipeline: null,
    captcha: {
        active: false,
        message: "",
        resolvedMessage: "",
    },
    browser: {
        url: "",
        event: "idle",
        patent_id: "",
        title: "",
        applicant: "",
        country: "",
        row: 0,
        total: 0,
        pdf_url: "",
        emails: [],
        phones: [],
        name: "",
        status: "",
        found_count: 0,
        not_found_count: 0,
        error_count: 0,
    },
};

let alertAudioContext = null;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
    applyTheme(state.theme);
    const themeToggleBtn = document.getElementById("theme-toggle-btn");
    if (themeToggleBtn) {
        themeToggleBtn.onclick = () => toggleTheme();
    }
    await loadAgents();
    render();
});

function applyTheme(theme) {
    state.theme = theme === "light" ? "light" : "dark";
    document.body.setAttribute("data-theme", state.theme);
    localStorage.setItem("menteso-theme", state.theme);
    const themeToggleBtn = document.getElementById("theme-toggle-btn");
    if (themeToggleBtn) {
        themeToggleBtn.textContent = state.theme === "light" ? "🌙 Dark" : "☀️ Light";
    }
}

function toggleTheme() {
    applyTheme(state.theme === "light" ? "dark" : "light");
    render();
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
async function loadAgents() {
    try {
        const res = await fetch("/api/agents");
        state.agents = await res.json();
    } catch (e) {
        console.error("Failed to load agents:", e);
        state.agents = [];
    }
}

async function loadAgentDetail(name) {
    try {
        const res = await fetch(`/api/agents/${name}`);
        return await res.json();
    } catch (e) {
        console.error("Failed to load agent detail:", e);
        return null;
    }
}

async function loadAgentRunStatus(name) {
    try {
        const res = await fetch(`/api/agents/${name}/run-status`);
        const data = await res.json();
        state.agentRunStatus = data.status || "idle";
        return state.agentRunStatus;
    } catch (e) {
        console.error("Failed to load agent run status:", e);
        state.agentRunStatus = "idle";
        return "idle";
    }
}

function resetCaptchaAlert() {
    state.captcha.active = false;
    state.captcha.message = "";
    state.captcha.resolvedMessage = "";
}

function primeAlertAudio() {
    if (alertAudioContext) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    try {
        alertAudioContext = new AudioCtx();
    } catch {
        alertAudioContext = null;
    }
}

async function playCaptchaAlertSound() {
    primeAlertAudio();
    if (!alertAudioContext) return;

    try {
        if (alertAudioContext.state === "suspended") {
            await alertAudioContext.resume();
        }
        const start = alertAudioContext.currentTime;
        [0, 0.22, 0.44].forEach((offset) => {
            const osc = alertAudioContext.createOscillator();
            const gain = alertAudioContext.createGain();
            osc.type = "sine";
            osc.frequency.value = 1046;
            gain.gain.setValueAtTime(0.0001, start + offset);
            gain.gain.exponentialRampToValueAtTime(0.18, start + offset + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.16);
            osc.connect(gain);
            gain.connect(alertAudioContext.destination);
            osc.start(start + offset);
            osc.stop(start + offset + 0.18);
        });
    } catch (e) {
        console.warn("Failed to play CAPTCHA alert sound:", e);
    }
}

async function loadWipoGazettes(force = false) {
    if (state.wipoGazettesLoading) return;
    if (state.wipoGazettesLoaded && !force) return;

    state.wipoGazettesLoading = true;
    state.wipoGazettesError = "";
    renderMain();

    try {
        const res = await fetch("/api/wipo/gazettes");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to load WIPO gazettes");

        state.wipoGazettes = Array.isArray(data.options) ? data.options : [];
        state.wipoGazettesLoaded = true;

        const hasSelected = state.wipoGazettes.some((item) => item.value === state.selectedGazette);
        if (!hasSelected) {
            state.selectedGazette = state.wipoGazettes[0]?.value || "";
        }
    } catch (e) {
        console.error("Failed to load WIPO gazettes:", e);
        state.wipoGazettes = [];
        state.wipoGazettesLoaded = false;
        state.wipoGazettesError = e.message || "Failed to load WIPO gazettes";
    } finally {
        state.wipoGazettesLoading = false;
        renderMain();
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    return await res.json();
}

async function stopAgent(name) {
    const res = await fetch(`/api/agents/${name}/stop`, { method: "POST" });
    return await res.json();
}

async function saveGoogleSearchConsoleConfig() {
    const res = await fetch("/api/google/search-console/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            client_id: state.seo.google.clientId.trim(),
            client_secret: state.seo.google.clientSecret.trim(),
            property: state.seo.google.property.trim() || "sc-domain:patentzoom.us",
        }),
    });
    return await res.json();
}

async function launchGoogleBrowserSession() {
    const res = await fetch("/api/google/search-console/browser-session", {
        method: "POST",
    });
    return await res.json();
}

async function requestGoogleIndexing(url) {
    const res = await fetch("/api/google/search-console/request-indexing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
    });
    return await res.json();
}

async function runAgent(name, params = {}) {
    state.isRunning = true;
    state.stopRequested = false;
    state.agentRunStatus = "running";
    state.executionLog = [];
    state.lastResult = null;
    state.startTime = Date.now();
    state.pipelineMode = false;
    state.pipeline = null;
    resetCaptchaAlert();
    state.browser = {
        url: "", event: "idle", patent_id: "", title: "", applicant: "",
        country: "", row: 0, total: 0, pdf_url: "", emails: [], phones: [],
        name: "", status: "", found_count: 0, not_found_count: 0, error_count: 0,
    };
    if (state.selectedAgent?.ui_type === "seo_posting") {
        resetSeoWorkflow();
        handleSeoWorkflowEvent({
            type: "step",
            message: "Preparing a new PatentZoom SEO run.",
            data: { stage: "readiness", status: "active" },
        }, "step");
    }
    renderMain();

    const method = params.method || "GET";
    const queryParams = params.query || {};
    if (params.file_path) queryParams.file_path = params.file_path;
    if (params.mode) queryParams.mode = params.mode;
    if (params.gazette) queryParams.gazette = params.gazette;

    const query = new URLSearchParams();
    Object.entries(queryParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
            query.set(key, String(value));
        }
    });

    const qs = query.toString();
    const url = `/api/agents/${name}/run${method === "GET" && qs ? "?" + qs : ""}`;
    const fetchOptions = {
        method,
        headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
        body: method === "POST" ? JSON.stringify(params.body || {}) : undefined,
    };

    try {
        const response = await fetch(url, fetchOptions);
        if (!response.ok) {
            let message = `Run failed with status ${response.status}`;
            try {
                const data = await response.json();
                message = data.error || message;
                if (data.status) state.agentRunStatus = data.status;
            } catch {}
            addLogLine(message, "error");
            state.isRunning = false;
            state.stopRequested = false;
            state.browser.event = "done";
            updateBrowserPreview();
            renderMain();
            return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleSSEEvent(data);
                    } catch {}
                }
            }
        }
    } catch (e) {
        addLogLine(`Connection error: ${e.message}`, "error");
    }

    state.isRunning = false;
    state.stopRequested = false;
    state.agentRunStatus = "idle";
    state.browser.event = "done";
    updateBrowserPreview();

    await loadAgents();
    if (state.selectedAgent) {
        const detail = await loadAgentDetail(state.selectedAgent.module_name);
        if (detail) state.selectedAgent = detail;
        if (state.selectedAgent.ui_type === "seo_posting") {
            await loadSeoDashboardData(state.selectedAgent.module_name);
        }
    }
    renderMain();
}

function handleSSEEvent(data) {
    if (data.type === "step") {
        const type = classifyMessage(data.message);
        addLogLine(data.message, type);
        if (state.selectedAgent?.ui_type === "seo_posting") {
            handleSeoWorkflowEvent(data, type);
        }
    } else if (data.type === "pipeline_stats") {
        handlePipelineStats(data);
    } else if (data.type === "browser") {
        handleBrowserEvent(data);
    } else if (data.type === "complete") {
        state.lastResult = data.result;
        state.pipelineMode = false;
        addLogLine(
            data.result?.status === "stopped"
                ? "Agent stopped. Partial results are ready below."
                : "Agent execution complete.",
            data.result?.status === "stopped" ? "step" : "success",
        );
        if (state.selectedAgent?.ui_type === "seo_posting") {
            finalizeSeoWorkflow(data.result || {});
        }
        state.browser.event = "done";
        updateBrowserPreview();
        renderMain();
    } else if (data.type === "error") {
        addLogLine(`FATAL: ${data.message}`, "error");
        if (state.selectedAgent?.ui_type === "seo_posting") {
            handleSeoWorkflowEvent(data, "error");
        }
    } else if (data.type === "warning") {
        addLogLine(data.message, "warning");
        if (state.selectedAgent?.ui_type === "seo_posting") {
            handleSeoWorkflowEvent(data, "warning");
        }
    }
}

function handlePipelineStats(data) {
    state.pipelineMode = true;
    state.pipeline = data;
    updatePipelinePanel();
}

function handleBrowserEvent(data) {
    Object.assign(state.browser, data);
    if (data.event === "captcha_detected") {
        const wasActive = state.captcha.active;
        state.captcha.active = true;
        state.captcha.message = data.message || "CAPTCHA detected - action required";
        state.captcha.resolvedMessage = "";
        if (!wasActive) {
            playCaptchaAlertSound();
            renderMain();
        }
    } else if (data.event === "captcha_cleared") {
        state.captcha.active = false;
        state.captcha.resolvedMessage = data.message || "CAPTCHA cleared - resuming from the same row";
        renderMain();
    }
    updateBrowserPreview();
}

function classifyMessage(msg) {
    const lower = msg.toLowerCase();
    if (lower.includes("captcha"))
        return "warning";
    if (lower.includes("passed") || lower.includes("success") || lower.includes("saved") || lower.startsWith("done"))
        return "success";
    if (lower.includes("fail") || lower.includes("error") || lower.includes("fatal"))
        return "error";
    if (lower.includes("found:"))
        return "success";
    return "step";
}

function triggerSeoRun(agent, overrides = {}) {
    runAgent(agent.module_name, {
        method: "POST",
        body: {
            topic_override: state.seo.topicOverride.trim() || undefined,
            publish_override: overrides.publish_override || state.seo.publishOverride,
            enable_featured_image: overrides.enable_featured_image ?? state.seo.enableFeaturedImage,
            dry_run: overrides.dry_run ?? state.seo.dryRun,
        },
    });
}

function addLogLine(message, type = "step") {
    const now = new Date();
    const time = now.toLocaleTimeString("en-US", { hour12: false });
    state.executionLog.push({ time, message, type });

    const terminal = document.getElementById("terminal");
    if (terminal) {
        const cursor = terminal.querySelector(".terminal-cursor");
        const line = createTerminalLine({ time, message, type });
        if (cursor) terminal.insertBefore(line, cursor);
        else terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    }
}

// ---------------------------------------------------------------------------
// Browser Preview — live DOM updates
// ---------------------------------------------------------------------------
function updateBrowserPreview() {
    const urlBar = document.getElementById("browser-url");
    const statusEl = document.getElementById("browser-status");
    const content = document.getElementById("browser-content");
    if (!urlBar || !content) return;

    const b = state.browser;

    // Update URL bar
    urlBar.textContent = b.url || "about:blank";
    urlBar.title = b.url || "";

    // Update status dot
    if (statusEl) {
        const ev = b.event;
        if (ev === "navigate" || ev === "downloading" || ev === "extracting") {
            statusEl.innerHTML = '<span class="browser-status-dot loading"></span> Loading';
        } else if (ev === "captcha_detected") {
            statusEl.innerHTML = '<span class="browser-status-dot warning"></span> CAPTCHA';
        } else if (ev === "captcha_cleared") {
            statusEl.innerHTML = '<span class="browser-status-dot loading"></span> Resuming';
        } else if (ev === "contacts" && b.status === "found") {
            statusEl.innerHTML = '<span class="browser-status-dot found"></span> Found';
        } else if (ev === "no_pdf" || (ev === "contacts" && b.status !== "found")) {
            statusEl.innerHTML = '<span class="browser-status-dot not-found"></span> Not Found';
        } else if (ev === "pdf_found") {
            statusEl.innerHTML = '<span class="browser-status-dot found"></span> PDF Found';
        } else if (ev === "done") {
            statusEl.innerHTML = '<span class="browser-status-dot done"></span> Complete';
        } else {
            statusEl.innerHTML = '<span class="browser-status-dot idle"></span> Idle';
        }
    }

    // Update content area
    if (b.event === "idle") {
        content.innerHTML = `
            <div class="browser-idle-state">
                <div class="browser-idle-icon">&#x1F310;</div>
                <div class="browser-idle-text">Waiting for agent to start scraping...</div>
            </div>
        `;
    } else if (b.event === "captcha_detected") {
        content.innerHTML = `
            <div class="browser-page captcha-browser-state">
                <div class="captcha-browser-icon">&#9888;</div>
                <div class="captcha-browser-title">CAPTCHA detected</div>
                <div class="captcha-browser-text">Solve the challenge in the opened WIPO browser window. The agent will resume automatically from the same row.</div>
                <div class="captcha-browser-meta">Row ${esc(String(b.row || 0))}${b.patent_id ? ` • ${esc(b.patent_id)}` : ""}</div>
            </div>
        `;
    } else if (b.event === "captcha_cleared") {
        content.innerHTML = `
            <div class="browser-page captcha-browser-state">
                <div class="captcha-browser-icon">&#10003;</div>
                <div class="captcha-browser-title">CAPTCHA cleared</div>
                <div class="captcha-browser-text">Resume detected. The agent is continuing from the same row now.</div>
                <div class="captcha-browser-meta">Row ${esc(String(b.row || 0))}${b.patent_id ? ` • ${esc(b.patent_id)}` : ""}</div>
            </div>
        `;
    } else if (b.event === "navigate") {
        content.innerHTML = `
            <div class="browser-page">
                <div class="browser-loading-bar"></div>
                <div class="browser-patent-header">
                    <div class="browser-patent-id">${esc(b.patent_id)}</div>
                    <div class="browser-patent-title">${esc(b.title)}</div>
                    <div class="browser-patent-meta">
                        <span>${esc(b.applicant)}</span>
                        ${b.country ? `<span class="browser-country">${esc(b.country)}</span>` : ""}
                    </div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Documents</div>
                    <div class="browser-doc searching">
                        <span class="spinner-sm"></span> Searching for RO/101 or 306 PDF...
                    </div>
                </div>
                ${renderBrowserProgress(b)}
            </div>
        `;
    } else if (b.event === "pdf_found") {
        content.innerHTML = `
            <div class="browser-page">
                <div class="browser-patent-header">
                    <div class="browser-patent-id">${esc(b.patent_id)}</div>
                    <div class="browser-patent-title">${esc(b.title || state.browser.title)}</div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Documents</div>
                    <div class="browser-doc found-doc">
                        <span class="doc-icon">&#x1F4C4;</span>
                        <span>RO/101 or 306 PDF</span>
                        <span class="doc-status found">FOUND</span>
                    </div>
                    <div class="browser-doc downloading">
                        <span class="spinner-sm"></span> Downloading PDF...
                    </div>
                </div>
                ${renderBrowserProgress(b)}
            </div>
        `;
    } else if (b.event === "no_pdf") {
        content.innerHTML = `
            <div class="browser-page">
                <div class="browser-patent-header">
                    <div class="browser-patent-id">${esc(b.patent_id)}</div>
                    <div class="browser-patent-title">${esc(b.title || state.browser.title)}</div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Documents</div>
                    <div class="browser-doc not-found-doc">
                        <span class="doc-icon">&#x274C;</span>
                        <span>No RO/101 or 306 PDF found</span>
                        <span class="doc-status not-found">NOT FOUND</span>
                    </div>
                </div>
                ${renderBrowserProgress(b)}
            </div>
        `;
    } else if (b.event === "extracting") {
        content.innerHTML = `
            <div class="browser-page">
                <div class="browser-patent-header">
                    <div class="browser-patent-id">${esc(b.patent_id)}</div>
                    <div class="browser-patent-title">${esc(b.title || state.browser.title)}</div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Documents</div>
                    <div class="browser-doc found-doc">
                        <span class="doc-icon">&#x1F4C4;</span>
                        <span>PDF Downloaded</span>
                        <span class="doc-status found">OK</span>
                    </div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Contact Extraction</div>
                    <div class="browser-extracting">
                        <span class="spinner-sm"></span> Scanning PDF for emails, phones, names...
                    </div>
                </div>
                ${renderBrowserProgress(b)}
            </div>
        `;
    } else if (b.event === "contacts") {
        const hasContacts = b.emails.length > 0 || b.phones.length > 0;
        content.innerHTML = `
            <div class="browser-page">
                <div class="browser-patent-header">
                    <div class="browser-patent-id">${esc(b.patent_id)}</div>
                    <div class="browser-patent-title">${esc(b.title)}</div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Documents</div>
                    <div class="browser-doc found-doc">
                        <span class="doc-icon">&#x1F4C4;</span>
                        <span>PDF Processed</span>
                        <span class="doc-status found">OK</span>
                    </div>
                </div>
                <div class="browser-section">
                    <div class="browser-section-title">Extracted Contacts</div>
                    ${hasContacts ? `
                        ${b.emails.map(e => `<div class="contact-item email"><span class="contact-icon">&#x1F4E7;</span> ${esc(e)}</div>`).join("")}
                        ${b.phones.map(p => `<div class="contact-item phone"><span class="contact-icon">&#x1F4DE;</span> ${esc(p)}</div>`).join("")}
                        ${b.name ? `<div class="contact-item name"><span class="contact-icon">&#x1F464;</span> ${esc(b.name)}</div>` : ""}
                    ` : `
                        <div class="contact-none">No contacts found in this PDF</div>
                    `}
                </div>
                ${renderBrowserProgress(b)}
            </div>
        `;
    } else if (b.event === "done") {
        content.innerHTML = `
            <div class="browser-done-state">
                <div class="browser-done-icon">&#x2705;</div>
                <div class="browser-done-title">Scraping Complete</div>
                <div class="browser-done-stats">
                    <div class="browser-done-stat">
                        <span class="done-stat-value found">${b.found_count || 0}</span>
                        <span class="done-stat-label">Found</span>
                    </div>
                    <div class="browser-done-stat">
                        <span class="done-stat-value not-found">${b.not_found_count || 0}</span>
                        <span class="done-stat-label">Not Found</span>
                    </div>
                    <div class="browser-done-stat">
                        <span class="done-stat-value error">${b.error_count || 0}</span>
                        <span class="done-stat-label">Errors</span>
                    </div>
                </div>
            </div>
        `;
    }
}

function renderBrowserProgress(b) {
    if (!b.total) return "";
    const pct = Math.round((b.row / b.total) * 100);
    const fc = b.found_count || 0;
    const nfc = b.not_found_count || 0;
    const ec = b.error_count || 0;
    return `
        <div class="browser-progress">
            <div class="browser-progress-bar">
                <div class="browser-progress-fill" style="width:${pct}%"></div>
            </div>
            <div class="browser-progress-text">
                Row ${b.row} / ${b.total}
                <span class="browser-progress-stats">
                    <span class="bp-found">${fc} found</span>
                    <span class="bp-sep">|</span>
                    <span class="bp-not-found">${nfc} not found</span>
                    <span class="bp-sep">|</span>
                    <span class="bp-errors">${ec} errors</span>
                </span>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Pipeline Panel — live DOM updates for parallel mode
// ---------------------------------------------------------------------------
function updatePipelinePanel() {
    const panel = document.getElementById("pipeline-panel");
    if (!panel || !state.pipeline) return;

    const p = state.pipeline;
    const pct = p.total > 0 ? Math.round((p.completed / p.total) * 100) : 0;

    panel.innerHTML = `
        <div class="pipeline-header">
            <span class="pipeline-mode-badge">PIPELINE MODE</span>
            <span class="pipeline-workers">${p.browse_active || 0} browsers | ${p.ocr_active || 0} OCR</span>
        </div>
        <div class="pipeline-bar-wrap">
            <div class="pipeline-bar">
                <div class="pipeline-bar-fill" style="width:${pct}%"></div>
            </div>
            <div class="pipeline-bar-label">${p.completed} / ${p.total} (${pct}%)</div>
        </div>
        <div class="pipeline-metrics">
            <div class="pipeline-metric">
                <div class="pipeline-metric-value">${p.rows_per_minute || 0}</div>
                <div class="pipeline-metric-label">rows/min</div>
            </div>
            <div class="pipeline-metric">
                <div class="pipeline-metric-value">${formatETA(p.eta_minutes)}</div>
                <div class="pipeline-metric-label">ETA</div>
            </div>
            <div class="pipeline-metric">
                <div class="pipeline-metric-value success">${p.found || 0}</div>
                <div class="pipeline-metric-label">Found</div>
            </div>
            <div class="pipeline-metric">
                <div class="pipeline-metric-value warning">${p.not_found || 0}</div>
                <div class="pipeline-metric-label">Not Found</div>
            </div>
            <div class="pipeline-metric">
                <div class="pipeline-metric-value error">${p.errors || 0}</div>
                <div class="pipeline-metric-label">Errors</div>
            </div>
            <div class="pipeline-metric">
                <div class="pipeline-metric-value">${formatElapsed(p.elapsed_seconds)}</div>
                <div class="pipeline-metric-label">Elapsed</div>
            </div>
        </div>
        ${p.captcha_state === "cooldown" ? `
            <div class="captcha-warning">
                CAPTCHA cooldown — resuming in ${p.captcha_cooldown_remaining}s
            </div>
        ` : ""}
        ${p.skipped > 0 ? `
            <div class="pipeline-resume-info">${p.skipped} rows loaded from previous run (resume)</div>
        ` : ""}
    `;
}

function renderPipelineSection() {
    return `
        <div class="pipeline-section">
            <div class="section-title">Pipeline Progress</div>
            <div class="pipeline-panel" id="pipeline-panel">
                <div class="pipeline-idle">Pipeline starting...</div>
            </div>
        </div>
    `;
}

function formatETA(minutes) {
    if (!minutes || minutes <= 0) return "--";
    if (minutes < 1) return "<1m";
    if (minutes < 60) return Math.round(minutes) + "m";
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return h + "h " + m + "m";
}

function formatElapsed(seconds) {
    if (!seconds) return "0s";
    if (seconds < 60) return Math.round(seconds) + "s";
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (m < 60) return m + "m " + s + "s";
    const h = Math.floor(m / 60);
    return h + "h " + (m % 60) + "m";
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function render() {
    renderSidebar();
    renderMain();
}

function renderSidebar() {
    const countEl = document.getElementById("agent-count");
    const listEl = document.getElementById("agent-list");
    countEl.textContent = state.agents.length;

    listEl.innerHTML = "";
    if (state.agents.length === 0) {
        listEl.innerHTML = `<p style="padding:20px;color:var(--text-muted);font-size:13px;text-align:center">No agents found</p>`;
        return;
    }

    const groups = new Map();
    state.agents.forEach((agent) => {
        const groupName = agent.group || "Agents";
        if (!groups.has(groupName)) groups.set(groupName, []);
        groups.get(groupName).push(agent);
    });

    groups.forEach((agents, groupName) => {
        const groupEl = document.createElement("div");
        groupEl.className = "agent-group";
        groupEl.innerHTML = `<div class="agent-group-title">${esc(groupName)}</div>`;

        const itemsEl = document.createElement("div");
        itemsEl.className = "agent-group-items";

        agents.forEach((agent) => {
            const isSelected =
                state.selectedAgent &&
                state.selectedAgent.module_name === agent.module_name;
            const statusClass =
                agent.status === "active" ? "active" : agent.status === "error" ? "error" : "idle";
            const subAgents = agent.sub_agents || [];

            const item = document.createElement("div");
            item.className = `agent-item ${isSelected ? "active" : ""}`;
            item.innerHTML = `
                <span class="agent-dot ${statusClass}"></span>
                <div class="agent-item-info">
                    <div class="agent-item-name">${esc(agent.name || agent.module_name)}</div>
                    <div class="agent-item-role">${esc(agent.role || "")}${subAgents.length ? ` · ${subAgents.length} sub-agents` : ""}</div>
                </div>
            `;
            item.onclick = async () => {
                const detail = await loadAgentDetail(agent.module_name);
                state.selectedAgent = detail || agent;
                state.executionLog = [];
                state.lastResult = null;
                state.inputMode = "upload";
                state.uploadedFilePath = null;
                state.pipelineMode = false;
                state.pipeline = null;
                resetCaptchaAlert();
                state.browser.event = "idle";
                await loadAgentRunStatus(agent.module_name);
                if ((detail || agent).ui_type === "seo_posting") {
                    state.seoDashboard.previewArticle = null;
                    state.seoDashboard.historyEntry = null;
                    await loadSeoDashboardData(agent.module_name);
                } else {
                    state.seoDashboard.snapshot = null;
                    state.seoDashboard.error = "";
                    state.seoDashboard.previewArticle = null;
                    state.seoDashboard.historyEntry = null;
                    resetSeoWorkflow([]);
                }
                render();
            };
            itemsEl.appendChild(item);
        });

        groupEl.appendChild(itemsEl);
        listEl.appendChild(groupEl);
    });
}

function renderMain() {
    const main = document.getElementById("main-content");

    if (!state.selectedAgent) {
        main.innerHTML = `
            <div class="welcome">
                <div class="welcome-icon">&#x1F441;&#xFE0F;</div>
                <h2>Virtual Office</h2>
                <p>Select an agent from the sidebar to monitor its activity, run it, and inspect results in real-time.</p>
            </div>
        `;
        return;
    }

    const agent = state.selectedAgent;
    const memory = agent.memory || {};
    const stats = memory.stats || agent.stats || {};
    const learnings = memory.learnings || [];
    const rate = stats.success_rate || 0;
    const rateClass = rate >= 0.8 ? "success" : rate >= 0.5 ? "warning" : rate > 0 ? "error" : "";
    const subAgents = agent.sub_agents || [];
    const isPCTAgent = agent.module_name === "pct_agent";
    const isSeoAgent = agent.ui_type === "seo_posting";

    let html = `
        <!-- Agent Header -->
        <div class="agent-header">
            <h2>${esc(agent.name || agent.module_name)}</h2>
            <p class="agent-desc">${esc(agent.description || "")}</p>
            <div class="agent-badges">
                <span class="badge badge-role">${esc(agent.role || "Agent")}</span>
                <span class="badge badge-version">v${esc(agent.version || "1.0")}</span>
                ${agent.status === "active" ? '<span class="badge badge-active">Active</span>' : ""}
                ${state.agentRunStatus === "running" ? '<span class="badge badge-running">Running</span>' : ""}
                ${state.agentRunStatus === "stopping" ? '<span class="badge badge-warning">Stopping</span>' : ""}
                ${agent.requires_llm === false ? '<span class="badge badge-version">No LLM Required</span>' : ""}
                ${agent.accepts_upload ? '<span class="badge badge-role">Accepts Upload</span>' : ""}
            </div>
        </div>

        <!-- Sub-agents -->
        ${subAgents.length ? `
        <div class="sub-agents-row">
            <div class="section-title">Sub-Agents</div>
            <div class="sub-agents-list">
                ${subAgents.map((s) => `<span class="sub-agent-chip">${esc(s)}</span>`).join("")}
            </div>
        </div>
        ` : ""}

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${stats.total_runs || 0}</div>
                <div class="stat-label">Total Runs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value ${rateClass}">${formatPercent(rate)}</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${(stats.avg_execution_time || 0).toFixed(2)}s</div>
                <div class="stat-label">Avg Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="font-size:18px;color:var(--success)">${(agent.status || "idle").toUpperCase()}</div>
                <div class="stat-label">Status</div>
            </div>
        </div>
    `;

    if (isSeoAgent) {
        html += renderSEOOverviewSection();
    }

    if (isPCTAgent && state.captcha.active) {
        html += `
            <div class="captcha-alert-modal">
                <div class="captcha-alert-modal-card">
                    <div class="captcha-alert-modal-title">CAPTCHA detected</div>
                    <div class="captcha-alert-modal-text">Action required in the WIPO browser window. The agent is paused and watching for the CAPTCHA to be cleared.</div>
                </div>
            </div>
            <div class="captcha-alert-banner">
                <div class="captcha-alert-title">CAPTCHA detected - action required</div>
                <div class="captcha-alert-text">Solve the CAPTCHA in the opened WIPO browser window. Processing is paused and will resume automatically from the same row.</div>
            </div>
        `;
    } else if (isPCTAgent && state.captcha.resolvedMessage) {
        html += `
            <div class="captcha-alert-resolved">${esc(state.captcha.resolvedMessage)}</div>
        `;
    }

    // --- Input section ---
    if (isSeoAgent) {
        html += renderSEOInputSection(agent);
    } else if (agent.accepts_upload) {
        html += renderUploadSection(agent);
    } else {
        html += renderSimpleRunSection();
    }

    // --- Pipeline progress panel (shown in pipeline mode) ---
    if (isPCTAgent && (state.pipelineMode || (state.isRunning && state.pipeline))) {
        html += renderPipelineSection();
    }

    // --- Execution Log + Browser Preview (side by side) ---
    html += `
        <div class="execution-split">
            <div class="execution-log-panel${state.pipelineMode || !isPCTAgent ? " full-width" : ""}">
                <div class="section-title">Execution Log</div>
                <div class="terminal" id="terminal">
                    ${state.executionLog.length === 0 && !state.isRunning
                        ? '<span class="terminal-empty">Configure input above and click "Run Agent" to start...</span>'
                        : ""}
                    ${state.executionLog.map((l) => createTerminalLineHTML(l)).join("")}
                    ${state.isRunning ? '<span class="terminal-cursor"></span>' : ""}
                </div>
            </div>
            ${isPCTAgent && !state.pipelineMode ? `
            <div class="browser-preview-panel">
                <div class="section-title">Scraping Browser</div>
                <div class="browser-frame">
                    <div class="browser-toolbar">
                        <div class="browser-dots">
                            <span class="dot red"></span>
                            <span class="dot yellow"></span>
                            <span class="dot green"></span>
                        </div>
                        <div class="browser-url-bar" id="browser-url">about:blank</div>
                        <div class="browser-status-indicator" id="browser-status">
                            <span class="browser-status-dot idle"></span> Idle
                        </div>
                    </div>
                    <div class="browser-content" id="browser-content">
                        <div class="browser-idle-state">
                            <div class="browser-idle-icon">&#x1F310;</div>
                            <div class="browser-idle-text">Waiting for agent to start scraping...</div>
                        </div>
                    </div>
                </div>
            </div>
            ` : ""}
        </div>
    `;

    // --- Results ---
    if (state.lastResult) {
        if (isPCTAgent) {
            html += renderPCTResults(state.lastResult);
        } else if (isSeoAgent) {
            html += renderSEOResults(state.lastResult);
        } else if (state.lastResult.status === "failure") {
            html += renderFailureResults(state.lastResult);
        }
    }

    // --- Memory ---
    html += renderMemorySection(learnings);

    // --- Raw JSON ---
    if (state.lastResult) {
        html += `
            <button class="json-toggle" onclick="toggleJSON()">Show Raw JSON</button>
            <div id="json-output" class="json-block" style="display:none">${esc(JSON.stringify(state.lastResult, null, 2))}</div>
        `;
    }

    if (isSeoAgent && state.seoDashboard.previewArticle) {
        html += renderSEOPreviewModal(state.seoDashboard.previewArticle);
    }

    if (isSeoAgent && state.seoDashboard.historyEntry) {
        html += renderSEOHistoryModal(state.seoDashboard.historyEntry);
    }

    main.innerHTML = html;
    attachHandlers(agent);
}

// ---------------------------------------------------------------------------
// Agent-specific input sections
// ---------------------------------------------------------------------------
function renderUploadSection(agent) {
    const uploaded = state.uploadedFilePath;
    const types = (agent.upload_types || []).join(",");
    const isUploadMode = state.inputMode === "upload";
    const wipoOptions = state.wipoGazettes.map((option) => `
        <option value="${esc(option.value)}" ${option.value === state.selectedGazette ? "selected" : ""}>
            ${esc(option.label)}
        </option>
    `).join("");

    return `
        <div class="input-section">
            <div class="section-title">Input</div>
            <div class="input-card">
                <!-- Mode selector -->
                <div class="input-row">
                    <label class="input-label">Mode</label>
                    <div class="mode-tabs" id="mode-tabs">
                        <button type="button" class="mode-tab ${isUploadMode ? "active" : ""}" data-mode="upload">Upload Excel</button>
                        <button type="button" class="mode-tab ${!isUploadMode ? "active" : ""}" data-mode="wipo_download">Download from WIPO</button>
                    </div>
                </div>

                <!-- Upload area -->
                <div id="upload-area" class="upload-zone" style="display:${isUploadMode ? "block" : "none"}">
                    <div class="upload-dropzone" id="dropzone">
                        ${uploaded
                            ? `<div class="upload-done">
                                    <span class="upload-done-icon">&#x2713;</span>
                                    <span class="upload-done-name">${esc(uploaded.split(/[\\/]/).pop())}</span>
                                    <button type="button" class="upload-clear" id="clear-upload">&#x2715;</button>
                               </div>`
                            : `<div class="upload-prompt">
                                    <span class="upload-icon">&#x1F4C4;</span>
                                    <span>Drop Excel file here or <label for="file-input" class="upload-link">browse</label></span>
                                    <span class="upload-hint">${types || ".xlsx, .xls"}</span>
                               </div>`
                        }
                        <input type="file" id="file-input" accept="${types}" style="display:none">
                    </div>
                </div>

                <!-- WIPO area -->
                <div id="wipo-area" style="display:${isUploadMode ? "none" : "block"}">
                    <div class="wipo-info">
                        <span class="wipo-icon">&#x1F310;</span>
                        <div>
                            <div class="wipo-title">WIPO PatentScope Weekly Browse</div>
                            <div class="wipo-url">patentscope.wipo.int/search/en/resultWeeklyBrowse.jsf</div>
                        </div>
                    </div>
                    <div class="input-row">
                        <label class="input-label" for="wipo-gazette-select">Gazette Week</label>
                        <div class="wipo-controls">
                            <select
                                id="wipo-gazette-select"
                                class="wipo-select"
                                ${state.wipoGazettesLoading ? "disabled" : ""}
                            >
                                ${state.wipoGazettesLoading
                                    ? '<option value="">Loading WIPO weeks...</option>'
                                    : state.wipoGazettes.length
                                        ? wipoOptions
                                        : '<option value="">No WIPO weeks available</option>'
                                }
                            </select>
                            <button
                                type="button"
                                class="wipo-refresh"
                                id="refresh-wipo-gazettes"
                                ${state.wipoGazettesLoading ? "disabled" : ""}
                            >
                                Refresh
                            </button>
                        </div>
                        <div class="input-help">
                            Pick the WIPO weekly gazette you want the agent to download before processing.
                        </div>
                        ${state.wipoGazettesError
                            ? `<div class="input-error">${esc(state.wipoGazettesError)}</div>`
                            : ""
                        }
                    </div>
                </div>

                <!-- Run -->
                <div class="run-actions">
                    <button type="button" class="run-btn" id="run-btn" ${(state.isRunning || state.agentRunStatus !== "idle") ? "disabled" : ""}>
                        ${state.isRunning
                            ? '<span class="spinner"></span> Processing...'
                            : "&#x25B6;&nbsp;&nbsp;Run PCT Agent"}
                    </button>
                    <button type="button" class="stop-btn" id="stop-btn" ${(state.isRunning || state.agentRunStatus === "running" || state.agentRunStatus === "stopping") ? "" : "disabled"}>
                        ${state.stopRequested ? "Stopping..." : "Stop"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderSEOInputSection(agent) {
    const seo = state.seo;
    const todayRun = state.seoDashboard.snapshot?.todayRun || {};
    const selectedTopic = seo.topicOverride || todayRun.selectedTopic || "Waiting for dynamic topic discovery";
    const targetKeyword = todayRun.targetKeyword || seo.topicOverride || "Will be chosen from topic research";
    const secondaryKeywords = todayRun.secondaryKeywords || [];
    const sourceMix = todayRun.sourceMix || [];
    return `
        <div class="input-section">
            <div class="section-title">Today’s SEO Run</div>
            <div class="input-card seo-input-card">
                <div class="seo-panel-grid seo-run-summary-grid">
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Selected Topic</div>
                        <div class="seo-run-summary-value">${esc(selectedTopic)}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Target Keyword</div>
                        <div class="seo-run-summary-value">${esc(targetKeyword)}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Content Type</div>
                        <div class="seo-run-summary-value">${esc(todayRun.contentType || "SEO Blog Article")}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Target Audience</div>
                        <div class="seo-run-summary-value">${esc(todayRun.targetAudience || "Founders, inventors, and businesses")}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Source Mix</div>
                        <div class="seo-run-summary-value">${esc(sourceMix.length ? sourceMix.join(", ") : "Live topic sources pending")}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Confidence / Freshness</div>
                        <div class="seo-run-summary-value">${esc(`${todayRun.confidenceScore ?? "-"} / ${todayRun.freshnessLevel || "Pending"}`)}</div>
                    </div>
                </div>

                <div class="input-row">
                    <label class="input-label" for="seo-topic-override">Topic Override</label>
                    <input
                        id="seo-topic-override"
                        class="text-input"
                        type="text"
                        placeholder="Leave blank to use live Search Console, SerpAPI, and competitor topic discovery"
                        value="${esc(seo.topicOverride)}"
                    />
                    <div class="input-help">
                        Optional: force a specific topic for this run. Otherwise the agent will choose from live demand signals and competitor-topic discovery.
                    </div>
                </div>

                <div class="seo-chip-list">
                    ${secondaryKeywords.length
                        ? secondaryKeywords.map((keyword) => `<span class="sub-agent-chip">${esc(keyword)}</span>`).join("")
                        : '<span class="sub-agent-chip">Secondary keywords will appear after research</span>'}
                </div>

                <div class="seo-grid">
                    <div class="input-row">
                        <label class="input-label" for="seo-publish-override">Publish Mode</label>
                        <select id="seo-publish-override" class="wipo-select">
                            <option value="draft" ${seo.publishOverride === "draft" ? "selected" : ""}>Draft</option>
                            <option value="publish" ${seo.publishOverride === "publish" ? "selected" : ""}>Publish Immediately</option>
                        </select>
                        <div class="input-help">
                            Draft is safest. Publish only when you want this run to go live if validation passes.
                        </div>
                    </div>

                    <div class="input-row seo-toggles">
                        <label class="toggle-row">
                            <input id="seo-featured-image" type="checkbox" ${seo.enableFeaturedImage ? "checked" : ""}>
                            <span>Generate featured image</span>
                        </label>
                        <label class="toggle-row">
                            <input id="seo-dry-run" type="checkbox" ${seo.dryRun ? "checked" : ""}>
                            <span>Dry run only</span>
                        </label>
                        <div class="input-help">
                            Dry run skips WordPress publishing and lets you validate the topic, SEO metadata, and article structure safely.
                        </div>
                    </div>
                </div>

                <div class="seo-agent-note">
                    <div class="seo-note-title">${esc(agent.name || "SEO Posting Agent")}</div>
                    <div class="seo-note-text">Daily flow: topic research, outline, article generation, SEO validation, internal links, featured image, WordPress draft or publish, and duplicate-safe topic ledger updates.</div>
                </div>

                <div class="run-actions">
                    <button type="button" class="run-btn" id="run-btn" ${(state.isRunning || state.agentRunStatus !== "idle") ? "disabled" : ""}>
                        ${state.isRunning
                            ? '<span class="spinner"></span> Running SEO workflow...'
                            : "&#x25B6;&nbsp;&nbsp;Run SEO Posting Agent"}
                    </button>
                    <button type="button" class="run-btn secondary-run-btn" id="seo-save-draft-btn" ${(state.isRunning || state.agentRunStatus !== "idle") ? "disabled" : ""}>
                        Save as Draft
                    </button>
                    <button type="button" class="run-btn secondary-run-btn" id="seo-publish-now-btn" ${(state.isRunning || state.agentRunStatus !== "idle") ? "disabled" : ""}>
                        Publish Immediately
                    </button>
                    <button type="button" class="stop-btn" id="stop-btn" ${(state.isRunning || state.agentRunStatus === "running" || state.agentRunStatus === "stopping") ? "" : "disabled"}>
                        ${state.stopRequested ? "Stopping..." : "Stop"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderSEOOverviewSection() {
    const dashboard = state.seoDashboard;
    const snapshot = dashboard.snapshot;
    const seo = state.seo;

    if (dashboard.loading && !snapshot) {
        return `
            <div class="result-card seo-dashboard-shell">
                <h4>SEO Posting Agent Dashboard</h4>
                <div class="memory-empty">Loading PatentZoom SEO control data...</div>
            </div>
        `;
    }

    if (dashboard.error && !snapshot) {
        return `
            <div class="result-card seo-dashboard-shell">
                <h4>SEO Posting Agent Dashboard</h4>
                <div class="error-banner">&#x26A0; ${esc(dashboard.error)}</div>
            </div>
        `;
    }

    if (!snapshot) return "";

    const summary = snapshot.summary || {};
    const readiness = snapshot.readiness || [];
    const nextActions = snapshot.nextActions || [];
    const topicDiscovery = snapshot.topicDiscovery || {};
    const recentTopics = snapshot.recentTopics || [];
    const recentRuns = snapshot.recentRuns || [];
    const overview = snapshot.overview || {};
    const topicRadar = snapshot.topicRadar || {};
    const articleManager = snapshot.articleManager || [];
    const articlePreview = snapshot.articlePreview || {};
    const seoChecklist = snapshot.seoChecklist || [];
    const internalLinking = snapshot.internalLinking || {};
    const automationSettings = snapshot.automationSettings || [];
    const wordpressMonitor = snapshot.wordpressMonitor || {};
    const seoPerformance = snapshot.seoPerformance || [];
    const logsHistory = snapshot.logsHistory || [];
    const topKeywords = overview.topKeywords || [];
    const liveSignals = snapshot.liveSignals || [];
    const rejectedTopics = snapshot.rejectedTopics || [];
    const selectedTopic = topicDiscovery.selectedTopic || {};

    return `
        <div class="seo-dashboard-shell">
            <div class="section-title">SEO Posting Agent Dashboard</div>

            <div class="seo-overview-grid seo-overview-grid-wide">
                <div class="stat-card">
                    <div class="stat-value ${overview.publishedToday ? "success" : "warning"}">${overview.publishedToday ? "Yes" : "No"}</div>
                    <div class="stat-label">Published Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">${overview.monthlyArticlesPublished || 0} / ${overview.monthlyTarget || 30}</div>
                    <div class="stat-label">Monthly Articles Published</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${overview.successRate || 0}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${overview.seoScore || 0}</div>
                    <div class="stat-label">Average SEO Score</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value ${String(overview.wordpressStatus || "").toLowerCase().includes("connected") ? "success" : "error"}" style="font-size:18px">${esc(overview.wordpressStatus || "Pending")}</div>
                    <div class="stat-label">WordPress Status</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="font-size:18px">${overview.lastPublishedDate ? esc(overview.lastPublishedDate) : "Pending"}</div>
                    <div class="stat-label">Last Published Date</div>
                </div>
            </div>

            <div class="seo-panel-grid">
                <div class="result-card">
                    <div class="seo-card-header">
                        <h4>Overview</h4>
                        <span class="seo-kicker">${esc((summary.lastRunStatus || "never").toUpperCase())}</span>
                    </div>
                    <div class="seo-inline-metrics">
                        <div><strong>Tracked Topics:</strong> ${summary.totalTopics || 0}</div>
                        <div><strong>Recent Runs:</strong> ${summary.recentRunCount || 0}</div>
                        <div><strong>Auto Publish:</strong> ${summary.autoPublish ? "On" : "Off"}</div>
                    </div>
                    <div class="seo-chip-list">
                        ${topKeywords.length
                            ? topKeywords.map((item) => `<span class="sub-agent-chip">${esc(item.keyword)} · ${esc(String(item.count))}</span>`).join("")
                            : '<span class="sub-agent-chip">No keyword history yet</span>'}
                    </div>
                </div>

                <div class="result-card">
                    <div class="seo-card-header">
                        <h4>Service Readiness</h4>
                        <button type="button" class="json-toggle" id="seo-refresh-overview">Refresh</button>
                    </div>
                    <div class="seo-status-list">
                        ${readiness.map((item) => `
                            <div class="seo-status-item">
                                <div>
                                    <div class="seo-status-name">${esc(item.label)}</div>
                                    <div class="seo-status-detail">${esc(item.detail || "")}</div>
                                </div>
                                <span class="seo-status-pill ${item.ready ? "ready" : "blocked"}">${item.ready ? "Ready" : "Needs action"}</span>
                            </div>
                        `).join("")}
                    </div>
                </div>
            </div>

            <div class="seo-panel-grid">
                <div class="result-card">
                    <h4>Topic Radar</h4>
                    <div class="seo-slot-title">${esc(selectedTopic.title || selectedTopic.primaryKeyword || "Dynamic discovery pending")}</div>
                    <div class="seo-slot-meta">${esc(selectedTopic.theme || selectedTopic.intentCluster || "Patent-adjacent discovery")}</div>
                    <div class="seo-slot-cluster">Mode: ${esc(topicRadar.mode || "mixed_signal_dynamic")} â€¢ Snapshot: ${esc(topicRadar.generatedAt || "Pending")}</div>
                    <div class="seo-chip-list">
                        ${((selectedTopic.sourceTypes || []).length
                            ? (selectedTopic.sourceTypes || []).map((source) => `<span class="sub-agent-chip">${esc(source)}</span>`).join("")
                            : '<span class="sub-agent-chip">Waiting for live sources</span>')}
                    </div>
                    <div class="seo-seed-list">
                        <div class="seo-seed-item"><strong>Primary keyword:</strong> ${esc(selectedTopic.primaryKeyword || "-")}</div>
                        <div class="seo-seed-item"><strong>Demand / Freshness:</strong> ${esc(`${selectedTopic.demandScore ?? "-"} / ${selectedTopic.freshnessScore ?? "-"}`)}</div>
                        <div class="seo-seed-item"><strong>Why this topic was chosen:</strong> ${esc((selectedTopic.sourceEvidence || []).slice(0, 3).join(" | ") || "Live signal evidence will appear after discovery.")}</div>
                    </div>
                </div>

                <div class="result-card">
                    <h4>Dynamic Shortlist</h4>
                    <div class="seo-table-wrap">
                        <table class="results-table seo-mini-table">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>Topic</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${(topicRadar.queue || []).map((item) => `
                                    <tr>
                                        <td>${esc(String(item.rank || "-"))}</td>
                                        <td>
                                            <div class="seo-table-title">${esc(item.primaryKeyword || item.theme || "-")}</div>
                                            <div class="seo-table-subtitle">${esc([item.intentCluster, item.sourceMix].filter(Boolean).join(" â€¢ "))}</div>
                                        </td>
                                        <td><span class="status-pill ${String(item.status || "").toLowerCase() === "selected" ? "status-found" : "status-not_found"}">${esc(item.status || "-")}</span></td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="seo-panel-grid">
                <div class="result-card">
                    <h4>Live Signals</h4>
                    <div class="seo-table-wrap">
                        <table class="results-table seo-mini-table">
                            <thead>
                                <tr>
                                    <th>Source</th>
                                    <th>Signal</th>
                                    <th>Intent</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${liveSignals.length
                                    ? liveSignals.slice(0, 8).map((item) => `
                                        <tr>
                                            <td>${esc(item.sourceType || "-")}</td>
                                            <td>
                                                <div class="seo-table-title">${esc(item.keyword || item.title || "-")}</div>
                                                <div class="seo-table-subtitle">${esc(item.evidence || "")}</div>
                                            </td>
                                            <td>${esc(item.intentCluster || "-")}</td>
                                        </tr>
                                    `).join("")
                                    : '<tr><td colspan="3">No live signals captured yet.</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="result-card">
                    <h4>Rejected Topics</h4>
                    <div class="seo-table-wrap">
                        <table class="results-table seo-mini-table">
                            <thead>
                                <tr>
                                    <th>Topic</th>
                                    <th>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rejectedTopics.length
                                    ? rejectedTopics.slice(0, 8).map((item) => `
                                        <tr>
                                            <td>
                                                <div class="seo-table-title">${esc(item.title || item.primaryKeyword || "-")}</div>
                                                <div class="seo-table-subtitle">${esc(item.intentCluster || "")}</div>
                                            </td>
                                            <td>${esc(item.reason || "Filtered out")}</td>
                                        </tr>
                                    `).join("")
                                    : '<tr><td colspan="2">No rejected topics in the current snapshot.</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="result-card">
                <h4>AI Content Pipeline</h4>
                <div class="seo-stage-grid">
                    ${(dashboard.workflow.stages || []).map((stage, index) => `
                        <div class="seo-stage-card seo-stage-${stage.status}">
                            <div class="seo-stage-index">0${index + 1}</div>
                            <div class="seo-stage-name">${esc(stage.label)}</div>
                            <div class="seo-stage-desc">${esc(stage.detail || stage.description || "")}</div>
                        </div>
                    `).join("")}
                </div>
                <div class="seo-stage-current">
                    ${dashboard.workflow.currentMessage
                        ? `Current activity: ${esc(dashboard.workflow.currentMessage)}`
                        : "Current activity: waiting for a new SEO run"}
                </div>
            </div>

            <div class="result-card">
                <div class="seo-card-header">
                    <h4>Article Manager</h4>
                    <span class="seo-kicker">${articleManager.length} records</span>
                </div>
                ${articleManager.length
                    ? `<div class="seo-table-wrap">
                        <table class="results-table seo-mini-table">
                            <thead>
                                <tr>
                                    <th>Article title</th>
                                    <th>SEO score</th>
                                    <th>Keywords</th>
                                    <th>Slug</th>
                                    <th>Meta description</th>
                                    <th>Publish status</th>
                                    <th>Indexing</th>
                                    <th>Preview</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${articleManager.map((item) => `
                                    <tr>
                                        <td>${esc(item.title || "-")}</td>
                                        <td>${item.seoScore ?? "-"}</td>
                                        <td>${esc(item.primaryKeyword || "-")}</td>
                                        <td>${esc(item.slug || "-")}</td>
                                        <td title="${esc(item.metaDescription || "-")}">${esc(item.metaDescription || "-")}</td>
                                        <td><span class="status-pill ${String(item.publishStatus || "").toLowerCase() === "publish" ? "status-found" : "status-not_found"}">${esc(item.publishStatus || "-")}</span></td>
                                        <td>${esc(item.indexingStatus || "Pending")}</td>
                                        <td>${item.previewHtml ? `<button type="button" class="json-toggle seo-preview-btn" data-article-id="${esc(item.id)}">Preview</button>` : "-"}</td>
                                        <td>${String(item.publishStatus || "").toLowerCase() === "publish" && item.url ? `<button type="button" class="json-toggle seo-request-indexing-btn" data-url="${esc(item.url)}">Request Indexing</button>` : "-"}</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>`
                    : '<div class="memory-empty">No generated articles yet. Run the SEO workflow to populate this manager.</div>'}
            </div>

            <div class="seo-panel-grid seo-preview-check-grid">
                <div class="result-card">
                    <h4>Article Preview</h4>
                    ${articlePreview.title
                        ? `
                            <div class="seo-preview-meta">
                                <div><strong>Article Title:</strong> ${esc(articlePreview.title || "-")}</div>
                                <div><strong>Slug:</strong> ${esc(articlePreview.slug || "-")}</div>
                                <div><strong>Focus Keyword:</strong> ${esc(articlePreview.focusKeyword || "-")}</div>
                                <div><strong>Word Count:</strong> ${esc(String(articlePreview.wordCount || 0))}</div>
                                <div><strong>Category:</strong> ${esc(articlePreview.category || "-")}</div>
                                <div><strong>Author:</strong> ${esc(articlePreview.author || "-")}</div>
                                <div><strong>Status:</strong> ${esc(articlePreview.status || "-")}</div>
                                <div><strong>SEO Score:</strong> ${articlePreview.seoScore ?? "-"}</div>
                            </div>
                            <div class="seo-featured-image-shell">
                                <div class="seo-featured-image-label">Featured Image Preview</div>
                                ${articlePreview.featuredImagePreview
                                    ? `<img class="seo-featured-image-preview" src="${esc(articlePreview.featuredImagePreview)}" alt="Featured preview">`
                                    : `<div class="seo-featured-image-placeholder">Image preview will appear here after generation and upload.</div>`}
                            </div>
                            <div class="seo-preview-description"><strong>Meta Title:</strong> ${esc(articlePreview.metaTitle || "-")}</div>
                            <div class="seo-preview-description"><strong>Meta Description:</strong> ${esc(articlePreview.metaDescription || "-")}</div>
                            ${articlePreview.wordpressUrl ? `<div class="seo-preview-description"><strong>WordPress URL:</strong> <a class="result-link" href="${esc(articlePreview.wordpressUrl)}" target="_blank" rel="noopener noreferrer">${esc(articlePreview.wordpressUrl)}</a></div>` : ""}
                            <div class="seo-preview-body">${articlePreview.previewHtml || "<p>No preview content available.</p>"}</div>
                        `
                        : '<div class="memory-empty">No article generated yet. This panel will show the latest title, slug, metadata, preview, and WordPress URL.</div>'}
                </div>

                <div class="result-card">
                    <h4>SEO Validation Checklist</h4>
                    ${seoChecklist.length
                        ? `<div class="seo-checklist">
                            ${seoChecklist.map((item) => `
                                <div class="seo-check-item ${item.passed ? "passed" : "failed"}">
                                    <span class="seo-check-icon">${item.passed ? "✓" : "✕"}</span>
                                    <span>${esc(item.label || "")}</span>
                                    <span class="seo-check-status">${item.passed ? "Passed" : "Failed"}</span>
                                </div>
                            `).join("")}
                        </div>`
                        : '<div class="memory-empty">Validation checks will appear after an article is generated.</div>'}
                </div>
            </div>

            <div class="seo-panel-grid">
                <div class="result-card">
                    <h4>Internal Linking Engine</h4>
                    <div class="seo-slot-cluster">${esc(internalLinking.note || "")}</div>
                    <div class="seo-run-list">
                        ${(internalLinking.suggestions || []).map((item) => `
                            <div class="seo-run-item">
                                <div class="seo-run-title">${esc(item.title || "-")}</div>
                                <div class="seo-run-meta">
                                    <span>Relevance: ${esc(String(item.score ?? 0))}</span>
                                    <span>Slug: ${esc(item.slug || "-")}</span>
                                </div>
                                ${item.url ? `<a class="result-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.url)}</a>` : ""}
                            </div>
                        `).join("") || '<div class="memory-empty">No internal link suggestions available yet.</div>'}
                    </div>
                </div>

                <div class="result-card">
                    <h4>Automation Settings</h4>
                    <div class="seo-status-list">
                        ${automationSettings.map((item) => `
                            <div class="seo-status-item">
                                <div>
                                    <div class="seo-status-name">${esc(item.label)}</div>
                                    <div class="seo-status-detail">${item.kind === "service" ? "Integration health check" : item.kind === "setting" ? "Default publishing configuration" : "Environment toggle for this automation"}</div>
                                </div>
                                <span class="seo-status-pill ${item.enabled ? "ready" : "blocked"}">${item.enabled ? "Enabled" : "Disabled"}</span>
                            </div>
                        `).join("")}
                    </div>
                    <div class="seo-google-connect">
                        <div class="seo-card-header">
                            <h4>Google Search Console</h4>
                            <span class="seo-status-pill ${seo.google.connected ? "ready" : "blocked"}">${seo.google.connected ? "Connected" : "Not Connected"}</span>
                        </div>
                        <div class="input-row">
                            <label class="input-label" for="seo-google-client-id">OAuth Client ID</label>
                            <input id="seo-google-client-id" class="text-input" type="text" placeholder="Paste Google OAuth web client ID" value="${esc(seo.google.clientId)}" />
                        </div>
                        <div class="input-row">
                            <label class="input-label" for="seo-google-client-secret">OAuth Client Secret</label>
                            <input id="seo-google-client-secret" class="text-input" type="password" placeholder="Paste Google OAuth web client secret" value="${esc(seo.google.clientSecret)}" />
                        </div>
                        <div class="input-row">
                            <label class="input-label" for="seo-google-property">Search Console Property</label>
                            <input id="seo-google-property" class="text-input" type="text" placeholder="sc-domain:patentzoom.us" value="${esc(seo.google.property)}" />
                            <div class="input-help">Use your existing property. For PatentZoom the best option is <code>sc-domain:patentzoom.us</code>.</div>
                        </div>
                        <div class="seo-preview-description"><strong>Redirect URI:</strong> ${esc(seo.google.redirectUri || "http://127.0.0.1:8000/api/google/search-console/callback")}</div>
                        <div class="run-actions">
                            <button type="button" class="run-btn secondary-run-btn" id="seo-google-save-btn">Save Google OAuth</button>
                            <button type="button" class="run-btn secondary-run-btn" id="seo-google-connect-btn" ${seo.google.clientConfigured ? "" : "disabled"}>Connect Google Search Console</button>
                            <button type="button" class="run-btn secondary-run-btn" id="seo-google-browser-btn">Connect Browser Session</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="seo-panel-grid">
                <div class="result-card">
                    <h4>WordPress Publishing Monitor</h4>
                    <div class="seo-status-list">
                        <div class="seo-status-item">
                            <div>
                                <div class="seo-status-name">WordPress Connection Status</div>
                                <div class="seo-status-detail">${esc(wordpressMonitor.websiteUrl || "https://patentzoom.us")}</div>
                            </div>
                            <span class="seo-status-pill ${String(wordpressMonitor.connectionStatus || "").toLowerCase().includes("connected") ? "ready" : "blocked"}">${esc(wordpressMonitor.connectionStatus || "Unknown")}</span>
                        </div>
                        <div class="seo-status-item"><div><div class="seo-status-name">Last Published Post</div><div class="seo-status-detail">${esc(wordpressMonitor.lastPublishedPost || "No published post yet")}</div></div><span class="seo-status-pill ready">${esc(wordpressMonitor.mediaUploadStatus || "Enabled")}</span></div>
                        <div class="seo-status-item"><div><div class="seo-status-name">Drafts Created</div><div class="seo-status-detail">Failed Publishes: ${esc(String(wordpressMonitor.failedPublishes || 0))}</div></div><span class="seo-status-pill blocked">${esc(String(wordpressMonitor.draftsCreated || 0))}</span></div>
                        <div class="seo-status-item"><div><div class="seo-status-name">Default Category</div><div class="seo-status-detail">Default Author: ${esc(wordpressMonitor.defaultAuthor || "-")}</div></div><span class="seo-status-pill ready">${esc(wordpressMonitor.defaultCategory || "-")}</span></div>
                    </div>
                </div>

                <div class="result-card">
                    <h4>SEO Performance</h4>
                    ${seoPerformance.length
                        ? `<div class="seo-table-wrap">
                            <table class="results-table seo-mini-table">
                                <thead>
                                    <tr>
                                        <th>Article Title</th>
                                        <th>Published Date</th>
                                        <th>Focus Keyword</th>
                                        <th>Impressions</th>
                                        <th>Clicks</th>
                                        <th>CTR</th>
                                        <th>Average Position</th>
                                        <th>Indexed Status</th>
                                        <th>Leads Generated</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${seoPerformance.map((item) => `
                                        <tr>
                                            <td>${esc(item.articleTitle || "-")}</td>
                                            <td>${esc(item.publishedDate || "-")}</td>
                                            <td>${esc(item.focusKeyword || "-")}</td>
                                            <td>${esc(String(item.impressions || "Pending"))}</td>
                                            <td>${esc(String(item.clicks || "Pending"))}</td>
                                            <td>${esc(String(item.ctr || "Pending"))}</td>
                                            <td>${esc(String(item.averagePosition || "Pending"))}</td>
                                            <td>${esc(item.indexedStatus || "Pending")}</td>
                                            <td>${esc(String(item.leadsGenerated || "Pending"))}</td>
                                            <td>${item.requestIndexingEligible && item.url ? `<button type="button" class="json-toggle seo-request-indexing-btn" data-url="${esc(item.url)}">Request Indexing</button>` : "-"}</td>
                                        </tr>
                                    `).join("")}
                                </tbody>
                            </table>
                        </div>`
                        : '<div class="memory-empty">Performance rows are ready for future Search Console integration.</div>'}
                </div>
            </div>

            ${nextActions.length ? `
                <div class="result-card">
                    <h4>What Needs Action</h4>
                    <div class="seo-action-list">
                        ${nextActions.map((item) => `
                            <div class="seo-action-item tone-${esc(item.tone || "info")}">
                                <div class="seo-action-title">${esc(item.title)}</div>
                                <div class="seo-action-detail">${esc(item.detail || "")}</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            ` : ""}

            <div class="results-grid">
                <div class="result-card">
                    <h4>Recent Topic Ledger</h4>
                    ${recentTopics.length
                        ? `<div class="seo-table-wrap">
                            <table class="results-table seo-mini-table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Keyword</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${recentTopics.map((item) => `
                                        <tr>
                                            <td>${esc(item.date || "-")}</td>
                                            <td title="${esc(item.primaryKeyword || "-")}">${esc(item.primaryKeyword || "-")}</td>
                                            <td><span class="status-pill ${String(item.status || "").toLowerCase() === "publish" ? "status-found" : "status-not_found"}">${esc(item.status || "-")}</span></td>
                                        </tr>
                                    `).join("")}
                                </tbody>
                            </table>
                        </div>`
                        : '<div class="memory-empty">No SEO topics have been stored yet.</div>'}
                </div>

                <div class="result-card">
                    <h4>Recent SEO Runs</h4>
                    ${recentRuns.length
                        ? `<div class="seo-run-list">
                            ${recentRuns.map((run) => `
                                <div class="seo-run-item">
                                    <div class="seo-run-top">
                                        <span class="seo-run-status ${esc(run.status || "unknown")}">${esc(run.status || "unknown")}</span>
                                        <span class="memory-time">${esc(formatTimestamp(run.createdAt))}</span>
                                    </div>
                                    <div class="seo-run-title">${esc(run.title || run.primaryKeyword || "PatentZoom SEO run")}</div>
                                    <div class="seo-run-meta">
                                        <span>Keyword: ${esc(run.primaryKeyword || "-")}</span>
                                        <span>Post: ${esc(run.postStatus || "-")}</span>
                                        <span>Time: ${esc(String(run.executionTime || 0))}s</span>
                                    </div>
                                    ${run.error ? `<div class="seo-run-error">${esc(run.error)}</div>` : ""}
                                    ${run.wordpressUrl ? `<a class="result-link" href="${esc(run.wordpressUrl)}" target="_blank" rel="noopener noreferrer">${esc(run.wordpressUrl)}</a>` : ""}
                                </div>
                            `).join("")}
                        </div>`
                        : '<div class="memory-empty">No SEO runs logged yet.</div>'}
                </div>
            </div>

                <div class="result-card">
                    <h4>Run History</h4>
                ${logsHistory.length
                    ? `<div class="seo-table-wrap">
                        <table class="results-table seo-mini-table">
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Topic</th>
                                    <th>Mode</th>
                                    <th>Result</th>
                                    <th>SEO score</th>
                                    <th>Indexing</th>
                                    <th>Time Taken</th>
                                    <th>Failed Step</th>
                                    <th>Error Message</th>
                                    <th>WordPress URL</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${logsHistory.map((item, index) => `
                                    <tr>
                                        <td>${esc(item.publishDate || "-")}</td>
                                        <td>${esc(item.topic || "-")}</td>
                                        <td>${esc(item.mode || "-")}</td>
                                        <td><span class="status-pill ${String(item.status || "").toLowerCase() === "publish" || String(item.status || "").toLowerCase() === "success" ? "status-found" : "status-not_found"}">${esc(item.status || "-")}</span></td>
                                        <td>${item.seoScore ?? "-"}</td>
                                        <td>${esc(item.indexingStatus || "Pending")}</td>
                                        <td>${esc(String(item.timeTaken || 0))}s</td>
                                        <td>${esc(item.failedStep || "-")}</td>
                                        <td title="${esc(item.errorMessage || "-")}">${esc(item.errorMessage || "-")}</td>
                                        <td>${item.url ? `<a class="result-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.url)}</a>` : "-"}</td>
                                        <td>
                                            <div class="seo-action-buttons">
                                                <button type="button" class="json-toggle seo-history-action" data-history-action="logs" data-history-index="${index}">View Logs</button>
                                                <button type="button" class="json-toggle seo-history-action" data-history-action="retry" data-history-index="${index}">Retry</button>
                                                <button type="button" class="json-toggle seo-history-action" data-history-action="view" data-history-index="${index}" ${item.url ? "" : "disabled"}>View Post</button>
                                                <button type="button" class="json-toggle seo-history-action" data-history-action="regenerate" data-history-index="${index}">Regenerate</button>
                                                ${item.requestIndexingEligible && item.url ? `<button type="button" class="json-toggle seo-request-indexing-btn" data-url="${esc(item.url)}">Request Indexing</button>` : ""}
                                            </div>
                                        </td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>`
                    : '<div class="memory-empty">No SEO log history yet.</div>'}
            </div>
        </div>
    `;
}

function renderSEOPreviewModal(article) {
    return `
        <div class="captcha-alert-modal seo-preview-modal">
            <div class="captcha-alert-modal-card seo-preview-card">
                <div class="seo-card-header">
                    <div>
                        <div class="captcha-alert-modal-title">${esc(article.title || "Article Preview")}</div>
                        <div class="captcha-alert-modal-text">${esc(article.primaryKeyword || "")}</div>
                    </div>
                    <button type="button" class="json-toggle" id="close-seo-preview">Close</button>
                </div>
                <div class="seo-preview-meta">
                    <div><strong>Slug:</strong> ${esc(article.slug || "-")}</div>
                    <div><strong>Status:</strong> ${esc(article.publishStatus || "-")}</div>
                    <div><strong>SEO Score:</strong> ${article.seoScore ?? "-"}</div>
                </div>
                ${article.metaDescription ? `<div class="seo-preview-description">${esc(article.metaDescription)}</div>` : ""}
                <div class="seo-preview-body">${article.previewHtml || "<p>No preview content available.</p>"}</div>
            </div>
        </div>
    `;
}

function renderSEOHistoryModal(entry) {
    return `
        <div class="captcha-alert-modal seo-preview-modal">
            <div class="captcha-alert-modal-card seo-preview-card seo-history-card">
                <div class="seo-card-header">
                    <div>
                        <div class="captcha-alert-modal-title">${esc(entry.topic || "SEO Run History")}</div>
                        <div class="captcha-alert-modal-text">${esc(entry.publishDate || "-")} · ${esc(entry.mode || "-")} · ${esc(entry.status || "-")}</div>
                    </div>
                    <button type="button" class="json-toggle" id="close-seo-history">Close</button>
                </div>
                <div class="seo-preview-meta">
                    <div><strong>SEO Score:</strong> ${entry.seoScore ?? "-"}</div>
                    <div><strong>Time Taken:</strong> ${esc(String(entry.timeTaken || 0))}s</div>
                    <div><strong>Failed Step:</strong> ${esc(entry.failedStep || "-")}</div>
                </div>
                <div class="seo-preview-description"><strong>Error Message:</strong> ${esc(entry.errorMessage || "No error recorded. This run completed or stopped without a hard failure.")}</div>
                ${entry.url ? `<div class="seo-preview-description"><strong>WordPress URL:</strong> <a class="result-link" href="${esc(entry.url)}" target="_blank" rel="noopener noreferrer">${esc(entry.url)}</a></div>` : ""}
                <div class="json-block seo-history-json">${esc(JSON.stringify(entry, null, 2))}</div>
            </div>
        </div>
    `;
}

function renderSimpleRunSection() {
    return `
        <div class="run-section">
            <div class="run-actions">
                <button type="button" class="run-btn" id="run-btn" ${(state.isRunning || state.agentRunStatus !== "idle") ? "disabled" : ""}>
                    ${state.isRunning
                        ? '<span class="spinner"></span> Running...'
                        : "&#x25B6;&nbsp;&nbsp;Run Agent"}
                </button>
                <button type="button" class="stop-btn" id="stop-btn" ${(state.isRunning || state.agentRunStatus === "running" || state.agentRunStatus === "stopping") ? "" : "disabled"}>
                    ${state.stopRequested ? "Stopping..." : "Stop"}
                </button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Results renderers
// ---------------------------------------------------------------------------
function renderPCTResults(result) {
    if (result.status === "failure") {
        return `
            <div class="results-section">
                <div class="section-title">Results</div>
                <div class="error-banner">&#x26A0; ${esc(result.error || "Agent failed")}</div>
            </div>
        `;
    }

    const summary = result.summary || {};
    const results = result.results || [];
    const tests = result.tests || {};
    const outputFile = result.output_file || "";
    const outputName = outputFile.split(/[\\/]/).pop();

    let html = `
        <div class="results-section">
            <div class="section-title">Results</div>
            ${result.status === "stopped"
                ? '<div class="warning-banner">&#x23F9; Run stopped. Partial output was saved from the rows already processed.</div>'
                : ""
            }

            <!-- Summary cards -->
            <div class="stats-grid" style="grid-template-columns: repeat(5, 1fr)">
                <div class="stat-card">
                    <div class="stat-value">${summary.total || 0}</div>
                    <div class="stat-label">Total Rows</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value success">${summary.found || 0}</div>
                    <div class="stat-label">Contacts Found</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">${summary.not_found || 0}</div>
                    <div class="stat-label">Not Found</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value error">${summary.errors || 0}</div>
                    <div class="stat-label">Errors</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${result.execution_time || 0}s</div>
                    <div class="stat-label">Time</div>
                </div>
            </div>

            <!-- Download button -->
            ${outputName ? `
            <a href="/api/download/${encodeURIComponent(outputName)}" class="download-btn" download>
                &#x1F4E5; Download Work Report: ${esc(outputName)}
            </a>
            ` : ""}

            <!-- Row-by-row results table -->
            <div class="result-card" style="margin-top:16px;overflow-x:auto">
                <h4>&#x1F4CB; Row Details</h4>
                <table class="results-table">
                    <thead>
                        <tr>
                            <th>Row</th>
                            <th>Publication No</th>
                            <th>Country</th>
                            <th>Status</th>
                            <th>Email(s)</th>
                            <th>Phone(s)</th>
                            <th>Name</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.map((r) => `
                            <tr class="row-${r.status}">
                                <td>${r.row}</td>
                                <td>${esc(r.patent_id || "-")}</td>
                                <td>${esc(r.country || "-")}</td>
                                <td><span class="status-pill status-${r.status}">${esc(r.status)}</span></td>
                                <td>${r.emails?.length ? esc(r.emails.join("; ")) : "-"}</td>
                                <td>${r.phones?.length ? esc(r.phones.join("; ")) : "-"}</td>
                                <td>${esc(r.name || "-")}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>

            <!-- Self-tests -->
            <div class="result-card" style="margin-top:16px">
                <h4>&#x1F9EA; Self-Test Results — ${tests.passed_count || 0}/${tests.total || 0} Passed</h4>
                ${(tests.passed_tests || []).map((t) => `
                    <div class="test-item">
                        <span class="test-icon" style="color:var(--success)">&#x2713;</span>
                        <span class="test-name">${esc(t)}</span>
                    </div>
                `).join("")}
                ${(tests.failures || []).map((f) => `
                    <div class="test-item">
                        <span class="test-icon" style="color:var(--error)">&#x2717;</span>
                        <span class="test-name">${esc(f.name)}: ${esc(f.message)}</span>
                    </div>
                `).join("")}
            </div>
        </div>
    `;
    return html;
}

function renderSEOResults(result) {
    if (result.status === "failure") {
        return renderFailureResults(result);
    }

    const warnings = result.warnings || [];
    const outputLogs = result.outputLogs || [];
    const article = result.article || {};
    const ledger = result.ledgerEntry || {};
    const wpUrl = result.wordpressUrl || "";

    return `
        <div class="results-section">
            <div class="section-title">Results</div>
            ${result.status === "stopped"
                ? '<div class="warning-banner">&#x23F9; Run stopped. Partial logs were preserved.</div>'
                : ""
            }
            <div class="stats-grid" style="grid-template-columns: repeat(4, 1fr)">
                <div class="stat-card">
                    <div class="stat-value">${esc(result.postStatus || result.status || "-")}</div>
                    <div class="stat-label">Post Status</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${esc(result.primaryKeyword || "-")}</div>
                    <div class="stat-label">Primary Keyword</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${result.wordpressPostId || "-"}</div>
                    <div class="stat-label">WordPress Post ID</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${result.executionTime || 0}s</div>
                    <div class="stat-label">Execution Time</div>
                </div>
            </div>

            ${warnings.length
                ? `<div class="warning-banner">${warnings.map((warning) => esc(warning)).join("<br>")}</div>`
                : ""
            }

            <div class="result-card" style="margin-top:16px">
                <h4>&#x1F4DD; Article Summary</h4>
                <div class="seo-result-grid">
                    <div><strong>Topic:</strong> ${esc(result.topic || ledger.topicId || "-")}</div>
                    <div><strong>Title:</strong> ${esc(article.title || result.title || "-")}</div>
                    <div><strong>Slug:</strong> ${esc(article.slug || result.slug || "-")}</div>
                    <div><strong>Category:</strong> ${esc(article.category || "-")}</div>
                    <div><strong>Publish Source:</strong> ${esc(ledger.source || "-")}</div>
                    <div><strong>Featured Image ID:</strong> ${result.featuredImageId || "-"}</div>
                    <div class="full-span"><strong>Meta Title:</strong> ${esc(article.metaTitle || "-")}</div>
                    <div class="full-span"><strong>Meta Description:</strong> ${esc(article.metaDescription || "-")}</div>
                    ${wpUrl ? `<div class="full-span"><strong>WordPress URL:</strong> <a class="result-link" href="${esc(wpUrl)}" target="_blank" rel="noopener noreferrer">${esc(wpUrl)}</a></div>` : ""}
                </div>
            </div>

            ${outputLogs.length
                ? `<div class="result-card" style="margin-top:16px">
                    <h4>&#x1F4CA; Workflow Highlights</h4>
                    <div class="seo-log-list">
                        ${outputLogs.map((entry) => `<div class="seo-log-item">${esc(entry)}</div>`).join("")}
                    </div>
                </div>`
                : ""
            }
        </div>
    `;
}

function renderFailureResults(result) {
    return `
        <div class="results-section">
            <div class="section-title">Results</div>
            <div class="error-banner">&#x26A0; ${esc(result.error || `Agent failed after ${result.errors?.length || "?"} attempts`)}</div>
            ${(result.errors || []).map((err) => `
                <div class="result-card" style="margin-bottom:12px">
                    <h4>Attempt ${err.attempt}</h4>
                    <div class="json-block">${esc(err.traceback || err.error)}</div>
                </div>
            `).join("")}
        </div>
    `;
}

function renderMemorySection(learnings) {
    return `
        <div class="memory-section">
            <div class="section-title">Agent Memory — Recent Learnings</div>
            ${learnings.length === 0
                ? '<div class="memory-empty">No learnings yet — run the agent to start building memory.</div>'
                : `<div class="memory-list">
                    ${learnings.slice(-8).reverse().map((l) => `
                        <div class="memory-entry">
                            <span class="memory-icon">${l.outcome === "success" ? "&#x2705;" : "&#x274C;"}</span>
                            <div class="memory-content">
                                <div class="memory-task">${esc(l.task)}</div>
                                <div class="memory-insight">${esc(l.insight)}</div>
                                <div class="memory-time">${formatTimestamp(l.timestamp)} — Strategy: ${esc(l.strategy)}</div>
                            </div>
                        </div>
                    `).join("")}
                </div>`
            }
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Event Handlers
// ---------------------------------------------------------------------------
function attachHandlers(agent) {
    // Run button
    const runBtn = document.getElementById("run-btn");
    if (runBtn && !state.isRunning) {
        runBtn.onclick = async (e) => {
            e.preventDefault();
            e.stopPropagation();
            primeAlertAudio();
            const latestStatus = await loadAgentRunStatus(agent.module_name);
            if (latestStatus !== "idle") {
                addLogLine(
                    latestStatus === "stopping"
                        ? "Agent is still stopping. Please wait a moment and try again."
                        : "Agent is already running.",
                    "error",
                );
                renderMain();
                return;
            }

            if (agent.accepts_upload) {
                const mode = state.inputMode;

                if (mode === "upload" && !state.uploadedFilePath) {
                    addLogLine("Please upload an Excel file first", "error");
                    return;
                }
                if (mode === "wipo_download" && !state.selectedGazette) {
                    addLogLine("Please choose a WIPO gazette week first", "error");
                    return;
                }

                runAgent(agent.module_name, {
                    mode: mode,
                    file_path: mode === "upload" ? state.uploadedFilePath : undefined,
                    gazette: mode === "wipo_download" ? state.selectedGazette : undefined,
                });
            } else if (agent.ui_type === "seo_posting") {
                triggerSeoRun(agent);
            } else {
                runAgent(agent.module_name);
            }
        };
    }

    // Mode tabs
    const modeTabs = document.querySelectorAll(".mode-tab");
    modeTabs.forEach((tab) => {
        tab.onclick = (e) => {
            e.preventDefault();
            state.inputMode = tab.dataset.mode || "upload";
            renderMain();
            if (state.inputMode === "wipo_download" && !state.wipoGazettesLoaded) {
                loadWipoGazettes();
            }
        };
    });

    // File upload
    const fileInput = document.getElementById("file-input");
    if (fileInput) {
        fileInput.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                const res = await uploadFile(file);
                state.uploadedFilePath = res.path;
                renderMain();
            } catch (err) {
                addLogLine(`Upload failed: ${err.message}`, "error");
            }
        };
    }

    // Dropzone
    const dropzone = document.getElementById("dropzone");
    if (dropzone) {
        dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); };
        dropzone.ondragleave = () => dropzone.classList.remove("drag-over");
        dropzone.ondrop = async (e) => {
            e.preventDefault();
            dropzone.classList.remove("drag-over");
            const file = e.dataTransfer.files[0];
            if (!file) return;
            try {
                const res = await uploadFile(file);
                state.uploadedFilePath = res.path;
                renderMain();
            } catch (err) {
                addLogLine(`Upload failed: ${err.message}`, "error");
            }
        };
    }

    // Clear upload
    const clearBtn = document.getElementById("clear-upload");
    if (clearBtn) {
        clearBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            state.uploadedFilePath = null;
            renderMain();
        };
    }

    const stopBtn = document.getElementById("stop-btn");
    if (stopBtn && state.isRunning && !state.stopRequested) {
        stopBtn.onclick = async (e) => {
            e.preventDefault();
            e.stopPropagation();
            try {
                state.stopRequested = true;
                state.agentRunStatus = "stopping";
                addLogLine(
                    agent.module_name === "pct_agent"
                        ? "Stop requested. Interrupting the active browser step and saving partial results now."
                        : "Stop requested. Wrapping up the active workflow step and returning the latest result.",
                    "step",
                );
                renderMain();
                const response = await stopAgent(agent.module_name);
                if (response.status !== "stop_requested") {
                    throw new Error(response.error || "Stop request failed");
                }
            } catch (err) {
                state.stopRequested = false;
                state.agentRunStatus = "running";
                addLogLine(`Stop request failed: ${err.message}`, "error");
                renderMain();
            }
        };
    }

    const gazetteSelect = document.getElementById("wipo-gazette-select");
    if (gazetteSelect) {
        gazetteSelect.onchange = (e) => {
            state.selectedGazette = e.target.value || "";
        };
    }

    const refreshGazettesBtn = document.getElementById("refresh-wipo-gazettes");
    if (refreshGazettesBtn) {
        refreshGazettesBtn.onclick = (e) => {
            e.preventDefault();
            loadWipoGazettes(true);
        };
    }

    const seoTopicOverride = document.getElementById("seo-topic-override");
    if (seoTopicOverride) {
        seoTopicOverride.oninput = (e) => {
            state.seo.topicOverride = e.target.value || "";
        };
    }

    const seoPublishOverride = document.getElementById("seo-publish-override");
    if (seoPublishOverride) {
        seoPublishOverride.onchange = (e) => {
            state.seo.publishOverride = e.target.value || "draft";
        };
    }

    const seoFeaturedImage = document.getElementById("seo-featured-image");
    if (seoFeaturedImage) {
        seoFeaturedImage.onchange = (e) => {
            state.seo.enableFeaturedImage = !!e.target.checked;
        };
    }

    const seoDryRun = document.getElementById("seo-dry-run");
    if (seoDryRun) {
        seoDryRun.onchange = (e) => {
            state.seo.dryRun = !!e.target.checked;
        };
    }

    const seoRefreshOverview = document.getElementById("seo-refresh-overview");
    if (seoRefreshOverview && agent.ui_type === "seo_posting") {
        seoRefreshOverview.onclick = async (e) => {
            e.preventDefault();
            await loadSeoDashboardData(agent.module_name);
        };
    }

    const seoSaveDraftBtn = document.getElementById("seo-save-draft-btn");
    if (seoSaveDraftBtn && agent.ui_type === "seo_posting" && !state.isRunning) {
        seoSaveDraftBtn.onclick = async (e) => {
            e.preventDefault();
            primeAlertAudio();
            const latestStatus = await loadAgentRunStatus(agent.module_name);
            if (latestStatus !== "idle") return;
            triggerSeoRun(agent, { publish_override: "draft", dry_run: false });
        };
    }

    const seoPublishNowBtn = document.getElementById("seo-publish-now-btn");
    if (seoPublishNowBtn && agent.ui_type === "seo_posting" && !state.isRunning) {
        seoPublishNowBtn.onclick = async (e) => {
            e.preventDefault();
            primeAlertAudio();
            const latestStatus = await loadAgentRunStatus(agent.module_name);
            if (latestStatus !== "idle") return;
            triggerSeoRun(agent, { publish_override: "publish", dry_run: false });
        };
    }

    const seoGoogleClientId = document.getElementById("seo-google-client-id");
    if (seoGoogleClientId) {
        seoGoogleClientId.oninput = (e) => {
            state.seo.google.clientId = e.target.value || "";
        };
    }

    const seoGoogleClientSecret = document.getElementById("seo-google-client-secret");
    if (seoGoogleClientSecret) {
        seoGoogleClientSecret.oninput = (e) => {
            state.seo.google.clientSecret = e.target.value || "";
        };
    }

    const seoGoogleProperty = document.getElementById("seo-google-property");
    if (seoGoogleProperty) {
        seoGoogleProperty.oninput = (e) => {
            state.seo.google.property = e.target.value || "";
        };
    }

    const seoGoogleSaveBtn = document.getElementById("seo-google-save-btn");
    if (seoGoogleSaveBtn && agent.ui_type === "seo_posting") {
        seoGoogleSaveBtn.onclick = async (e) => {
            e.preventDefault();
            try {
                const response = await saveGoogleSearchConsoleConfig();
                if (response.error) throw new Error(response.error);
                state.seo.google.clientConfigured = !!response.clientConfigured;
                state.seo.google.connected = !!response.connected;
                state.seo.google.property = response.property || state.seo.google.property;
                addLogLine("Google Search Console OAuth settings saved.", "success");
                await loadSeoDashboardData(agent.module_name);
            } catch (err) {
                addLogLine(`Google OAuth save failed: ${err.message}`, "error");
            }
        };
    }

    const seoGoogleConnectBtn = document.getElementById("seo-google-connect-btn");
    if (seoGoogleConnectBtn && agent.ui_type === "seo_posting") {
        seoGoogleConnectBtn.onclick = (e) => {
            e.preventDefault();
            window.open("/api/google/search-console/connect", "_blank", "noopener,noreferrer");
        };
    }

    const seoGoogleBrowserBtn = document.getElementById("seo-google-browser-btn");
    if (seoGoogleBrowserBtn && agent.ui_type === "seo_posting") {
        seoGoogleBrowserBtn.onclick = async (e) => {
            e.preventDefault();
            try {
                const response = await launchGoogleBrowserSession();
                if (response.error) throw new Error(response.error);
                addLogLine(response.message || "Google browser session opened.", "success");
            } catch (err) {
                addLogLine(`Google browser session failed: ${err.message || err}`, "error");
            }
        };
    }

    if (agent.ui_type === "seo_posting") {
        document.querySelectorAll(".seo-preview-btn").forEach((btn) => {
            btn.onclick = (e) => {
                e.preventDefault();
                const articleId = btn.dataset.articleId || "";
                const article = (state.seoDashboard.snapshot?.articleManager || []).find((item) => item.id === articleId);
                if (!article) return;
                state.seoDashboard.previewArticle = article;
                renderMain();
            };
        });

        document.querySelectorAll(".seo-request-indexing-btn").forEach((btn) => {
            btn.onclick = async (e) => {
                e.preventDefault();
                const url = btn.dataset.url || "";
                if (!url) return;
                btn.disabled = true;
                addLogLine(`Requesting Google indexing fallback for ${url}`, "step");
                try {
                    const response = await requestGoogleIndexing(url);
                    if (response.error) {
                        throw new Error(response.error);
                    }
                    const indexing = response.indexing || {};
                    const summary =
                        indexing.browserFallbackSubmitted
                            ? indexing.browserFallbackMessage || "Request Indexing clicked in Google Search Console"
                            : indexing.browserFallbackStatus === "login_required"
                                ? "Browser fallback needs one Google login in the automation profile"
                                : indexing.inspection?.coverageState ||
                                  indexing.inspection?.verdict ||
                                  (indexing.autoSubmitSucceeded ? "Submitted to Google" : "Indexing handoff attempted");
                    addLogLine(`Indexing request complete: ${summary}`, "success");
                    await loadSeoDashboardData(agent.module_name);
                } catch (err) {
                    addLogLine(`Indexing request failed: ${err.message || err}`, "error");
                } finally {
                    btn.disabled = false;
                }
            };
        });

        const closeSeoPreview = document.getElementById("close-seo-preview");
        if (closeSeoPreview) {
            closeSeoPreview.onclick = (e) => {
                e.preventDefault();
                state.seoDashboard.previewArticle = null;
                renderMain();
            };
        }

        document.querySelectorAll(".seo-history-action").forEach((btn) => {
            btn.onclick = async (e) => {
                e.preventDefault();
                const historyIndex = Number(btn.dataset.historyIndex || "-1");
                const action = btn.dataset.historyAction || "";
                const entry = (state.seoDashboard.snapshot?.logsHistory || [])[historyIndex];
                if (!entry) return;

                if (action === "logs") {
                    state.seoDashboard.historyEntry = entry;
                    renderMain();
                    return;
                }

                if (action === "view" && entry.url) {
                    window.open(entry.url, "_blank", "noopener,noreferrer");
                    return;
                }

                if (action === "retry" || action === "regenerate") {
                    state.seo.topicOverride = entry.topic || "";
                    state.seo.publishOverride = entry.mode === "publish" ? "publish" : "draft";
                    state.seo.dryRun = action === "retry" ? false : true;
                    renderMain();
                    const latestStatus = await loadAgentRunStatus(agent.module_name);
                    if (latestStatus !== "idle") return;
                    triggerSeoRun(agent, {
                        topic_override: entry.topic || "",
                        publish_override: state.seo.publishOverride,
                        dry_run: state.seo.dryRun,
                    });
                }
            };
        });

        const closeSeoHistory = document.getElementById("close-seo-history");
        if (closeSeoHistory) {
            closeSeoHistory.onclick = (e) => {
                e.preventDefault();
                state.seoDashboard.historyEntry = null;
                renderMain();
            };
        }
    }
}

function inferSeoStageFromMessage(message = "") {
    const lower = String(message || "").toLowerCase();
    if (lower.includes("preparing a new patentzoom seo run")) return { stage: "readiness", status: "active" };
    if (lower.includes("validating local patentzoom seo setup")) return { stage: "readiness", status: "active" };
    if (lower.includes("loading recent patentzoom posts")) return { stage: "readiness", status: "active" };
    if (lower.includes("loaded") && lower.includes("recent patentzoom posts")) return { stage: "readiness", status: "complete" };
    if (lower.includes("researching keywords")) return { stage: "keywords", status: "active" };
    if (lower.includes("selected \"") || lower.includes("chosen topic:")) return { stage: "keywords", status: "complete" };
    if (lower.includes("starting ai article generation")) return { stage: "content", status: "active" };
    if (lower.includes("article draft completed")) return { stage: "content", status: "complete" };
    if (lower.includes("article outline") || lower.includes("final seo article draft")) return { stage: "content", status: "active" };
    if (lower.includes("running seo optimization")) return { stage: "optimization", status: "active" };
    if (lower.includes("seo optimization complete")) return { stage: "optimization", status: "complete" };
    if (lower.includes("seo optimizer") || lower.includes("internal links")) return { stage: "optimization", status: "active" };
    if (lower.includes("starting featured image generation")) return { stage: "image", status: "active" };
    if (lower.includes("featured image stage complete")) return { stage: "image", status: "complete" };
    if (lower.includes("featured image stage skipped")) return { stage: "image", status: "skipped" };
    if (lower.includes("featured image stage completed without")) return { stage: "image", status: "warning" };
    if (lower.includes("generating featured image") || lower.includes("uploaded featured image")) return { stage: "image", status: "active" };
    if (lower.includes("publishing article to wordpress")) return { stage: "publishing", status: "active" };
    if (lower.includes("publishing stage complete")) return { stage: "publishing", status: "complete" };
    if (lower.includes("publishing skipped") || lower.includes("dry run enabled")) return { stage: "publishing", status: "skipped" };
    if (lower.includes("submitting sitemap") || lower.includes("indexing handoff")) return { stage: "indexing", status: "active" };
    if (lower.includes("indexing handoff complete") || lower.includes("submitted indexing api request") || lower.includes("sitemap ping sent")) return { stage: "indexing", status: "complete" };
    if (lower.includes("indexing skipped")) return { stage: "indexing", status: "skipped" };
    return null;
}

function setSeoStageStatus(stageKey, status, detail) {
    const workflow = state.seoDashboard.workflow;
    const index = workflow.stages.findIndex((stage) => stage.key === stageKey);
    if (index < 0) return;

    if (status === "active") {
        workflow.stages.forEach((stage, idx) => {
            if (idx < index && stage.status === "pending") {
                stage.status = "complete";
            }
        });
    }

    workflow.stages[index].status = status;
    if (detail) workflow.stages[index].detail = detail;
    workflow.currentStage = stageKey;
    workflow.currentMessage = detail || workflow.currentMessage;
}

function handleSeoWorkflowEvent(event, fallbackType = "step") {
    const data = event.data || {};
    const inferred = data.stage
        ? { stage: data.stage, status: data.status || fallbackType }
        : inferSeoStageFromMessage(event.message);
    if (!inferred) return;
    const status = inferred.status === "step" ? "active" : inferred.status;
    setSeoStageStatus(inferred.stage, status, event.message || "");
}

function finalizeSeoWorkflow(result) {
    if (result.status === "failure") {
        const workflow = state.seoDashboard.workflow;
        const active = workflow.stages.find((stage) => stage.status === "active");
        if (active) active.status = "error";
        workflow.currentMessage = result.error || "The SEO workflow failed.";
        return;
    }

    if (result.status === "stopped") {
        state.seoDashboard.workflow.currentMessage = "Run stopped. Review the partial output and logs below.";
        return;
    }

    if (result.postStatus === "dry-run") {
        setSeoStageStatus("publishing", "skipped", "Dry run finished without publishing.");
        setSeoStageStatus("indexing", "skipped", "Indexing was skipped because nothing was published.");
    } else {
        setSeoStageStatus("publishing", "complete", `WordPress status: ${result.postStatus || "saved"}`);
        setSeoStageStatus(
            "indexing",
            result.postStatus === "publish" ? "complete" : "skipped",
            result.postStatus === "publish"
                ? "Published URL handed off for sitemap and indexing checks."
                : "Draft saved. Indexing waits until the post is published.",
        );
    }
    state.seoDashboard.workflow.currentMessage = "PatentZoom SEO workflow finished successfully.";
}

function buildSeoWorkflowState(stageDefs = []) {
    return {
        currentStage: "",
        currentMessage: "",
        stages: (stageDefs || []).map((stage) => ({
            key: stage.key,
            label: stage.label,
            description: stage.description,
            status: "pending",
            detail: "",
        })),
    };
}

function resetSeoWorkflow(stageDefs = null) {
    const defs = stageDefs || state.seoDashboard.snapshot?.workflowStages || [];
    state.seoDashboard.workflow = buildSeoWorkflowState(defs);
}

async function loadSeoDashboardData(name) {
    state.seoDashboard.loading = true;
    state.seoDashboard.error = "";
    state.seoDashboard.previewArticle = null;
    state.seoDashboard.historyEntry = null;
    renderMain();
    try {
        const res = await fetch(`/api/agents/${name}/dashboard-data`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to load SEO dashboard data");
        state.seoDashboard.snapshot = data;
        state.seo.publishOverride = data?.todayRun?.publishMode === "publish" ? "publish" : "draft";
        state.seo.enableFeaturedImage = data?.todayRun?.generateFeaturedImage !== false;
        state.seo.dryRun = false;
        state.seo.google.clientConfigured = !!data?.googleAuth?.clientConfigured;
        state.seo.google.connected = !!data?.googleAuth?.connected;
        state.seo.google.property = data?.googleAuth?.property || state.seo.google.property;
        state.seo.google.redirectUri = data?.googleAuth?.redirectUri || state.seo.google.redirectUri;
        if (!state.seo.topicOverride) {
            state.seo.topicOverride = data?.todayRun?.selectedTopic || "";
        }
        resetSeoWorkflow(data.workflowStages || []);
    } catch (e) {
        console.error("Failed to load SEO dashboard data:", e);
        state.seoDashboard.error = e.message || "Failed to load SEO dashboard data";
        state.seoDashboard.snapshot = null;
        resetSeoWorkflow([]);
    } finally {
        state.seoDashboard.loading = false;
        renderMain();
    }
}

// ---------------------------------------------------------------------------
// Terminal helpers
// ---------------------------------------------------------------------------
function createTerminalLine(entry) {
    const div = document.createElement("div");
    div.className = `terminal-line ${entry.type}`;
    const prefix =
        entry.type === "success" ? "&#x2713;" : entry.type === "error" ? "&#x2717;" : "&#x203A;";
    div.innerHTML = `
        <span class="terminal-time">${entry.time}</span>
        <span class="terminal-prefix">${prefix}</span>
        <span class="terminal-msg">${esc(entry.message)}</span>
    `;
    return div;
}

function createTerminalLineHTML(entry) {
    const prefix =
        entry.type === "success" ? "&#x2713;" : entry.type === "error" ? "&#x2717;" : "&#x203A;";
    return `
        <div class="terminal-line ${entry.type}">
            <span class="terminal-time">${entry.time}</span>
            <span class="terminal-prefix">${prefix}</span>
            <span class="terminal-msg">${esc(entry.message)}</span>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function esc(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function formatPercent(rate) {
    return `${Math.round(rate * 100)}%`;
}

function formatTimestamp(ts) {
    if (!ts) return "";
    try {
        return new Date(ts).toLocaleString();
    } catch {
        return ts;
    }
}

function toggleJSON() {
    const el = document.getElementById("json-output");
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
}
