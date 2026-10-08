"""Keep PCT status attached to the backend after a live log disconnection."""
from pathlib import Path
import argparse


HELPER = '''async function recoverPCTRunAfterStream(name) {
    if (name !== "pct_agent") return false;
    const status = await loadAgentRunStatus(name);
    if (status === "idle") return false;
    // A closed log stream is not evidence that the background worker stopped.
    state.isRunning = true;
    state.stopRequested = status === "stopping";
    addLogLine(status === "unknown"
        ? "Dashboard connection interrupted; checking the agent status again."
        : "Live log connection ended; continuing updates from the running agent.", "step");
    startRunStatusPoller();
    renderMain();
    return true;
}

'''

REPLACEMENTS = [
    ('''        const res = await fetch(`/api/agents/${name}/run-status`);
        const data = await res.json();''',
     '''        const res = await fetch(`/api/agents/${name}/run-status`);
        if (!res.ok) throw new Error(`Run status request failed (${res.status})`);
        const data = await res.json();'''),
    ('''        console.error("Failed to load agent run status:", e);
        state.agentRunStatus = "idle";''',
     '''        console.error("Failed to load agent run status:", e);
        if (name === "pct_agent") {
            // Keep polling: a network failure cannot confirm an idle worker.
            startRunStatusPoller();
            return "unknown";
        }
        state.agentRunStatus = "idle";'''),
    ('''    if (!data || typeof data !== "object") return;
    if (data.lastEvent?.type === "complete" && state.isRunning) {''',
     '''    if (!data || typeof data !== "object") return;
    if (state.selectedAgent?.module_name === "pct_agent"
            && ["running", "stopping"].includes(data.status)) {
        if (data.run_id && state.pctRunId !== data.run_id) {
            state.pctRunId = data.run_id;
            state.executionLog = [];
        }
        state.lastResult = null;
        state.isRunning = true;
        state.stopRequested = data.status === "stopping";
    }
    if (data.lastEvent?.type === "complete" && state.isRunning) {'''),
    ('''            addLogLine(message, "error");
            state.isRunning = false;''',
     '''            addLogLine(message, "error");
            if (await recoverPCTRunAfterStream(name)) return;
            state.isRunning = false;'''),
    ('''        addLogLine(`Connection error: ${e.message}`, "error");
    }

    state.isRunning = false;''',
     '''        addLogLine(`Connection error: ${e.message}`, "error");
    }

    if (await recoverPCTRunAfterStream(name)) return;
    state.isRunning = false;'''),
    ('''function handleSSEEvent(data) {''', HELPER + '''function handleSSEEvent(data) {'''),
]


def patch(source):
    if HELPER in source:
        return source
    for before, after in REPLACEMENTS:
        if source.count(before) != 1:
            raise ValueError("Dashboard status code differs; inspect before patching")
        source = source.replace(before, after, 1)
    return source


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    args.path.write_text(patch(args.path.read_text(encoding="utf-8")), encoding="utf-8")
