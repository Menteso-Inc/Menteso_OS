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
    renderMain();

    // Build query string from params
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

    // Refresh agent data after run
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
    } else if (data.type === "complete") {
        state.lastResult = data.result;
        addLogLine("Agent execution complete.", "success");
        renderMain();
    } else if (data.type === "error") {
        addLogLine(`FATAL: ${data.message}`, "error");
    }
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
                <div class="welcome-icon">👁️</div>
                <h2>Visual Observer Agent</h2>
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

    // --- Input section (agent-specific) ---
    if (agent.accepts_upload) {
        html += renderUploadSection(agent);
    } else {
        html += renderSimpleRunSection();
    }

    // --- Terminal ---
    html += `
        <div class="terminal-section">
            <div class="section-title">Execution Log</div>
            <div class="terminal" id="terminal">
                ${state.executionLog.length === 0 && !state.isRunning
                    ? '<span class="terminal-empty">Configure input above and click "Run Agent" to start...</span>'
                    : ""}
                ${state.executionLog.map((l) => createTerminalLineHTML(l)).join("")}
                ${state.isRunning ? '<span class="terminal-cursor"></span>' : ""}
            </div>
        </div>
    `;

    // --- Results ---
    if (state.lastResult) {
        if (agent.module_name === "pct_agent") {
            html += renderPCTResults(state.lastResult);
        } else if (state.lastResult.status === "success") {
            html += renderTestAgentResults(state.lastResult);
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
                                    <span class="upload-done-icon">✓</span>
                                    <span class="upload-done-name">${esc(uploaded.split(/[\\/]/).pop())}</span>
                                    <button class="upload-clear" id="clear-upload">✕</button>
                               </div>`
                            : `<div class="upload-prompt">
                                    <span class="upload-icon">📄</span>
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
                        <span class="wipo-icon">🌐</span>
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
                        : "▶&nbsp;&nbsp;Run PCT Agent"}
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
                    : "▶&nbsp;&nbsp;Run Agent"}
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
                <div class="error-banner">⚠ ${esc(result.error || "Agent failed")}</div>
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
                📥 Download Output Excel: ${esc(outputName)}
            </a>
            ` : ""}

            <!-- Row-by-row results table -->
            <div class="result-card" style="margin-top:16px;overflow-x:auto">
                <h4>📋 Row Details</h4>
                <table class="results-table">
                    <thead>
                        <tr>
                            <th>Row</th>
                            <th>Doc ID</th>
                            <th>Status</th>
                            <th>Email(s)</th>
                            <th>Phone(s)</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.map((r) => `
                            <tr class="row-${r.status}">
                                <td>${r.row}</td>
                                <td>${esc(r.doc_id || "-")}</td>
                                <td><span class="status-pill status-${r.status}">${esc(r.status)}</span></td>
                                <td>${r.emails?.length ? esc(r.emails.join("; ")) : "-"}</td>
                                <td>${r.phones?.length ? esc(r.phones.join("; ")) : "-"}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>

            <!-- Self-tests -->
            <div class="result-card" style="margin-top:16px">
                <h4>🧪 Self-Test Results — ${tests.passed_count || 0}/${tests.total || 0} Passed</h4>
                ${(tests.passed_tests || []).map((t) => `
                    <div class="test-item">
                        <span class="test-icon" style="color:var(--success)">✓</span>
                        <span class="test-name">${esc(t)}</span>
                    </div>
                `).join("")}
                ${(tests.failures || []).map((f) => `
                    <div class="test-item">
                        <span class="test-icon" style="color:var(--error)">✗</span>
                        <span class="test-name">${esc(f.name)}: ${esc(f.message)}</span>
                    </div>
                `).join("")}
            </div>
        </div>
    `;
    return html;
}

function renderTestAgentResults(result) {
    const data = result.data || {};
    const sys = data.system || {};
    const py = data.python || {};
    const disk = data.disk || {};
    const env = data.env_status || {};
    const tests = result.tests || {};
    const usage = disk.usage_percent || 0;

    return `
        <div class="results-section">
            <div class="section-title">Results</div>
            <div class="results-grid">
                <div class="result-card">
                    <h4>🖥 System</h4>
                    ${Object.entries(sys).map(([k, v]) => `
                        <div class="result-row"><span class="result-key">${esc(k)}</span><span class="result-val">${esc(String(v))}</span></div>
                    `).join("")}
                </div>
                <div class="result-card">
                    <h4>🐍 Python</h4>
                    ${Object.entries(py).map(([k, v]) => `
                        <div class="result-row"><span class="result-key">${esc(k)}</span><span class="result-val">${esc(String(v))}</span></div>
                    `).join("")}
                </div>
                <div class="result-card">
                    <h4>💾 Disk Usage</h4>
                    <div class="result-row"><span class="result-key">Total</span><span class="result-val">${disk.total_gb || 0} GB</span></div>
                    <div class="result-row"><span class="result-key">Used</span><span class="result-val">${disk.used_gb || 0} GB</span></div>
                    <div class="result-row"><span class="result-key">Free</span><span class="result-val">${disk.free_gb || 0} GB</span></div>
                    <div class="progress-bar"><div class="progress-fill ${usage > 85 ? "high" : ""}" style="width:${usage}%"></div></div>
                    <div style="text-align:center;margin-top:8px;font-size:13px;color:var(--text-secondary)">${usage}% used</div>
                </div>
                <div class="result-card">
                    <h4>🔑 Environment Keys</h4>
                    ${Object.entries(env).map(([k, v]) => `
                        <div class="result-row"><span class="result-key">${esc(k)}</span><span class="result-val">${v === "set" ? "🟢 Set" : "🔴 Not Set"}</span></div>
                    `).join("")}
                </div>
            </div>
            <div class="result-card" style="margin-top:16px">
                <h4>🧪 Self-Test Results — ${tests.passed_count || 0}/${tests.total || 0} Passed</h4>
                ${(tests.passed_tests || []).map((t) => `<div class="test-item"><span class="test-icon" style="color:var(--success)">✓</span><span class="test-name">${esc(t)}</span></div>`).join("")}
                ${(tests.failures || []).map((f) => `<div class="test-item"><span class="test-icon" style="color:var(--error)">✗</span><span class="test-name">${esc(f.name)}: ${esc(f.message)}</span></div>`).join("")}
            </div>
            <div class="stats-grid" style="margin-top:16px;grid-template-columns:repeat(3,1fr)">
                <div class="stat-card"><div class="stat-value success">${result.attempts || 1}</div><div class="stat-label">Attempts</div></div>
                <div class="stat-card"><div class="stat-value">${result.execution_time || 0}s</div><div class="stat-label">Execution Time</div></div>
                <div class="stat-card"><div class="stat-value success">${tests.passed_count || 0}/${tests.total || 0}</div><div class="stat-label">Tests Passed</div></div>
            </div>
        </div>
    `;
}

function renderFailureResults(result) {
    return `
        <div class="results-section">
            <div class="section-title">Results</div>
            <div class="error-banner">⚠ ${esc(result.error || `Agent failed after ${result.errors?.length || "?"} attempts`)}</div>
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
                            <span class="memory-icon">${l.outcome === "success" ? "✅" : "❌"}</span>
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
        entry.type === "success" ? "✓" : entry.type === "error" ? "✗" : "›";
    div.innerHTML = `
        <span class="terminal-time">${entry.time}</span>
        <span class="terminal-prefix">${prefix}</span>
        <span class="terminal-msg">${esc(entry.message)}</span>
    `;
    return div;
}

function createTerminalLineHTML(entry) {
    const prefix =
        entry.type === "success" ? "✓" : entry.type === "error" ? "✗" : "›";
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
