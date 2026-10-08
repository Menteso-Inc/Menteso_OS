// Exercise the dashboard's real functions with dropped streams and status fetches.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

async function check(file) {
    const code = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
    function fn(name) {
        let start = code.indexOf(`function ${name}(`);
        assert(start >= 0, name);
        if (code.slice(start - 6, start) === 'async ') start -= 6;
        return code.slice(start, code.indexOf('\n}\n', start) + 2);
    }
    const state = {selectedAgent: {module_name: 'pct_agent'}, agentRunStatus: 'running',
        isRunning: true, lastResult: {status: 'stopped'}, executionLog: [{message: 'old run'}],
        runMetrics: {processedRows: 218}, browser: {}};
    let polls = 0;
    let response = {status: 'running', run_id: 'resumed-run', metrics: {processedRows: 280, totalRows: 4241},
        browser: {timing: {startedAt: Date.now() - 10000, resumedRows: 218, rowTimestamps: []}}};
    let fail = false;
    let httpStatus = 200;
    const context = vm.createContext({state, Date, console: {error: () => {}},
        document: {getElementById: () => null},
        fetch: async () => {
            if (fail) throw new Error('connection lost');
            return {ok: httpStatus === 200, status: httpStatus, json: async () => response};
        },
        startRunStatusPoller: () => {polls++;}, stopRunStatusPoller: () => {},
        startRunMetricsTicker: () => {}, stopRunMetricsTicker: () => {},
        addLogLine: () => {}, renderMain: () => {}, updateRunMetricsPanel: () => {},
        updateBrowserPreview: () => {}, pushRowCompletionTimestamp: () => {}});
    vm.runInContext(['loadAgentRunStatus', 'applyRunStatusSnapshot', 'recoverPCTRunAfterStream'].map(fn).join('\n'), context);
    assert(await vm.runInContext('recoverPCTRunAfterStream("pct_agent")', context));
    assert.strictEqual(state.isRunning, true);
    assert.strictEqual(state.lastResult, null, 'Old stopped report must not remain in the active run');
    assert.strictEqual(state.executionLog.length, 0);
    assert.strictEqual(state.runMetrics.processedRows, 280);
    assert(polls > 0);
    fail = true;
    assert.strictEqual(await vm.runInContext('loadAgentRunStatus("pct_agent")', context), 'unknown');
    assert.strictEqual(state.agentRunStatus, 'running', 'Network failure must not mark worker idle');
    assert(await vm.runInContext('recoverPCTRunAfterStream("pct_agent")', context));
    fail = false;
    httpStatus = 502;
    assert.strictEqual(await vm.runInContext('loadAgentRunStatus("pct_agent")', context), 'unknown');
    httpStatus = 200;
    response = {...response, status: 'stopping'};
    assert(await vm.runInContext('recoverPCTRunAfterStream("pct_agent")', context));
    assert.strictEqual(state.stopRequested, true);
    response = {status: 'idle', lastEvent: {type: 'complete', result: {status: 'stopped'}}};
    assert.strictEqual(await vm.runInContext('recoverPCTRunAfterStream("pct_agent")', context), false);
    assert.strictEqual(state.isRunning, false);
    assert.strictEqual(state.lastResult.status, 'stopped');
    const priorPolls = polls;
    assert.strictEqual(await vm.runInContext('recoverPCTRunAfterStream("other_agent")', context), false);
    assert.strictEqual(polls, priorPolls);
    assert.strictEqual((code.match(/if \(await recoverPCTRunAfterStream\(name\)\) return;/g) || []).length, 2);
    console.log(file + ': running, stopping, completion, stale results, network failure and HTTP error checks passed');
}

(async () => {
    for (const file of process.argv.slice(2)) await check(file);
})().catch(error => {console.error(error); process.exitCode = 1;});
