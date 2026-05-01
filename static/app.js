/* ============================================================
   Menteso Virtual Office — Dashboard Frontend
   ============================================================ */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
    agents: [],
    selectedAgent: null,
    isRunning: false,
    executionLog: [],
    lastResult: null,
    startTime: null,
    uploadedFilePath: null,
    pipelineMode: false,
    pipeline: null,
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

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
    await loadAgents();
    render();
});

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

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    return await res.json();
}

async function runAgent(name, params = {}) {
    state.isRunning = true;
    state.executionLog = [];
    state.lastResult = null;
    state.startTime = Date.now();
    state.pipelineMode = false;
    state.pipeline = null;
    state.browser = {
        url: "", event: "idle", patent_id: "", title: "", applicant: "",
        country: "", row: 0, total: 0, pdf_url: "", emails: [], phones: [],
        name: "", status: "", found_count: 0, not_found_count: 0, error_count: 0,
    };
    renderMain();

    const query = new URLSearchParams();
    if (params.file_path) query.set("file_path", params.file_path);
    if (params.mode) query.set("mode", params.mode);
    const qs = query.toString();
    const url = `/api/agents/${name}/run${qs ? "?" + qs : ""}`;

    try {
        const response = await fetch(url);
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
    state.browser.event = "done";
    updateBrowserPreview();

    await loadAgents();
    if (state.selectedAgent) {
        const detail = await loadAgentDetail(state.selectedAgent.module_name);
        if (detail) state.selectedAgent = detail;
    }
    renderMain();
}

function handleSSEEvent(data) {
    if (data.type === "step") {
        const type = classifyMessage(data.message);
        addLogLine(data.message, type);
    } else if (data.type === "pipeline_stats") {
        handlePipelineStats(data);
    } else if (data.type === "browser") {
        handleBrowserEvent(data);
    } else if (data.type === "complete") {
        state.lastResult = data.result;
        state.pipelineMode = false;
        addLogLine("Agent execution complete.", "success");
        state.browser.event = "done";
        updateBrowserPreview();
        renderMain();
    } else if (data.type === "error") {
        addLogLine(`FATAL: ${data.message}`, "error");
    }
}

function handlePipelineStats(data) {
    state.pipelineMode = true;
    state.pipeline = data;
    updatePipelinePanel();
}

function handleBrowserEvent(data) {
    Object.assign(state.browser, data);
    updateBrowserPreview();
}

function classifyMessage(msg) {
    const lower = msg.toLowerCase();
    if (lower.includes("passed") || lower.includes("success") || lower.includes("saved") || lower.startsWith("done"))
        return "success";
    if (lower.includes("fail") || lower.includes("error") || lower.includes("fatal"))
        return "error";
    if (lower.includes("found:"))
        return "success";
    return "step";
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

    state.agents.forEach((agent) => {
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
            state.uploadedFilePath = null;
            render();
        };
        listEl.appendChild(item);
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

    let html = `
        <!-- Agent Header -->
        <div class="agent-header">
            <h2>${esc(agent.name || agent.module_name)}</h2>
            <p class="agent-desc">${esc(agent.description || "")}</p>
            <div class="agent-badges">
                <span class="badge badge-role">${esc(agent.role || "Agent")}</span>
                <span class="badge badge-version">v${esc(agent.version || "1.0")}</span>
                ${agent.status === "active" ? '<span class="badge badge-active">Active</span>' : ""}
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

    // --- Input section ---
    if (agent.accepts_upload) {
        html += renderUploadSection(agent);
    } else {
        html += renderSimpleRunSection();
    }

    // --- Pipeline progress panel (shown in pipeline mode) ---
    if (state.pipelineMode || (state.isRunning && state.pipeline)) {
        html += renderPipelineSection();
    }

    // --- Execution Log + Browser Preview (side by side) ---
    html += `
        <div class="execution-split">
            <div class="execution-log-panel${state.pipelineMode ? " full-width" : ""}">
                <div class="section-title">Execution Log</div>
                <div class="terminal" id="terminal">
                    ${state.executionLog.length === 0 && !state.isRunning
                        ? '<span class="terminal-empty">Configure input above and click "Run Agent" to start...</span>'
                        : ""}
                    ${state.executionLog.map((l) => createTerminalLineHTML(l)).join("")}
                    ${state.isRunning ? '<span class="terminal-cursor"></span>' : ""}
                </div>
            </div>
            ${!state.pipelineMode ? `
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
        if (agent.module_name === "pct_agent") {
            html += renderPCTResults(state.lastResult);
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

    main.innerHTML = html;
    attachHandlers(agent);
}

// ---------------------------------------------------------------------------
// Agent-specific input sections
// ---------------------------------------------------------------------------
function renderUploadSection(agent) {
    const uploaded = state.uploadedFilePath;
    const types = (agent.upload_types || []).join(",");

    return `
        <div class="input-section">
            <div class="section-title">Input</div>
            <div class="input-card">
                <!-- Mode selector -->
                <div class="input-row">
                    <label class="input-label">Mode</label>
                    <div class="mode-tabs" id="mode-tabs">
                        <button class="mode-tab active" data-mode="upload">Upload Excel</button>
                        <button class="mode-tab" data-mode="wipo_download">Download from WIPO</button>
                    </div>
                </div>

                <!-- Upload area -->
                <div id="upload-area" class="upload-zone">
                    <div class="upload-dropzone" id="dropzone">
                        ${uploaded
                            ? `<div class="upload-done">
                                    <span class="upload-done-icon">&#x2713;</span>
                                    <span class="upload-done-name">${esc(uploaded.split(/[\\/]/).pop())}</span>
                                    <button class="upload-clear" id="clear-upload">&#x2715;</button>
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

                <!-- WIPO area (hidden by default) -->
                <div id="wipo-area" style="display:none">
                    <div class="wipo-info">
                        <span class="wipo-icon">&#x1F310;</span>
                        <div>
                            <div class="wipo-title">WIPO PatentScope Weekly Browse</div>
                            <div class="wipo-url">patentscope.wipo.int/search/en/resultWeeklyBrowse.jsf</div>
                        </div>
                    </div>
                </div>

                <!-- Run -->
                <button class="run-btn" id="run-btn" ${state.isRunning ? "disabled" : ""}>
                    ${state.isRunning
                        ? '<span class="spinner"></span> Processing...'
                        : "&#x25B6;&nbsp;&nbsp;Run PCT Agent"}
                </button>
            </div>
        </div>
    `;
}

function renderSimpleRunSection() {
    return `
        <div class="run-section">
            <button class="run-btn" id="run-btn" ${state.isRunning ? "disabled" : ""}>
                ${state.isRunning
                    ? '<span class="spinner"></span> Running...'
                    : "&#x25B6;&nbsp;&nbsp;Run Agent"}
            </button>
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
        runBtn.onclick = () => {
            if (agent.accepts_upload) {
                const activeTab = document.querySelector(".mode-tab.active");
                const mode = activeTab ? activeTab.dataset.mode : "upload";

                if (mode === "upload" && !state.uploadedFilePath) {
                    addLogLine("Please upload an Excel file first", "error");
                    return;
                }

                runAgent(agent.module_name, {
                    mode: mode,
                    file_path: mode === "upload" ? state.uploadedFilePath : undefined,
                });
            } else {
                runAgent(agent.module_name);
            }
        };
    }

    // Mode tabs
    const modeTabs = document.querySelectorAll(".mode-tab");
    modeTabs.forEach((tab) => {
        tab.onclick = () => {
            modeTabs.forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            const uploadArea = document.getElementById("upload-area");
            const wipoArea = document.getElementById("wipo-area");
            if (tab.dataset.mode === "upload") {
                if (uploadArea) uploadArea.style.display = "block";
                if (wipoArea) wipoArea.style.display = "none";
            } else {
                if (uploadArea) uploadArea.style.display = "none";
                if (wipoArea) wipoArea.style.display = "block";
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
            e.stopPropagation();
            state.uploadedFilePath = null;
            renderMain();
        };
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
