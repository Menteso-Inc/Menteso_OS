const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const code = fs.readFileSync(process.argv[2] || 'static/app.js', 'utf8').replace(/\r\n/g, '\n');
function fn(name) {
    let start = code.indexOf(`function ${name}(`);
    if (code.slice(start - 6, start) === 'async ') start -= 6;
    assert(start >= 0, name);
    return code.slice(start, code.indexOf('\n}\n', start) + 2);
}
let now = 1000000;
const state = {isRunning: true, selectedAgent: {module_name: 'pct_agent'},
    captcha: {}, browser: {}, executionLog: [], runMetrics: {totalRows: 100,
    processedRows: 3, errorRows: 3, startedAt: 1000, rowTimestamps: [10000, 20000, 30000]}};
const context = vm.createContext({state, Date: {now: () => now}, console,
    document: {getElementById: () => null},
    updateRunMetricsPanel: () => {}, updateBrowserPreview: () => {},
    startRunMetricsTicker: () => {}, stopRunMetricsTicker: () => {},
    pushRowCompletionTimestamp: () => {}, renderMain: () => {}, playCaptchaAlertSound: () => {},
    CAPTCHA_PROGRESS_EVENTS: new Set()});
vm.runInContext(['syncPCTTelemetry', 'computeRunMetricsView', 'formatStopwatch',
    'applyRunStatusSnapshot', 'resetCaptchaAlert', 'handleBrowserEvent'].map(fn).join('\n'), context);
function sync(metrics) { context.incoming = metrics; vm.runInContext('syncPCTTelemetry(incoming)', context); }
function view() { return vm.runInContext('computeRunMetricsView(state.runMetrics)', context); }
const snapshot = {telemetryVersion: 1, telemetrySequence: 10, captchaCount: 2,
    captchaTotals: {manual: 2}, captchaDetected: 8, captchaFailures: 6,
    captchaUnconfirmedCount: 2, successfulRowTimestamps: [], verificationRows: [4],
    verificationStartedAt: {'4': 10000}};
sync(snapshot); sync(snapshot);
assert.equal(state.runMetrics.captchaCount, 2, 'Repeated polls must not add counts');
sync({...snapshot, telemetrySequence: 9, captchaCount: 1});
assert.equal(state.runMetrics.captchaCount, 2, 'Late snapshots must not roll counts back');
context.event = {event: 'solver_succeeded', type: 'browser', tier: 'manual', telemetry: snapshot};
vm.runInContext('handleBrowserEvent(event)', context);
assert.equal(state.runMetrics.captchaCount, 2, 'SSE after poll must not double count');
assert.equal(view().etaText, 'Learning', 'Download errors are not verified-PDF speed samples');
assert.match(view().activityText, /Verifying PDF for row 4/);
assert.match(view().captchaNote, /8 challenges detected/);
sync({...snapshot, telemetrySequence: 11, captchaActive: true});
assert.equal(view().etaText, 'Waiting');
sync({...snapshot, telemetrySequence: 12, captchaActive: false,
    successfulRowTimestamps: [1000, 11000, 21000, 31000, 41000]});
const earlier = view().etaText;
now += 600000;
assert.notEqual(view().etaText, earlier, 'A stalled worker must not show a frozen optimistic ETA');
vm.runInContext('applyRunStatusSnapshot({status:"running",run_id:"new-run",metrics:{},browser:{}})', context);
assert.equal(state.runMetrics.captchaCount, 0, 'New runs must not inherit old CAPTCHA totals');
assert.equal(state.runMetrics.telemetrySequence, undefined);
console.log('PCT telemetry: refresh, SSE/poll duplication, ordering, new run, errors, CAPTCHA and stalled ETA checks passed');
