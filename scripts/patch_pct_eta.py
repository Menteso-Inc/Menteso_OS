"""Apply the same small PCT timing fix to local or customized dashboard JS."""
from pathlib import Path
import argparse


OLD = '''        const newProcessed = state.runMetrics.processedRows || 0;
        const delta = Math.max(0, newProcessed - previousProcessed);
        const now = Date.now();
        for (let i = 0; i < delta; i++) {
            pushRowCompletionTimestamp(now);
        }
        updateRunMetricsPanel();'''
NEW = '''        const newProcessed = state.runMetrics.processedRows || 0;
        const timing = data.browser?.timing;
        if (state.selectedAgent?.module_name === "pct_agent" && timing?.startedAt) {
            // Authoritative completion times exclude restored rows and survive
            // refresh, reconnection and duplicate SSE/poll delivery.
            const rm = state.runMetrics;
            rm.startedAt = timing.startedAt;
            rm.modeChangedAt = timing.startedAt;
            rm.rowsAtModeChange = timing.resumedRows || 0;
            rm.rowTimestamps = (timing.rowTimestamps || []).slice(-20);
            rm.recalibrating = rm.rowTimestamps.length < 5;
            if (["running", "stopping"].includes(data.status)) {
                rm.finishedAt = null;
                state.isRunning = true;
                startRunMetricsTicker();
            }
        } else {
            const delta = Math.max(0, newProcessed - previousProcessed);
            const now = Date.now();
            for (let i = 0; i < delta; i++) pushRowCompletionTimestamp(now);
        }
        updateRunMetricsPanel();'''


def patch(source):
    if NEW in source:
        return source
    if source.count(OLD) != 1:
        raise ValueError("Dashboard timing code differs; inspect before patching")
    return source.replace(OLD, NEW, 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    args.path.write_text(patch(args.path.read_text(encoding="utf-8")), encoding="utf-8")
