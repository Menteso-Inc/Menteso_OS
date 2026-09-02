/* ============================================================
   Menteso Virtual Office — Dashboard Frontend
   ============================================================ */

// ---------------------------------------------------------------------------
// Fast-mode level table (mirrors FAST_MODE_LEVELS in agents/pct_agent/agent.py).
// Level 1 = safe sequential, level 5 = max parallel. Sent with run requests
// so the backend picks the right runtime profile.
// ---------------------------------------------------------------------------
const FAST_LEVELS = {
    1: { emoji: "😇", label: "Safe",       hint: "1 browser, headless. Slowest, safest." },
    2: { emoji: "🙂", label: "Mild",       hint: "1 pipeline, 2 browsers, headless." },
    3: { emoji: "😏", label: "Balanced",   hint: "2 pipelines, 4 browsers, headless. ~50 rows/min." },
    4: { emoji: "😎", label: "Aggressive", hint: "3 pipelines, 6 browsers, headless. ~100 rows/min." },
    5: { emoji: "😈", label: "Max",        hint: "4 pipelines, 8 browsers, headless. ~150 rows/min." },
};

function readStoredFastLevel() {
    const raw = parseInt(localStorage.getItem("menteso-fast-level"), 10);
    if (Number.isFinite(raw) && raw >= 1 && raw <= 5) return raw;
    // Match the Python-side FAST_MODE_DEFAULT_LEVEL — start in Balanced (L3).
    return 3;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
    theme: localStorage.getItem("menteso-theme") || "dark",
    fastLevel: readStoredFastLevel(),
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
        activeWorkspaceId: "patent-drawing-experts",
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
        expandedInsight: "overview",
        workflow: {
            currentStage: "",
            currentMessage: "",
            stages: [],
        },
        previewArticle: null,
        historyEntry: null,
    },
    accountantDashboard: {
        loading: false,
        error: "",
        snapshot: null,
        view: "invoice_request",
        snapshotFingerprint: "",
        tableScrollLeft: 0,
    },
    pipelineMode: false,
    pipeline: null,
    captcha: {
        active: false,
        message: "",
        resolvedMessage: "",
    },
    // Mirror of FAST_MODE_LEVELS in agents/pct_agent/agent.py so the
    // dashboard slider shows the same emoji + label the agent uses.
    fastModeLevels: {
        1: { emoji: "😇", label: "Safe",       hint: "1 browser, headless. Slowest, safest." },
        2: { emoji: "🙂", label: "Mild",       hint: "2 browsers, headless. Slight speedup." },
        3: { emoji: "😏", label: "Balanced",   hint: "4 browsers, headless. ~50 rows/min." },
        4: { emoji: "😎", label: "Aggressive", hint: "6 browsers, headless. ~100 rows/min." },
        5: { emoji: "😈", label: "Max",        hint: "8 browsers, headless. ~150 rows/min." },
    },

    // Run metrics — fed by browser events. Stopwatch + ETA + captcha tier
    // breakdown so the operator can see real-time progress and which tier
    // is actually clearing each challenge.
    runMetrics: {
        startedAt: null,
        finishedAt: null,
        totalRows: 0,
        processedRows: 0,
        foundRows: 0,
        notFoundRows: 0,
        errorRows: 0,
        captchaTotals: { vision: 0, openai: 0, audio: 0, diy: 0, manual: 0, other: 0 },
        captchaCount: 0,
        lastTickAt: 0,
        // Active fast-mode level (1-5). User can drag the slider mid-run
        // and the backend will pick up the new level at the next chunk.
        fastLevel: 1,
        fastLevelChanging: false,
        // Rolling window of row-completion timestamps (ms). Used so the ETA
        // reflects the *current* rate rather than the cumulative average,
        // which is wrecked by any captcha early in the run.
        rowTimestamps: [],
        // When the user last changed the fast-mode level. After a mode
        // change the rolling window is cleared so the ETA reflects the
        // NEW rate rather than the average of old + new rates.
        modeChangedAt: null,
        rowsAtModeChange: 0,
        recalibrating: false,
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

const SEO_WORKSPACES = [
    {
        id: "ip-docketers",
        name: "IP Docketers SEO Agent",
        kind: "live",
        status: "active",
        placeholderTitle: "",
        placeholderMessage: "",
        placeholderDetail: "",
    },
    {
        id: "menteso",
        name: "Menteso SEO Agent",
        kind: "live",
        status: "active",
        placeholderTitle: "",
        placeholderMessage: "",
        placeholderDetail: "",
    },
    {
        id: "patent-drawing-experts",
        name: "Patent Drawing Experts SEO Agent",
        kind: "live",
        status: "active",
        placeholderTitle: "",
        placeholderMessage: "",
        placeholderDetail: "",
    },
];

function getSeoWorkspaceById(workspaceId) {
    return SEO_WORKSPACES.find((item) => item.id === workspaceId) || SEO_WORKSPACES[0];
}

function getActiveSeoWorkspaceLabel() {
    return getSeoWorkspaceById(state.seo.activeWorkspaceId).name || "SEO workspace";
}

function getDefaultSearchConsoleProperty(workspaceId) {
    const workspace = getSeoWorkspaceById(workspaceId);
    if (workspace.id === "patent-drawing-experts") {
        return "sc-domain:patentdrawingexperts.com";
    }
    if (workspace.id === "ip-docketers") {
        return "sc-domain:your-domain.com";
    }
    if (workspace.id === "menteso") {
        return "sc-domain:your-domain.com";
    }
    return "";
}

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
    setInterval(async () => {
        if (state.selectedAgent?.ui_type !== "accountant_monitor") return;
        const changed = await loadAccountantDashboardData(state.selectedAgent.module_name);
        if (changed) renderMain();
    }, 3000);
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
        applyRunStatusSnapshot(data);
        if (name === "pct_agent" && data.status === "running") {
            startRunStatusPoller();
        }
        return state.agentRunStatus;
    } catch (e) {
        console.error("Failed to load agent run status:", e);
        state.agentRunStatus = "idle";
        return "idle";
    }
}

function applyRunStatusSnapshot(data) {
    if (!data || typeof data !== "object") return;
    if (data.lastEvent?.type === "complete" && state.isRunning) {
        state.lastResult = data.lastEvent.result || null;
        state.isRunning = false;
        state.stopRequested = false;
        state.agentRunStatus = "idle";
        state.browser.event = "done";
        if (state.runMetrics) state.runMetrics.finishedAt = Date.now();
        stopRunMetricsTicker();
    }
    const metrics = data.metrics || {};
    if (state.runMetrics && metrics) {
        const previousProcessed = state.runMetrics.processedRows || 0;
        if (Number(metrics.totalRows) > 0) state.runMetrics.totalRows = Number(metrics.totalRows);
        if (Number(metrics.processedRows) >= 0) state.runMetrics.processedRows = Number(metrics.processedRows);
        if (Number(metrics.foundRows) >= 0) state.runMetrics.foundRows = Number(metrics.foundRows);
        if (Number(metrics.notFoundRows) >= 0) state.runMetrics.notFoundRows = Number(metrics.notFoundRows);
        if (Number(metrics.errorRows) >= 0) state.runMetrics.errorRows = Number(metrics.errorRows);
        if (Number(metrics.captchaCount) >= 0) state.runMetrics.captchaCount = Number(metrics.captchaCount);
        const newProcessed = state.runMetrics.processedRows || 0;
        const delta = Math.max(0, newProcessed - previousProcessed);
        const now = Date.now();
        for (let i = 0; i < delta; i++) {
            pushRowCompletionTimestamp(now);
        }
        updateRunMetricsPanel();
    }
    if (data.browser && typeof data.browser === "object") {
        Object.assign(state.browser, data.browser);
        updateBrowserPreview();
    }
    if (Array.isArray(data.logs) && data.logs.length) {
        const existing = new Set(state.executionLog.map((line) => `${line.time}|${line.message}`));
        data.logs.forEach((line) => {
            const entry = {
                time: line.time || "",
                message: String(line.message || ""),
                type: line.type || classifyMessage(String(line.message || "")),
            };
            const key = `${entry.time}|${entry.message}`;
            if (entry.message && !existing.has(key)) {
                existing.add(key);
                state.executionLog.push(entry);
            }
        });
        if (state.executionLog.length > 220) {
            state.executionLog.splice(0, state.executionLog.length - 220);
        }
        const terminal = document.getElementById("terminal");
        if (terminal) {
            terminal.innerHTML = state.executionLog.map((l) => createTerminalLineHTML(l)).join("") + '<div class="terminal-cursor"></div>';
            terminal.scrollTop = terminal.scrollHeight;
        }
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

// ---------------------------------------------------------------------------
// Run Metrics — stopwatch + ETA + captcha tier breakdown
// ---------------------------------------------------------------------------
let runMetricsTickerId = null;
let runStatusPollerId = null;

function startRunMetricsTicker() {
    stopRunMetricsTicker();
    runMetricsTickerId = setInterval(() => {
        if (state.runMetrics) state.runMetrics.lastTickAt = Date.now();
        updateRunMetricsPanel();
    }, 1000);
    startRunStatusPoller();
}

function stopRunMetricsTicker() {
    if (runMetricsTickerId !== null) {
        clearInterval(runMetricsTickerId);
        runMetricsTickerId = null;
    }
    stopRunStatusPoller();
}

function startRunStatusPoller() {
    stopRunStatusPoller();
    runStatusPollerId = setInterval(async () => {
        if (!state.selectedAgent || (!state.isRunning && state.agentRunStatus !== "running" && state.agentRunStatus !== "stopping")) {
            return;
        }
        await loadAgentRunStatus(state.selectedAgent.module_name);
        renderMain();
    }, 2000);
}

function stopRunStatusPoller() {
    if (runStatusPollerId !== null) {
        clearInterval(runStatusPollerId);
        runStatusPollerId = null;
    }
}

function formatStopwatch(ms) {
    if (!ms || ms < 0) ms = 0;
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function computeRunMetricsView(rm) {
    const now = rm.finishedAt || Date.now();
    const elapsedMs = rm.startedAt ? Math.max(0, now - rm.startedAt) : 0;
    const elapsedSec = elapsedMs / 1000;

    const processed = rm.processedRows || 0;
    const total = rm.totalRows || 0;
    const remaining = Math.max(0, total - processed);

    // Rolling-window ETA: look at the last N row completions and use that
    // rate to project the remaining time. Avoids the "first captcha eats
    // 15s" skew that made the cumulative ETA say 16 hours. On mode change
    // the window is cleared so old-rate samples don't pollute the new
    // estimate.
    const samples = rm.rowTimestamps || [];
    const MIN_SAMPLES_FOR_ETA = 5;
    let ratePerMin = 0;
    let etaText = "—";

    // Mode-change-aware baseline: after a slider change the cumulative
    // fallback should measure from the change point, not from the run start.
    const baselineStart = rm.modeChangedAt || rm.startedAt;
    const baselineProcessed = (rm.processedRows || 0) - (rm.rowsAtModeChange || 0);
    const baselineElapsedSec = baselineStart ? Math.max(0, (now - baselineStart) / 1000) : 0;
    const isRecalibrating = !!rm.recalibrating;

    if (samples.length >= MIN_SAMPLES_FOR_ETA) {
        const first = samples[0];
        const last = samples[samples.length - 1];
        const windowMs = Math.max(1, last - first);
        const rowsInWindow = samples.length - 1; // intervals, not points
        ratePerMin = (rowsInWindow / windowMs) * 60_000;
        if (remaining > 0 && ratePerMin > 0) {
            const etaMs = (remaining / ratePerMin) * 60_000;
            etaText = formatStopwatch(etaMs);
        } else if (remaining === 0) {
            etaText = "0";
        }
        // Enough fresh samples — recalibration is complete.
        if (isRecalibrating) rm.recalibrating = false;
    } else if (baselineProcessed > 0 && baselineElapsedSec > 0) {
        // Not enough samples yet — use the post-mode-change baseline so
        // the rate shown is from THIS mode's work, not a stale average.
        ratePerMin = (baselineProcessed / baselineElapsedSec) * 60;
        etaText = remaining > 0
            ? (isRecalibrating ? "recalibrating…" : "calculating…")
            : "0";
    } else if (isRecalibrating) {
        etaText = "recalibrating…";
    } else if (processed > 0 && elapsedSec > 0) {
        // Fresh-run fallback before the very first row even completes.
        ratePerMin = (processed / elapsedSec) * 60;
        etaText = remaining > 0 ? "calculating…" : "0";
    }

    if (String(etaText).toLowerCase().includes("calculating")) etaText = "Calc";
    if (String(etaText).toLowerCase().includes("recalibrating")) etaText = "Recal";

    // Auto-solved vs manual breakdown
    const totals = rm.captchaTotals || {};
    const autoSolved =
        (totals.vision || 0) +
        (totals.openai || 0) +
        (totals.audio || 0) +
        (totals.diy || 0);
    const manualSolved = totals.manual || 0;

    // Throttle warning: high not_found rate after the warm-up window
    // means WIPO is rate-limiting us. Surface it in the UI so the user
    // knows to back off the speed level.
    const recentProcessed = processed - (rm.rowsAtModeChange || 0);
    const notFoundRate = recentProcessed > 0
        ? (rm.notFoundRows || 0) / Math.max(1, processed)
        : 0;
    const degraded = processed >= 20 && notFoundRate > 0.7;

    return {
        elapsedText: formatStopwatch(elapsedMs),
        etaText,
        ratePerMin: ratePerMin.toFixed(1),
        processed,
        degraded,
        notFoundRate,
        total,
        remaining,
        foundRows: rm.foundRows || 0,
        notFoundRows: rm.notFoundRows || 0,
        errorRows: rm.errorRows || 0,
        captchaCount: rm.captchaCount || 0,
        autoSolved,
        manualSolved,
        tiers: {
            vision: totals.vision || 0,
            openai: totals.openai || 0,
            audio: totals.audio || 0,
            diy: totals.diy || 0,
            manual: totals.manual || 0,
            other: totals.other || 0,
        },
        running: !rm.finishedAt && state.isRunning,
    };
}

function renderRunMetricsPanel() {
    if (!state.runMetrics || !state.runMetrics.startedAt) {
        return "";
    }
    const v = computeRunMetricsView(state.runMetrics);
    const progressPct = v.total > 0
        ? Math.min(100, Math.round((v.processed / v.total) * 100))
        : 0;
    const warningBar = v.degraded
        ? `<div class="run-metrics-warning">
              ⚠ High not_found rate (${Math.round(v.notFoundRate * 100)}%) —
              WIPO may be rate-limiting. The retry pass will re-scrape these rows once the main run finishes.
           </div>`
        : "";
    return `
        <div class="run-metrics-panel" id="run-metrics-panel">
            ${warningBar}
            <div class="run-metrics-grid">
                <div class="run-metrics-stopwatch">
                    <div class="run-metrics-label">${v.running ? "ELAPSED" : "FINAL TIME"}</div>
                    <div class="run-metrics-stopwatch-value" id="rm-elapsed">${v.elapsedText}</div>
                    <div class="run-metrics-sub">
                        <span id="rm-rate">${v.ratePerMin}</span> rows/min
                    </div>
                </div>
                <div class="run-metrics-block">
                    <div class="run-metrics-label">ETA</div>
                    <div class="run-metrics-eta-value" id="rm-eta">${v.etaText}</div>
                    <div class="run-metrics-sub"><span id="rm-remaining">${v.remaining}</span> rows left</div>
                </div>
                <div class="run-metrics-block">
                    <div class="run-metrics-label">PROGRESS</div>
                    <div class="run-metrics-eta-value">
                        <span id="rm-processed">${v.processed}</span>
                        <span class="run-metrics-fraction">/ <span id="rm-total">${v.total}</span></span>
                    </div>
                    <div class="run-metrics-progress-bar">
                        <div class="run-metrics-progress-fill" id="rm-progress" style="width:${progressPct}%"></div>
                    </div>
                </div>
                <div class="run-metrics-block">
                    <div class="run-metrics-label">CAPTCHAS SOLVED</div>
                    <div class="run-metrics-eta-value" id="rm-captcha-count">${v.captchaCount}</div>
                    <div class="run-metrics-tier-row">
                        <span class="rm-tier-badge rm-tier-auto" title="GPT-4o Vision / OCR / Whisper"
                              id="rm-tier-auto">Auto&nbsp;${v.autoSolved}</span>
                        <span class="rm-tier-badge rm-tier-manual" title="Solved by human"
                              id="rm-tier-manual">Manual&nbsp;${v.manualSolved}</span>
                    </div>
                </div>
            </div>
            <div class="run-metrics-tiers-detail" id="rm-tiers-detail">
                ${renderTierBreakdown(v.tiers)}
                ${renderFastModeSlider()}
            </div>
        </div>
    `;
}

function renderFastModeSlider() {
    // Slider removed: PCT agent now always runs at L5 Max. The backend
    // (resolve_fast_level in agents/pct_agent/agent.py) ignores any value
    // a leftover client might still POST.
    return "";
}

function onFastModeSlide(rawValue) {
    // Live preview while dragging — show the new emoji/label without
    // hitting the network on every pixel.
    const lvl = Math.max(1, Math.min(5, parseInt(rawValue, 10) || 1));
    const profile = (typeof FAST_LEVELS !== "undefined" ? FAST_LEVELS[lvl] : state.fastModeLevels[lvl]);
    if (!profile) return;
    const label = document.getElementById("rm-fastmode-current");
    if (label) {
        label.innerHTML = `${profile.emoji} <strong>L${lvl}</strong> ${esc(profile.label)}`;
    }
    const wrap = document.getElementById("rm-fastmode-wrap");
    if (wrap) wrap.title = profile.hint;
}

async function onFastModeCommit(rawValue) {
    const lvl = Math.max(1, Math.min(5, parseInt(rawValue, 10) || 1));
    const previous = state.fastLevel;
    state.fastLevel = lvl;
    try { localStorage.setItem("menteso-fast-level", String(lvl)); } catch {}

    const profile = (typeof FAST_LEVELS !== "undefined" ? FAST_LEVELS[lvl] : state.fastModeLevels[lvl]);

    // Also sync the OTHER slider (the chip near the Run button) so both
    // controls show the same value.
    const otherSlider = document.getElementById("fast-mode-slider");
    if (otherSlider && otherSlider.value !== String(lvl)) {
        otherSlider.value = String(lvl);
    }

    // If the agent isn't running, the level applies on the next run.
    if (!state.isRunning || !state.selectedAgent) {
        addLogLine(
            `[Mode] Scraping speed set to ${profile.emoji} L${lvl} ${profile.label} ` +
            `— applies on the next run`,
            "step",
        );
        if (state.runMetrics) updateRunMetricsPanel();
        return;
    }

    if (state.runMetrics) {
        state.runMetrics.fastLevelChanging = true;
        updateRunMetricsPanel();
    }
    try {
        const res = await fetch(
            `/api/agents/${state.selectedAgent.module_name}/fast-level`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ level: lvl }),
            },
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        addLogLine(
            `[Mode] Live upgrade to ${profile.emoji} L${lvl} ${profile.label} ` +
            `— takes effect on the next chunk. Recomputing ETA from the new rate…`,
            "success",
        );
        // Reset the rolling window so the ETA reflects the NEW rate within
        // a few rows, rather than averaging old (slow) + new (fast) rates.
        if (state.runMetrics && lvl !== previous) {
            resetRunMetricsForModeChange();
        }
    } catch (e) {
        state.fastLevel = previous;
        try { localStorage.setItem("menteso-fast-level", String(previous)); } catch {}
        addLogLine(`[Mode] Could not update speed level: ${e.message}`, "error");
    } finally {
        if (state.runMetrics) {
            state.runMetrics.fastLevelChanging = false;
            updateRunMetricsPanel();
        }
    }
}

function resetRunMetricsForModeChange() {
    const rm = state.runMetrics;
    if (!rm) return;
    rm.rowTimestamps = [];
    rm.modeChangedAt = Date.now();
    rm.rowsAtModeChange = rm.processedRows || 0;
    rm.recalibrating = true;
}

function renderTierBreakdown(tiers) {
    const labels = {
        vision: "Vision (GPT-4o)",
        openai: "OpenAI",
        audio: "Whisper Audio",
        diy: "DIY OCR",
        manual: "Manual",
        other: "Other",
    };
    const parts = [];
    for (const [key, label] of Object.entries(labels)) {
        const n = tiers[key] || 0;
        if (n === 0) continue;
        parts.push(
            `<span class="rm-tier-chip"><span class="rm-tier-chip-label">${label}</span>` +
            `<span class="rm-tier-chip-count">${n}</span></span>`
        );
    }
    if (parts.length === 0) {
        return `<span class="rm-tier-empty">No captchas hit yet</span>`;
    }
    return parts.join("");
}

function updateRunMetricsPanel() {
    const panel = document.getElementById("run-metrics-panel");
    if (!panel || !state.runMetrics || !state.runMetrics.startedAt) return;
    const v = computeRunMetricsView(state.runMetrics);
    const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };
    setText("rm-elapsed", v.elapsedText);
    setText("rm-rate", v.ratePerMin);
    setText("rm-eta", v.etaText);
    setText("rm-remaining", String(v.remaining));
    setText("rm-processed", String(v.processed));
    setText("rm-total", String(v.total));
    setText("rm-captcha-count", String(v.captchaCount));
    setText("rm-tier-auto", `Auto ${v.autoSolved}`);
    setText("rm-tier-manual", `Manual ${v.manualSolved}`);
    const bar = document.getElementById("rm-progress");
    if (bar) {
        const pct = v.total > 0
            ? Math.min(100, Math.round((v.processed / v.total) * 100))
            : 0;
        bar.style.width = `${pct}%`;
    }
    const tiersEl = document.getElementById("rm-tiers-detail");
    if (tiersEl) {
        tiersEl.innerHTML =
            renderTierBreakdown(v.tiers) +
            renderFastModeSlider();
    }

    const label = panel.querySelector(".run-metrics-stopwatch .run-metrics-label");
    if (label) label.textContent = v.running ? "ELAPSED" : "FINAL TIME";

    // Keep the Scraping Browser extraction tally in sync on every stats tick.
    updateExtractSummary();
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

async function forceClearAgent(name) {
    const res = await fetch(`/api/agents/${name}/force-clear`, { method: "POST" });
    return await res.json();
}

async function saveGoogleSearchConsoleConfig() {
    const workspaceId = state.seo.activeWorkspaceId || "patentzoom";
    const res = await fetch("/api/google/search-console/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            workspace_id: workspaceId,
            client_id: state.seo.google.clientId.trim(),
            client_secret: state.seo.google.clientSecret.trim(),
            property: state.seo.google.property.trim() || getDefaultSearchConsoleProperty(workspaceId),
        }),
    });
    return await res.json();
}

async function launchGoogleBrowserSession() {
    const workspaceId = encodeURIComponent(state.seo.activeWorkspaceId || "patentzoom");
    const res = await fetch(`/api/google/search-console/browser-session?workspace_id=${workspaceId}`, {
        method: "POST",
    });
    return await res.json();
}

async function requestGoogleIndexing(url) {
    const res = await fetch("/api/google/search-console/request-indexing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            url,
            workspace_id: state.seo.activeWorkspaceId || "patentzoom",
        }),
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
    state.runMetrics = {
        startedAt: Date.now(),
        finishedAt: null,
        totalRows: 0,
        processedRows: 0,
        foundRows: 0,
        notFoundRows: 0,
        errorRows: 0,
        captchaTotals: { vision: 0, openai: 0, audio: 0, diy: 0, manual: 0, other: 0 },
        captchaCount: 0,
        lastTickAt: Date.now(),
        fastLevel: (state.runMetrics && state.runMetrics.fastLevel) || 1,
        fastLevelChanging: false,
        rowTimestamps: [],
        modeChangedAt: null,
        rowsAtModeChange: 0,
        recalibrating: false,
    };
    startRunMetricsTicker();
    if (state.selectedAgent?.ui_type === "seo_posting") {
        resetSeoWorkflow();
        handleSeoWorkflowEvent({
            type: "step",
            message: `Preparing a new ${getActiveSeoWorkspaceLabel()} run.`,
            data: { stage: "readiness", status: "active" },
        }, "step");
    }
    renderMain();

    const method = params.method || "GET";
    const queryParams = params.query || {};
    if (params.file_path) queryParams.file_path = params.file_path;
    if (params.mode) queryParams.mode = params.mode;
    if (params.gazette) queryParams.gazette = params.gazette;
    if (params.fast_level !== undefined && params.fast_level !== null) {
        queryParams.fast_level = params.fast_level;
    }

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
            if (state.runMetrics) state.runMetrics.finishedAt = Date.now();
            stopRunMetricsTicker();
            updateBrowserPreview();
            updateRunMetricsPanel();
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
    if (state.runMetrics) {
        state.runMetrics.finishedAt = Date.now();
    }
    stopRunMetricsTicker();
    updateBrowserPreview();
    updateRunMetricsPanel();

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
    } else if (data.type === "fast_level_changed") {
        // Server confirms the new level; sync local state in case another
        // client or session changed it.
        const lvl = Math.max(1, Math.min(5, parseInt(data.level, 10) || 1));
        if (state.runMetrics && state.runMetrics.fastLevel !== lvl) {
            state.runMetrics.fastLevel = lvl;
            state.fastLevel = lvl;
            // Reset rolling window so ETA recomputes from the new rate.
            resetRunMetricsForModeChange();
            updateRunMetricsPanel();
        }
    }
}

function handlePipelineStats(data) {
    state.pipelineMode = true;
    state.pipeline = data;
    // Pool/parallel mode reports row counts through this snapshot, not via
    // per-row browser events. Mirror them into runMetrics so the stopwatch
    // panel works in both modes.
    if (state.runMetrics) {
        if (typeof data.total === "number" && data.total > 0) {
            state.runMetrics.totalRows = data.total;
        }
        const completed = (data.found || 0) + (data.not_found || 0) + (data.errors || 0);
        const previouslyProcessed = state.runMetrics.processedRows;
        const newlyProcessed = Math.max(0, completed - previouslyProcessed);
        state.runMetrics.processedRows = completed;
        state.runMetrics.foundRows = data.found || 0;
        state.runMetrics.notFoundRows = data.not_found || 0;
        state.runMetrics.errorRows = data.errors || 0;
        // Snapshots arrive every ~2s; record an approximate row completion
        // timestamp for each new row so the rolling-window ETA still works.
        const now = Date.now();
        for (let i = 0; i < newlyProcessed; i++) {
            pushRowCompletionTimestamp(now);
        }
    }
    updatePipelinePanel();
    updateRunMetricsPanel();
}

function pushRowCompletionTimestamp(ts) {
    const rm = state.runMetrics;
    if (!rm) return;
    rm.rowTimestamps.push(ts || Date.now());
    // Keep only the last 100 samples — enough for a stable rolling rate,
    // small enough to stay light on memory.
    const MAX_SAMPLES = 100;
    if (rm.rowTimestamps.length > MAX_SAMPLES) {
        rm.rowTimestamps.splice(0, rm.rowTimestamps.length - MAX_SAMPLES);
    }
}

// Browser events that prove the agent is actively making progress past the
// captcha point — if any of these arrive while the banner is up, the captcha
// is definitively gone and we drop the alert immediately.
const CAPTCHA_PROGRESS_EVENTS = new Set([
    "navigate",
    "extracting",
    "contacts",
    "pdf_found",
    "no_pdf",
    "downloading",
    "done",
]);

function handleBrowserEvent(data) {
    Object.assign(state.browser, data);

    // --- Run metrics: tier-attribution & row-progress accounting ---
    if (state.runMetrics) {
        if (typeof data.total === "number" && data.total > 0) {
            state.runMetrics.totalRows = data.total;
        }
        if (data.event === "solver_succeeded") {
            const tier = (data.tier || "other").toLowerCase();
            const totals = state.runMetrics.captchaTotals;
            if (totals[tier] === undefined) totals[tier] = 0;
            totals[tier] += 1;
            state.runMetrics.captchaCount += 1;
            updateRunMetricsPanel();
        }
        // contacts is the per-row terminal event in headed sequential mode;
        // in pool mode pipeline stats provide processed counts.
        if (data.event === "contacts") {
            state.runMetrics.processedRows += 1;
            if (data.status === "found") state.runMetrics.foundRows += 1;
            else if (data.status === "not_found") state.runMetrics.notFoundRows += 1;
            else state.runMetrics.errorRows += 1;
            pushRowCompletionTimestamp();
            updateRunMetricsPanel();
        } else if (data.event === "no_pdf") {
            state.runMetrics.processedRows += 1;
            state.runMetrics.notFoundRows += 1;
            pushRowCompletionTimestamp();
            updateRunMetricsPanel();
        }
    }

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
    } else if (state.captcha.active && CAPTCHA_PROGRESS_EVENTS.has(data.event)) {
        // Safety net: a stale banner can happen if the captcha-cleared event
        // is missed (network blip, agent moved on). Any forward-progress
        // browser event proves the agent is past the challenge.
        state.captcha.active = false;
        state.captcha.resolvedMessage = "CAPTCHA cleared - resuming from the same row";
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

function parseSeoTopicOverrideCommand(rawValue) {
    const source = String(rawValue || "").trim();
    if (!source) {
        return { topicOverride: undefined, bypassDailyLimit: false };
    }

    const commandPattern = /^\/bypass-daily-limit(?:\s+|:\s*|-)?/i;
    if (!commandPattern.test(source)) {
        return { topicOverride: source, bypassDailyLimit: false };
    }

    const stripped = source.replace(commandPattern, "").trim();
    return {
        topicOverride: stripped || undefined,
        bypassDailyLimit: true,
    };
}

function triggerSeoRun(agent, overrides = {}) {
    const parsedTopicOverride = parseSeoTopicOverrideCommand(state.seo.topicOverride);
    runAgent(agent.module_name, {
        method: "POST",
        body: {
            workspace_id: state.seo.activeWorkspaceId || "patentzoom",
            topic_override: parsedTopicOverride.topicOverride,
            publish_override: overrides.publish_override || state.seo.publishOverride,
            enable_featured_image: overrides.enable_featured_image ?? state.seo.enableFeaturedImage,
            dry_run: overrides.dry_run ?? state.seo.dryRun,
            bypass_daily_limit: parsedTopicOverride.bypassDailyLimit,
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
// Always-visible extraction tally in the Scraping Browser panel, aggregated
// across ALL parallel tabs (not just whichever one flashed last). This is the
// reliable answer to "how many extracted vs not". Driven by runMetrics so it
// refreshes on every stats tick, independent of per-tab browser events.
function updateExtractSummary() {
    const summaryEl = document.getElementById("browser-extract-summary");
    if (!summaryEl) return;
    const rm = state.runMetrics || {};
    const found = rm.foundRows || 0;
    const notFound = rm.notFoundRows || 0;
    const errors = rm.errorRows || 0;
    const processed = rm.processedRows || (found + notFound + errors);
    const total = rm.totalRows || 0;
    const rate = processed > 0 ? Math.round((found / processed) * 100) : 0;
    summaryEl.innerHTML = `
        <div class="bxs-cell bxs-found" title="Contacts extracted">
            <span class="bxs-value">${found}</span><span class="bxs-label">Extracted</span>
        </div>
        <div class="bxs-cell bxs-not" title="Processed but no contact found">
            <span class="bxs-value">${notFound}</span><span class="bxs-label">Not extracted</span>
        </div>
        <div class="bxs-cell bxs-err" title="Errors / captcha-blocked">
            <span class="bxs-value">${errors}</span><span class="bxs-label">Errors</span>
        </div>
        <div class="bxs-cell bxs-prog" title="Rows processed of total">
            <span class="bxs-value">${processed}${total ? `/${total}` : ""}</span><span class="bxs-label">Processed${rate ? ` · ${rate}% hit` : ""}</span>
        </div>
    `;
}

function updateBrowserPreview() {
    const urlBar = document.getElementById("browser-url");
    const statusEl = document.getElementById("browser-status");
    const content = document.getElementById("browser-content");
    if (!urlBar || !content) return;

    const b = state.browser;

    updateExtractSummary();

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
    renderSidebarFlat();
    renderMain();
}

function getActiveSeoWorkspace() {
    const workspace = getSeoWorkspaceById(state.seo.activeWorkspaceId);
    if (state.seo.activeWorkspaceId !== workspace.id) {
        state.seo.activeWorkspaceId = workspace.id;
    }
    return workspace;
}

function renderSeoWorkspaceTabs() {
    const activeWorkspace = getActiveSeoWorkspace();
    return `
        <div class="seo-workspace-switcher">
            <div class="seo-workspace-tabs">
                ${SEO_WORKSPACES.map((workspace) => `
                    <button
                        type="button"
                        class="seo-workspace-chip ${workspace.id === activeWorkspace.id ? "active" : ""}"
                        data-seo-workspace="${esc(workspace.id)}"
                        aria-pressed="${workspace.id === activeWorkspace.id ? "true" : "false"}"
                    >
                        ${esc(workspace.name)}
                    </button>
                `).join("")}
            </div>
        </div>
    `;
}

function renderSeoWorkspacePlaceholder(workspace) {
    return `
        <div class="seo-dashboard-shell">
            <div class="section-title">SEO Posting Agent Dashboard</div>
            <div class="seo-panel-grid">
                <div class="result-card seo-workspace-placeholder-card">
                    <div class="seo-card-header">
                        <h4>${esc(workspace.name)}</h4>
                        <span class="seo-status-pill blocked">Setup in progress</span>
                    </div>
                    <div class="seo-slot-title">${esc(workspace.placeholderTitle || "Dashboard Coming Soon")}</div>
                    <div class="seo-slot-meta">${esc(workspace.placeholderMessage || "Agent setup in progress.")}</div>
                    <div class="memory-empty seo-workspace-placeholder-copy">
                        ${esc(workspace.placeholderDetail || "This dashboard will appear here once the workflow is connected.")}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function getSeoWorkspaceStats(agent, workspace, stats, rate, rateClass) {
    if (!workspace || workspace.kind === "live") {
        const snapshot = state.seoDashboard.snapshot || {};
        const snapshotWorkspaceId = snapshot?.workspace?.id || "";
        const workspaceStats = snapshotWorkspaceId === (workspace?.id || "") ? (snapshot?.summary?.workspaceStats || {}) : null;
        const totalRuns = workspaceStats?.total_runs ?? stats.total_runs ?? 0;
        const successRateRaw = workspaceStats?.success_rate ?? rate;
        const avgExecutionTime = workspaceStats?.avg_execution_time ?? stats.avg_execution_time ?? 0;
        const successClass = successRateRaw >= 0.8 ? "success" : successRateRaw >= 0.5 ? "warning" : successRateRaw > 0 ? "error" : "";
        return {
            totalRuns,
            successRate: formatPercent(successRateRaw),
            successRateClass: successClass || rateClass,
            avgTime: `${Number(avgExecutionTime || 0).toFixed(2)}s`,
            status: (agent.status || "idle").toUpperCase(),
            statusClass: "success",
        };
    }

    return {
        totalRuns: "--",
        successRate: "--",
        successRateClass: "",
        avgTime: "--",
        status: "SETUP",
        statusClass: "warning",
    };
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
                } else if ((detail || agent).ui_type === "accountant_monitor") {
                    await loadAccountantDashboardData(agent.module_name);
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

function renderSidebarFlat() {
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
            state.inputMode = "upload";
            state.uploadedFilePath = null;
            state.pipelineMode = false;
            state.pipeline = null;
            resetCaptchaAlert();
            state.browser.event = "idle";
            await loadAgentRunStatus(agent.module_name);
            if ((detail || agent).ui_type === "seo_posting") {
                state.seo.activeWorkspaceId = "patent-drawing-experts";
                state.seoDashboard.previewArticle = null;
                state.seoDashboard.historyEntry = null;
                await loadSeoDashboardData(agent.module_name);
            } else if ((detail || agent).ui_type === "accountant_monitor") {
                await loadAccountantDashboardData(agent.module_name);
            } else {
                state.seoDashboard.snapshot = null;
                state.seoDashboard.error = "";
                state.seoDashboard.previewArticle = null;
                state.seoDashboard.historyEntry = null;
                resetSeoWorkflow([]);
            }
            render();
        };
        listEl.appendChild(item);
    });
}

function renderInvoiceRequestSection() {
    const data = state.accountantDashboard.snapshot;
    if (state.accountantDashboard.loading) {
        return '<div class="input-section"><div class="input-card">Loading live AccountantAgent status...</div></div>';
    }
    if (!data) {
        return `<div class="input-section"><div class="input-card"><div class="seo-note-title">Status unavailable</div><div class="seo-note-text">${esc(state.accountantDashboard.error || "No runtime status has been published yet.")}</div></div></div>`;
    }
    const stages = [
        ["sleeping", "Sleeping"], ["wake_up", "Wake Up"], ["mail_check", "Check Mail"],
        ["mail_found", "Mail Found"], ["parsing", "Read Request"],
        ["zoho_lookup", "Find Details"], ["routing", "Choose Company"],
        ["creating_invoice", "Create Invoice"], ["sending_email", "Send Email"],
        ["complete", "Complete"],
    ];
    const activeIndex = Math.max(0, stages.findIndex(([key]) => key === data.stage));
    return `
        <div class="input-section">
            <div class="input-card">
                <div class="section-title">Live AWS Runtime</div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-value ${data.live ? "success" : "error"}">${data.live ? "LIVE" : "STALE"}</div><div class="stat-label">Runtime</div></div>
                    <div class="stat-card"><div class="stat-value">${esc(String(data.processed || 0))}</div><div class="stat-label">Last Run Processed</div></div>
                    <div class="stat-card"><div class="stat-value">${esc(String(data.skipped || 0))}</div><div class="stat-label">Last Run Skipped</div></div>
                    <div class="stat-card"><div class="stat-value ${Number(data.failed || 0) ? "error" : "success"}">${esc(String(data.failed || 0))}</div><div class="stat-label">Last Run Failed</div></div>
                </div>
                <div class="seo-note-text">Schedule: ${esc(data.schedule || "Every 2 minutes")} · Runtime: ${esc(data.runtime || "ec2-systemd")} · Last check: ${esc(formatTimestamp(data.lastRun || ""))}</div>
                <div class="seo-note-text">Automatic workflow: Gmail intake → PID parsing → Zoho validation → Wave invoice → threaded reply with PDF.</div>
                <div class="section-title" style="margin-top:24px">Current Stage</div>
                <div class="seo-note-text" style="margin-bottom:14px"><strong>${esc(data.message || "Waiting for mail")}</strong></div>
                <div class="sub-agents-list">
                    ${stages.map(([key, label], index) => {
                        const stateClass = key === data.stage ? "ready" : (data.stage !== "sleeping" && index < activeIndex ? "ready" : "");
                        return `<span class="sub-agent-chip ${stateClass}">${key === data.stage ? "● " : ""}${esc(label)}</span>`;
                    }).join("")}
                </div>
            </div>
        </div>`;
}

function renderReminderAgentSection(data) {
    const reminder = data.reminder || {};
    const customers = reminder.customers || [];
    const sentEmails = reminder.sentEmails || [];
    const agentCollection = Object.entries(reminder.agentCollectionTotals || {})
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([currency, amount]) => `${Number(amount || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${currency}`)
        .join(" + ") || "0.00";
    const selected = customers.find(row => row.customer_id === state.accountantDashboard.selectedReminderCustomer);
    const drawer = selected ? `<div onclick="closeReminderDrawer()" style="position:fixed;inset:0;background:#0f172a55;z-index:9998"></div>
        <aside style="position:fixed;right:0;top:0;height:100vh;width:min(480px,92vw);background:var(--card-bg,#fff);z-index:9999;box-shadow:-12px 0 35px #0003;padding:24px;overflow:auto">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:start"><div><div class="section-title">${esc(selected.customer || "Client details")}</div><div class="seo-note-text">${esc(selected.email || "")}</div></div><button class="secondary-btn" onclick="closeReminderDrawer()" aria-label="Close">✕</button></div>
        <div class="stats-grid" style="margin-top:20px"><div class="stat-card"><div class="stat-value">${esc(String(selected.invoice_count || 0))}</div><div class="stat-label">Invoices</div></div><div class="stat-card"><div class="stat-value">${esc(Number(selected.total_due || 0).toFixed(2))}</div><div class="stat-label">${esc(selected.currency || "")} due</div></div></div>
        <div class="input-card" style="margin-top:16px"><div><strong>Status</strong><div>${esc(selected.status || "")}</div></div><hr><div><strong>Invoice numbers</strong><div>${esc((selected.invoice_numbers || []).join(", "))}</div></div><hr><div><strong>Oldest due date</strong><div>${esc(selected.oldest_due_date || "")}</div></div><hr><div><strong>Last reminder sent</strong><div>${esc(formatTimestamp(selected.last_live_sent_at || "") || "Not sent")}</div></div><hr><div><strong>Next reminder</strong><div>${esc(selected.reminder_type === "multiple" ? "Stopped" : (formatTimestamp(selected.next_follow_up || "") || "Not scheduled"))}</div></div><hr><div><strong>Latest client activity</strong><div>${esc((selected.last_activity || "No action").replaceAll("_", " "))}</div><div class="seo-note-text">${esc(formatTimestamp(selected.last_activity_at || ""))}</div><div>${esc(selected.last_activity_detail || "")}</div></div></div>
        </aside>` : "";
    return `<div class="input-section"><div class="input-card">
        <div class="section-title">Invoice Reminder Agent</div>
        <div class="collection-summary-card">
            <div class="collection-summary-title"><strong>Overdue Collections</strong><span>Automatically refreshed from Wave</span></div>
            <div class="collection-summary-metrics">
                <div><span>Total overdue in Wave</span><strong>${esc(String(reminder.overdueTotal || 0))}</strong></div>
                <div><span>Wave reminders</span><strong>${esc(String(reminder.waveReminderInvoices || 0))}</strong></div>
                <div><span>Agent reminders</span><strong>${esc(String(reminder.agentReminderInvoices || 0))}</strong></div>
                <div><span>Missing email</span><strong>${esc(String(reminder.missingEmailInvoices || 0))}</strong></div>
                <div><span>Agent-owned collection</span><strong>${esc(agentCollection)}</strong></div>
            </div>
            <div class="collection-summary-status">Delivery: <strong>${esc(String(reminder.mode || "test").toUpperCase())}</strong><span>Scheduler: <strong class="${reminder.paused ? "error" : "success"}">${reminder.paused ? "PAUSED" : "ACTIVE"}</strong></span></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin:18px 0 10px">
            <div class="seo-note-text">Last Wave scan: ${esc(formatTimestamp(reminder.lastScanAt || ""))}</div>
            <button class="secondary-btn" onclick="setReminderPause('', ${reminder.paused ? "false" : "true"})">${reminder.paused ? "Resume all" : "Pause all"}</button>
        </div>
        <div id="reminder-table-scroll" onscroll="state.accountantDashboard.tableScrollLeft=this.scrollLeft" style="overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch;scrollbar-gutter:stable"><table style="width:100%;min-width:1320px;border-collapse:collapse;font-size:13px;white-space:nowrap">
            <thead><tr><th style="text-align:left;padding:9px">Client</th><th style="text-align:left;padding:9px">Email</th><th style="text-align:right;padding:9px">Invoices</th><th style="text-align:right;padding:9px">Total due</th><th style="text-align:left;padding:9px">Oldest due</th><th style="text-align:left;padding:9px">Last sent</th><th style="text-align:left;padding:9px">Next sent</th><th style="text-align:left;padding:9px">Client activity</th><th style="text-align:left;padding:9px">Status</th><th style="padding:9px">Control</th></tr></thead>
            <tbody>${customers.map(row => `<tr onclick="openReminderDrawer('${esc(row.customer_id || "")}')" style="border-top:1px solid var(--border-color);cursor:pointer">
                <td style="padding:9px"><strong>${esc(row.customer || "")}</strong><div class="seo-note-text">${esc((row.invoice_numbers || []).join(", "))}</div></td>
                <td style="padding:9px">${esc(row.email || "")}</td>
                <td style="padding:9px;text-align:right">${esc(String(row.invoice_count || 0))}</td>
                <td style="padding:9px;text-align:right">${esc(Number(row.total_due || 0).toFixed(2))} ${esc(row.currency || "")}</td>
                <td style="padding:9px">${esc(row.oldest_due_date || "")}</td>
                <td style="padding:9px">${esc(formatTimestamp(row.last_live_sent_at || ""))}</td>
                <td style="padding:9px">${esc(row.reminder_type === "multiple" ? "Stopped" : formatTimestamp(row.next_follow_up || ""))}</td>
                <td style="padding:9px"><strong>${esc((row.last_activity || "No action").replaceAll("_", " "))}</strong><div class="seo-note-text">${esc(formatTimestamp(row.last_activity_at || ""))}</div></td>
                <td style="padding:9px"><span class="sub-agent-chip ${row.status === "paused" ? "" : "ready"}">${esc(row.status || "")}</span></td>
                <td style="padding:9px;text-align:center">${row.reminder_type === "multiple" ? '<button class="secondary-btn" disabled title="Multiple-invoice reminders are stopped">⏸</button>' : `<button class="secondary-btn" style="min-width:40px" title="${row.status === "paused" ? "Resume reminders" : "Pause reminders"}" aria-label="${row.status === "paused" ? "Resume reminders" : "Pause reminders"}" onclick="event.stopPropagation();setReminderPause('${esc(row.customer_id || "")}', ${row.status === "paused" ? "false" : "true"})">${row.status === "paused" ? "▶" : "⏸"}</button>`}</td>
            </tr>`).join("") || '<tr><td colspan="10" style="padding:18px">No eligible overdue clients found.</td></tr>'}</tbody>
        </table></div>
        <div class="section-title" style="margin-top:24px">Agent Sent Emails</div>
        <div class="seo-note-text" style="margin-bottom:10px">Messages sent through Amazon SES. Human Gmail messages remain in Gmail Sent.</div>
        <div style="overflow-x:auto"><table style="width:100%;min-width:900px;border-collapse:collapse;font-size:13px;white-space:nowrap">
            <thead><tr><th style="text-align:left;padding:9px">Sent (IST)</th><th style="text-align:left;padding:9px">From</th><th style="text-align:left;padding:9px">To</th><th style="text-align:left;padding:9px">Subject</th><th style="text-align:left;padding:9px">Type</th><th style="text-align:left;padding:9px">SES status</th></tr></thead>
            <tbody>${sentEmails.map(mail => `<tr style="border-top:1px solid var(--border-color)"><td style="padding:9px">${esc(formatTimestamp(mail.sent_at || ""))}</td><td style="padding:9px">${esc(mail.from || "")}</td><td style="padding:9px">${esc((mail.recipients || []).join(", "))}</td><td style="padding:9px">${esc(mail.subject || "")}</td><td style="padding:9px">${esc((mail.kind || "").replaceAll("_", " "))}</td><td style="padding:9px"><span class="sub-agent-chip ready">${esc(mail.status || "sent")}</span></td></tr>`).join("") || '<tr><td colspan="6" style="padding:18px">No agent email has been sent through SES yet.</td></tr>'}</tbody>
        </table></div>
    </div></div>${drawer}`;
}

function openReminderDrawer(customerId) {
    state.accountantDashboard.selectedReminderCustomer = customerId;
    render();
}

function closeReminderDrawer() {
    state.accountantDashboard.selectedReminderCustomer = "";
    render();
}

function renderAccountantOverviewSection() {
    const data = state.accountantDashboard.snapshot;
    if (state.accountantDashboard.loading || !data) return renderInvoiceRequestSection();
    const view = state.accountantDashboard.view || "invoice_request";
    return `<div class="input-section"><div class="sub-agents-list" style="margin-bottom:14px">
        <button class="sub-agent-chip ${view === "invoice_request" ? "ready" : ""}" onclick="setAccountantView('invoice_request')">Invoice Request Agent</button>
        <button class="sub-agent-chip ${view === "invoice_reminder" ? "ready" : ""}" onclick="setAccountantView('invoice_reminder')">Invoice Reminder Agent</button>
    </div></div>${view === "invoice_reminder" ? renderReminderAgentSection(data) : renderInvoiceRequestSection()}`;
}

function setAccountantView(view) {
    state.accountantDashboard.view = view;
    render();
}

async function setReminderPause(customerId, paused) {
    const response = await fetch('/api/accountant/reminders/control', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: paused ? 'pause' : 'resume', customer_id: customerId}),
    });
    const result = await response.json();
    if (!response.ok) { alert(result.error || 'Unable to update reminder control'); return; }
    await loadAccountantDashboardData('accountant_agent');
    render();
}

async function loadAccountantDashboardData(name = "accountant_agent") {
    state.accountantDashboard.loading = true;
    state.accountantDashboard.error = "";
    try {
        const response = await fetch(`/api/agents/${name}/dashboard-data`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to load AccountantAgent status");
        const fingerprint = JSON.stringify(data);
        const changed = fingerprint !== state.accountantDashboard.snapshotFingerprint;
        state.accountantDashboard.snapshot = data;
        state.accountantDashboard.snapshotFingerprint = fingerprint;
        return changed;
    } catch (error) {
        state.accountantDashboard.snapshot = null;
        state.accountantDashboard.error = error.message || "Failed to load AccountantAgent status";
        return true;
    } finally {
        state.accountantDashboard.loading = false;
    }
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
    const isAccountantAgent = agent.ui_type === "accountant_monitor";
    const activeSeoWorkspace = isSeoAgent ? getActiveSeoWorkspace() : null;
    const isLiveSeoWorkspace = !!activeSeoWorkspace && activeSeoWorkspace.kind === "live";
    const workspaceStats = isSeoAgent
        ? getSeoWorkspaceStats(agent, activeSeoWorkspace, stats, rate, rateClass)
        : {
            totalRuns: stats.total_runs || 0,
            successRate: formatPercent(rate),
            successRateClass: rateClass,
            avgTime: `${(stats.avg_execution_time || 0).toFixed(2)}s`,
            status: (agent.status || "idle").toUpperCase(),
            statusClass: "success",
        };

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
                ${agent.hosted_on === "aws" ? '<span class="badge badge-role">AWS Hosted</span>' : ""}
            </div>
            ${isSeoAgent ? renderSeoWorkspaceTabs() : ""}
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
                <div class="stat-value">${esc(String(workspaceStats.totalRuns))}</div>
                <div class="stat-label">Total Runs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value ${workspaceStats.successRateClass}">${esc(String(workspaceStats.successRate))}</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${esc(String(workspaceStats.avgTime))}</div>
                <div class="stat-label">Avg Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-value ${workspaceStats.statusClass}" style="font-size:18px">${esc(String(workspaceStats.status))}</div>
                <div class="stat-label">Status</div>
            </div>
        </div>
    `;

    if (isSeoAgent && isLiveSeoWorkspace) {
        html += renderSEOOverviewSection();
    } else if (isSeoAgent) {
        html += renderSeoWorkspacePlaceholder(activeSeoWorkspace);
    } else if (isAccountantAgent) {
        html += renderAccountantOverviewSection();
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
    if (isSeoAgent && isLiveSeoWorkspace) {
        html += renderSEOInputSection(agent);
    } else if (isSeoAgent) {
        html += `
            <div class="input-section">
                <div class="input-card seo-input-card seo-placeholder-input-card">
                    <div class="seo-note-title">${esc(activeSeoWorkspace?.name || "SEO Agent")}</div>
                    <div class="seo-note-text">This SEO agent dashboard is reserved for future setup. Live SEO workspaces will appear here as they are connected to the shared engine.</div>
                </div>
            </div>
        `;
    } else if (isAccountantAgent) {
        // The AccountantAgent is scheduler-managed; there is no manual run control.
    } else if (agent.accepts_upload) {
        html += renderUploadSection(agent);
    } else {
        html += renderSimpleRunSection();
    }

    // --- Pipeline progress panel (shown in pipeline mode) ---
    if (isPCTAgent && (state.pipelineMode || (state.isRunning && state.pipeline))) {
        html += renderPipelineSection();
    }

    // --- Run Metrics panel (stopwatch + ETA + captcha tier breakdown) ---
    // Only for PCT agent (where rows + captchas matter).
    if (isPCTAgent && state.runMetrics && state.runMetrics.startedAt) {
        html += renderRunMetricsPanel();
    }

    // --- Execution Log + Browser Preview (side by side) ---
    // Scraping Browser stays visible in pool mode too — with N tabs running
    // it cycles through whichever worker emitted the most recent event,
    // which is what the user wants ("show what's being scraped right now").
    if ((!isSeoAgent || isLiveSeoWorkspace) && !isAccountantAgent) {
        const showBrowserPanel = isPCTAgent;
        html += `
            <div class="execution-split">
                <div class="execution-log-panel${showBrowserPanel ? "" : " full-width"}">
                    <div class="section-title">Execution Log</div>
                    <div class="terminal" id="terminal">
                        ${state.executionLog.length === 0 && !state.isRunning
                            ? '<span class="terminal-empty">Configure input above and click "Run Agent" to start...</span>'
                            : ""}
                        ${state.executionLog.map((l) => createTerminalLineHTML(l)).join("")}
                        ${state.isRunning ? '<span class="terminal-cursor"></span>' : ""}
                    </div>
                </div>
                ${showBrowserPanel ? `
                <div class="browser-preview-panel">
                    <div class="section-title">Scraping Browser${state.pipelineMode ? ' <span class="browser-pool-hint">(latest of N parallel tabs)</span>' : ""}</div>
                    <div class="browser-extract-summary" id="browser-extract-summary"></div>
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
    }

    // --- Results ---
    if (state.lastResult) {
        if (isPCTAgent) {
            html += renderPCTResults(state.lastResult);
        } else if (isSeoAgent && isLiveSeoWorkspace) {
            html += renderSEOResults(state.lastResult);
        } else if (state.lastResult.status === "failure") {
            html += renderFailureResults(state.lastResult);
        }
    }

    // --- Memory ---
    if ((!isSeoAgent || isLiveSeoWorkspace) && !isAccountantAgent) {
        html += renderMemorySection(learnings);
    }

    // --- Raw JSON ---
    if (state.lastResult && (!isSeoAgent || isLiveSeoWorkspace)) {
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
    const reminderScroll = document.getElementById("reminder-table-scroll");
    if (reminderScroll) {
        reminderScroll.scrollLeft = state.accountantDashboard.tableScrollLeft || 0;
    }
    if (isSeoAgent && isLiveSeoWorkspace) {
        applySeoInsightsAccordion();
    }
    attachHandlers(agent);
}

// ---------------------------------------------------------------------------
// Agent-specific input sections
// ---------------------------------------------------------------------------
function renderFastModeControl() {
    // Slider removed: PCT agent now always runs at L5 Max. See
    // resolve_fast_level in agents/pct_agent/agent.py — it's hard-locked.
    return "";
}

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
                    ${renderFastModeControl()}
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
    const sourceMix = Array.isArray(todayRun.sourceMix)
        ? todayRun.sourceMix
        : (typeof todayRun.sourceMix === "string" && todayRun.sourceMix.trim()
            ? todayRun.sourceMix.split(",").map((item) => item.trim()).filter(Boolean)
            : []);
    const runStateLabel = state.isRunning
        ? "Workflow in progress"
        : seo.dryRun
            ? "Dry run ready"
            : seo.publishOverride === "publish"
                ? "Live publish ready"
                : "Draft mode ready";
    const runStateClass = state.isRunning
        ? "success"
        : seo.publishOverride === "publish" && !seo.dryRun
            ? "warning"
            : "";
    return `
        <div class="input-section">
            <div class="section-title">Today’s SEO Run</div>
            <div class="input-card seo-input-card">
                <div class="seo-run-command-bar">
                    <div class="seo-run-command-copy">
                        <div class="seo-run-command-kicker">Live topic control</div>
                        <div class="seo-run-command-title">Review the selected topic, adjust only what you need, then launch the SEO workflow.</div>
                    </div>
                    <div class="seo-run-command-state ${runStateClass}">${esc(runStateLabel)}</div>
                </div>

                <div class="seo-panel-grid seo-run-summary-grid">
                    <div class="seo-run-summary-card seo-run-summary-card-primary seo-run-summary-card-topic">
                        <div class="seo-run-summary-label">Selected Topic</div>
                        <div class="seo-run-summary-value">${esc(selectedTopic)}</div>
                    </div>
                    <div class="seo-run-summary-card seo-run-summary-card-primary seo-run-summary-card-keyword">
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
                    <div class="seo-run-summary-card seo-run-summary-card-wide">
                        <div class="seo-run-summary-label">Source Mix</div>
                        <div class="seo-run-summary-value">${esc(sourceMix.length ? sourceMix.join(", ") : "Live topic sources pending")}</div>
                    </div>
                    <div class="seo-run-summary-card">
                        <div class="seo-run-summary-label">Confidence / Freshness</div>
                        <div class="seo-run-summary-value">${esc(`${todayRun.confidenceScore ?? "-"} / ${todayRun.freshnessLevel || "Pending"}`)}</div>
                    </div>
                </div>

                <div class="seo-run-controls-grid">
                    <div class="seo-run-control-panel">
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
                                Optional: force a specific topic for this run. Otherwise the agent will choose from live demand signals and competitor-topic discovery. For testing, use <code>/bypass-daily-limit</code> here to allow an extra live post today, with or without a custom topic after the command.
                            </div>
                        </div>

                        <div class="seo-chip-list">
                            ${secondaryKeywords.length
                                ? secondaryKeywords.map((keyword) => `<span class="sub-agent-chip">${esc(keyword)}</span>`).join("")
                                : '<span class="sub-agent-chip">Secondary keywords will appear after research</span>'}
                        </div>
                    </div>

                    <div class="seo-run-control-panel seo-run-control-panel-side">
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
                    </div>
                </div>

                <div class="seo-run-actions-shell">
                    <div class="seo-run-actions-copy">
                        <div class="seo-run-actions-title">Execution actions</div>
                        <div class="seo-run-actions-note">Use draft for safe review, live publish for production, or stop an active workflow if the topic or output needs to change.</div>
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
        </div>
    `;
}

function toSeoCardKey(title) {
    return String(title || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

function getSeoExpandedInsight() {
    if (state.seoDashboard.expandedInsight === null) {
        return null;
    }
    if (typeof state.seoDashboard.expandedInsight !== "string" || !state.seoDashboard.expandedInsight.trim()) {
        state.seoDashboard.expandedInsight = "overview";
    }
    return state.seoDashboard.expandedInsight;
}

function getSeoIndexingStatusClass(status) {
    const normalized = String(status || "").trim().toLowerCase();
    if (!normalized || normalized === "pending" || normalized === "unknown") {
        return "status-not_found";
    }
    if (
        normalized.includes("indexed")
        || normalized.includes("request")
        || normalized.includes("pass")
        || normalized.includes("allowed")
    ) {
        return "status-found";
    }
    if (
        normalized.includes("fail")
        || normalized.includes("error")
        || normalized.includes("blocked")
        || normalized.includes("revoked")
    ) {
        return "status-error";
    }
    return "status-not_found";
}

function applySeoInsightsAccordion() {
    const shell = document.querySelector(".seo-dashboard-shell");
    if (!shell) return;

    const cards = [
        ...shell.querySelectorAll(
            ":scope > .result-card, :scope > .seo-panel-grid > .result-card, :scope > .results-grid > .result-card"
        ),
    ];
    cards.forEach((card) => {
        const header = card.querySelector(":scope > .seo-card-header");
        const directHeading = card.querySelector(":scope > h4");
        const headingNode = header?.querySelector(":scope > h4") || directHeading;
        const title = (headingNode?.textContent || "").trim();
        const key = toSeoCardKey(title);
        if (!key) return;

        const expanded = getSeoExpandedInsight() === key;
        card.dataset.seoCard = key;
        card.classList.add("seo-collapsible-card");
        card.classList.toggle("expanded", expanded);
        card.classList.toggle("collapsed", !expanded);

        const headerEl = header || document.createElement("div");
        headerEl.classList.add("seo-card-header", "seo-card-header-collapsible");
        if (!header) {
            card.insertBefore(headerEl, card.firstChild);
        }

        const existingActions = [];
        [...headerEl.children].forEach((child) => {
            if (child !== headingNode) existingActions.push(child);
        });
        if (headingNode) {
            headingNode.remove();
        }

        const contentId = `seo-card-content-${key}`;

        const titleButton = document.createElement("button");
        titleButton.type = "button";
        titleButton.className = "seo-card-toggle-label";
        titleButton.dataset.seoCardToggle = key;
        titleButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        titleButton.setAttribute("aria-controls", contentId);
        titleButton.innerHTML = `<span class="seo-card-heading">${esc(title)}</span>`;

        const actionsWrap = document.createElement("div");
        actionsWrap.className = "seo-card-header-actions";
        existingActions.forEach((node) => actionsWrap.appendChild(node));

        const arrowButton = document.createElement("button");
        arrowButton.type = "button";
        arrowButton.className = "seo-card-arrow-btn";
        arrowButton.dataset.seoCardToggle = key;
        arrowButton.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${title}`);
        arrowButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        arrowButton.setAttribute("aria-controls", contentId);
        arrowButton.innerHTML = expanded ? "&#9662;" : "&#9656;";
        actionsWrap.appendChild(arrowButton);

        headerEl.innerHTML = "";
        headerEl.appendChild(titleButton);
        headerEl.appendChild(actionsWrap);

        let content = card.querySelector(":scope > .seo-collapsible-content");
        if (!content) {
            content = document.createElement("div");
            content.className = "seo-collapsible-content";
            content.id = contentId;
            const inner = document.createElement("div");
            inner.className = "seo-collapsible-inner";

            [...card.childNodes].forEach((node) => {
                if (node !== headerEl) inner.appendChild(node);
            });

            content.appendChild(inner);
            card.appendChild(content);
        }

        content.classList.toggle("expanded", expanded);
        content.classList.toggle("collapsed", !expanded);
    });
}

function renderSEOOverviewSection() {
    const dashboard = state.seoDashboard;
    const snapshot = dashboard.snapshot;
    const seo = state.seo;

    if (dashboard.loading && !snapshot) {
        return `
            <div class="result-card seo-dashboard-shell">
                <h4>SEO Posting Agent Dashboard</h4>
                <div class="memory-empty">Loading ${esc(getActiveSeoWorkspaceLabel())} control data...</div>
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
    const socialStatus = snapshot.socialStatus || {};
    const seoPerformance = snapshot.seoPerformance || [];
    const logsHistory = snapshot.logsHistory || [];
    const topKeywords = overview.topKeywords || [];
    const liveSignals = snapshot.liveSignals || [];
    const rejectedTopics = snapshot.rejectedTopics || [];
    const selectedTopic = topicDiscovery.selectedTopic || {};
    const workspace = snapshot.workspace || {};
    const workspaceSiteName = workspace.siteName || workspace.name || getActiveSeoWorkspaceLabel();
    const workspacePropertyPlaceholder = getDefaultSearchConsoleProperty(workspace.id || state.seo.activeWorkspaceId);

    return `
        <div class="seo-dashboard-shell">
            <div class="section-title">SEO Posting Agent Dashboard</div>

            <div class="seo-overview-grid seo-overview-grid-wide seo-kpi-grid">
                <div class="stat-card stat-card-primary">
                    <div class="stat-value">${overview.articlesPublished || 0}</div>
                    <div class="stat-label">Articles Published</div>
                </div>
                <div class="stat-card stat-card-positive">
                    <div class="stat-value ${overview.publishedToday ? "success" : "warning"}">${overview.publishedToday ? "Yes" : "No"}</div>
                    <div class="stat-label">Published Today</div>
                </div>
                <div class="stat-card stat-card-secondary">
                    <div class="stat-value warning">${overview.monthlyArticlesPublished || 0} / ${overview.monthlyTarget || 30}</div>
                    <div class="stat-label">Monthly Articles Published</div>
                </div>
                <div class="stat-card stat-card-secondary">
                    <div class="stat-value">${overview.successRate || 0}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card stat-card-secondary">
                    <div class="stat-value">${overview.seoScore || 0}</div>
                    <div class="stat-label">Average SEO Score</div>
                </div>
                <div class="stat-card stat-card-positive">
                    <div class="stat-value ${String(overview.wordpressStatus || "").toLowerCase().includes("connected") ? "success" : "error"}" style="font-size:18px">${esc(overview.wordpressStatus || "Pending")}</div>
                    <div class="stat-label">WordPress Status</div>
                </div>
                <div class="stat-card stat-card-secondary">
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
                    <div class="seo-slot-meta">${esc(selectedTopic.theme || selectedTopic.intentCluster || `${workspaceSiteName} topic discovery`)}</div>
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
                        <table class="results-table seo-mini-table seo-article-manager-table">
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
                                        <td>
                                            <div class="seo-table-title">${esc(item.title || "-")}</div>
                                            <div class="seo-table-subtitle">${item.url ? `<a class="result-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.url)}</a>` : "Draft or unpublished article"}</div>
                                        </td>
                                        <td>${item.seoScore ?? "-"}</td>
                                        <td>
                                            <div class="seo-table-title">${esc(item.primaryKeyword || "-")}</div>
                                            <div class="seo-table-subtitle">${esc(item.focusKeyword || item.secondaryKeyword || "Primary focus keyword")}</div>
                                        </td>
                                        <td><code class="seo-inline-code">${esc(item.slug || "-")}</code></td>
                                        <td><div class="seo-table-description" title="${esc(item.metaDescription || "-")}">${esc(item.metaDescription || "-")}</div></td>
                                        <td><span class="status-pill ${String(item.publishStatus || "").toLowerCase() === "publish" ? "status-found" : "status-not_found"}">${esc(item.publishStatus || "-")}</span></td>
                                        <td><span class="status-pill ${getSeoIndexingStatusClass(item.indexingStatus)}">${esc(item.indexingStatus || "Pending")}</span></td>
                                        <td>
                                            <div class="seo-action-buttons seo-article-actions">
                                                ${item.previewHtml ? `<button type="button" class="json-toggle seo-preview-btn" data-article-id="${esc(item.id)}">Preview</button>` : `<span class="seo-table-subtitle">No preview</span>`}
                                            </div>
                                        </td>
                                        <td>
                                            <div class="seo-action-buttons seo-article-actions">
                                                ${String(item.publishStatus || "").toLowerCase() === "publish" && item.url ? `<button type="button" class="json-toggle seo-request-indexing-btn" data-url="${esc(item.url)}">Request Indexing</button>` : `<span class="seo-table-subtitle">Not available</span>`}
                                            </div>
                                        </td>
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
                            <input id="seo-google-property" class="text-input" type="text" placeholder="${esc(workspacePropertyPlaceholder)}" value="${esc(seo.google.property)}" />
                            <div class="input-help">Use the Search Console domain property for this workspace, for example <code>${esc(workspacePropertyPlaceholder)}</code>.</div>
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
                    <h4>Social Publishing</h4>
                    <div class="seo-status-list">
                        <div class="seo-status-item">
                            <div>
                                <div class="seo-status-name">Auto Social Posting</div>
                                <div class="seo-status-detail">${socialStatus.autoPostEnabled ? "Published articles are shared automatically after a successful live publish." : "Automatic social posting is turned off for this workspace."}</div>
                            </div>
                            <span class="seo-status-pill ${socialStatus.autoPostEnabled ? "ready" : "blocked"}">${socialStatus.autoPostEnabled ? "Enabled" : "Disabled"}</span>
                        </div>
                        <div class="seo-status-item">
                            <div>
                                <div class="seo-status-name">Content Rules</div>
                                <div class="seo-status-detail">Featured image: ${socialStatus.useFeaturedImage ? "On" : "Off"} • Hashtags: ${socialStatus.useHashtags ? "On" : "Off"}</div>
                            </div>
                            <span class="seo-status-pill ready">${esc(String(socialStatus.configuredPlatformCount || 0))} Active</span>
                        </div>
                        ${(socialStatus.platformRows || []).map((item) => `
                            <div class="seo-status-item">
                                <div>
                                    <div class="seo-status-name">${esc(item.label || "-")}</div>
                                    <div class="seo-status-detail">${esc(item.detail || "")}${item.postId ? ` • Post ID: ${esc(item.postId)}` : ""}</div>
                                </div>
                                <span class="seo-status-pill ${item.status === "Posted" ? "ready" : "blocked"}">${esc(item.status || "-")}</span>
                            </div>
                        `).join("")}
                        ${(socialStatus.pendingPlatforms || []).length
                            ? `<div class="seo-status-item">
                                <div>
                                    <div class="seo-status-name">Later Setup</div>
                                    <div class="seo-status-detail">${esc((socialStatus.pendingPlatforms || []).map((item) => item.charAt(0).toUpperCase() + item.slice(1)).join(", "))} is planned but not connected yet for this workspace.</div>
                                </div>
                                <span class="seo-status-pill blocked">Pending</span>
                            </div>`
                            : ""}
                        ${socialStatus.latestArticleUrl
                            ? `<div class="seo-status-item">
                                <div>
                                    <div class="seo-status-name">Latest Social Post</div>
                                    <div class="seo-status-detail">${esc(socialStatus.latestTitle || "Latest article")} • ${esc(formatTimestamp(socialStatus.updatedAt || socialStatus.latestPostedAt || ""))}</div>
                                    <a class="result-link" href="${esc(socialStatus.latestArticleUrl)}" target="_blank" rel="noopener noreferrer">${esc(socialStatus.latestArticleUrl)}</a>
                                </div>
                                <span class="seo-status-pill ${socialStatus.latestOk ? "ready" : "blocked"}">${socialStatus.latestOk ? "Success" : "Check"}</span>
                            </div>`
                            : `<div class="memory-empty">No social post has been recorded yet for this workspace.</div>`}
                    </div>
                </div>

                <div class="result-card">
                    <h4>WordPress Publishing Monitor</h4>
                    <div class="seo-status-list">
                        <div class="seo-status-item">
                            <div>
                                <div class="seo-status-name">WordPress Connection Status</div>
                                <div class="seo-status-detail">${esc(wordpressMonitor.websiteUrl || "-")}</div>
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
                                    <div class="seo-run-title">${esc(run.title || run.primaryKeyword || "SEO run")}</div>
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
    // Fast-mode slider — updates state + localStorage live. Editable
    // even mid-run; the change handler delegates to onFastModeCommit
    // which POSTs to the live API when the agent is running.
    const fastSlider = document.getElementById("fast-mode-slider");
    if (fastSlider) {
        fastSlider.oninput = (e) => {
            const raw = parseInt(e.target.value, 10);
            const level = Number.isFinite(raw) ? Math.max(1, Math.min(5, raw)) : 1;
            const cur = document.getElementById("fast-mode-current");
            if (cur) {
                const profile = FAST_LEVELS[level] || FAST_LEVELS[1];
                cur.innerHTML =
                    `<span class="fast-mode-current-emoji">${profile.emoji}</span>` +
                    `<span class="fast-mode-current-label">L${level} ${esc(profile.label)}</span>`;
            }
            const chip = fastSlider.closest(".fast-mode-chip");
            if (chip) {
                const profile = FAST_LEVELS[level] || FAST_LEVELS[1];
                chip.setAttribute("title", profile.hint);
            }
            // Live preview the metrics-panel slider too
            onFastModeSlide(String(level));
        };
        fastSlider.onchange = (e) => {
            // POST + persist via the shared commit path.
            onFastModeCommit(e.target.value);
        };
    }

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

                addLogLine(
                    "Starting at Fast Mode L1 Safe — single-browser sequential mode for reliability over speed",
                    "info",
                );

                runAgent(agent.module_name, {
                    mode: mode,
                    file_path: mode === "upload" ? state.uploadedFilePath : undefined,
                    gazette: mode === "wipo_download" ? state.selectedGazette : undefined,
                });
            } else if (agent.ui_type === "seo_posting") {
                triggerSeoRun(agent);
            } else {
                runAgent(agent.module_name, {});
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
    // Attach handler whenever the button is enabled — that includes the
    // case where state.isRunning is false locally but the server still
    // believes the agent is running (zombie run).
    const stopBtnEnabled = state.isRunning
        || state.agentRunStatus === "running"
        || state.agentRunStatus === "stopping";
    if (stopBtn && stopBtnEnabled && !state.stopRequested) {
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
                // Acceptable responses: stop_requested (alive thread), cleared (zombie),
                // idle (already cleared). Anything else is a real error.
                if (!["stop_requested", "cleared", "idle"].includes(response.status)) {
                    throw new Error(response.error || "Stop request failed");
                }
                if (response.status === "cleared" || response.status === "idle") {
                    // Server self-healed a zombie run — sync our local state.
                    state.isRunning = false;
                    state.stopRequested = false;
                    state.agentRunStatus = "idle";
                    addLogLine("Server cleared stale state — agent is now idle.", "step");
                    renderMain();
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

    if (agent.ui_type === "seo_posting") {
        document.querySelectorAll("[data-seo-workspace]").forEach((btn) => {
            btn.onclick = async (e) => {
                e.preventDefault();
                const nextId = btn.dataset.seoWorkspace || "";
                if (!nextId || state.seo.activeWorkspaceId === nextId) return;
                state.seo.activeWorkspaceId = nextId;
                state.seoDashboard.previewArticle = null;
                state.seoDashboard.historyEntry = null;
                state.seo.google.property = getDefaultSearchConsoleProperty(nextId);
                await loadSeoDashboardData(agent.module_name);
                renderMain();
            };
        });

        document.querySelectorAll("[data-seo-card-toggle]").forEach((btn) => {
            btn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const nextKey = btn.dataset.seoCardToggle || "";
                if (!nextKey) return;
                state.seoDashboard.expandedInsight =
                    state.seoDashboard.expandedInsight === nextKey ? null : nextKey;
                renderMain();
            };
        });
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
                const workspaceId = encodeURIComponent(state.seo.activeWorkspaceId || "patentzoom");
                window.open(`/api/google/search-console/connect?workspace_id=${workspaceId}`, "_blank", "noopener,noreferrer");
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
    if (lower.includes("preparing a new") && lower.includes("seo agent run")) return { stage: "readiness", status: "active" };
    if (lower.includes("validating local") && lower.includes("seo agent setup")) return { stage: "readiness", status: "active" };
    if (lower.includes("loading recent") && lower.includes("posts")) return { stage: "readiness", status: "active" };
    if (lower.includes("loaded") && lower.includes("recent") && lower.includes("posts")) return { stage: "readiness", status: "complete" };
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
    state.seoDashboard.workflow.currentMessage = `${getActiveSeoWorkspaceLabel()} workflow finished successfully.`;
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
        const workspaceId = encodeURIComponent(state.seo.activeWorkspaceId || "patentzoom");
        const res = await fetch(`/api/agents/${name}/dashboard-data?workspace_id=${workspaceId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to load SEO dashboard data");
        state.seoDashboard.snapshot = data;
        state.seo.publishOverride = data?.todayRun?.publishMode === "publish" ? "publish" : "draft";
        state.seo.enableFeaturedImage = data?.todayRun?.generateFeaturedImage !== false;
        state.seo.dryRun = false;
        state.seo.google.clientConfigured = !!data?.googleAuth?.clientConfigured;
        state.seo.google.connected = !!data?.googleAuth?.connected;
        state.seo.google.property = data?.googleAuth?.property || getDefaultSearchConsoleProperty(state.seo.activeWorkspaceId);
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
        return `${new Date(ts).toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata",
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit", hour12: true,
        })} IST`;
    } catch {
        return ts;
    }
}

function toggleJSON() {
    const el = document.getElementById("json-output");
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
}
