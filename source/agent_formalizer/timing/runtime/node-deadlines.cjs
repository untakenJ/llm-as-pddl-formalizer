'use strict';
// Explicit deadline API for inspected OpenClaw/SDK sites, not global time mocks.
const fs = require('node:fs');
const path = require('node:path');
const { Worker } = require('node:worker_threads');
const timers = require('node:timers');
const directory = process.env.BENCHMARK_DEADLINE_DIR;
let worker;

function rpc(request) {
  if (!worker) {
    worker = new Worker(path.join(__dirname, 'node-rpc-worker.cjs'), { execArgv: [], env: { ...process.env, NODE_OPTIONS: '' } });
    worker.unref();
  }
  const shared = new SharedArrayBuffer(4104);
  const state = new Int32Array(shared, 0, 2);
  worker.postMessage({ request, shared, directory });
  if (Atomics.wait(state, 0, 0, 3000) === 'timed-out') throw new Error('benchmark deadline IPC unavailable');
  const reply = Buffer.from(new Uint8Array(shared, 8, Atomics.load(state, 1))).toString();
  if (Atomics.load(state, 0) !== 1) throw new Error(reply);
  const result = JSON.parse(reply);
  if (result.error) throw new Error(`benchmark deadline IPC rejected: ${result.error}`);
  return result;
}

function nowMs() {
  const state = JSON.parse(fs.readFileSync(`${directory}/clock.json`, 'utf8'));
  if (state.policy !== 'logical-deadline-v1') throw new Error('benchmark deadline policy mismatch');
  const physical = Number(process.hrtime.bigint()) / 1e9;
  return (state.logical + (state.paused ? 0 : Math.max(0, physical - state.anchor))) * 1000;
}

class LogicalTimeout {
  constructor(callback, delay, args) {
    if (typeof callback !== 'function') throw new TypeError('callback must be a function');
    this.callback = callback;
    this.args = args;
    const ms = Number(delay);
    // Node's ordinary one-shot timer normalization (including zero/NaN).
    this.delay = Number.isFinite(ms) && ms >= 1 && ms <= 2147483647 ? Math.trunc(ms) : 1;
    this.referenced = true;
    this.key = null;
    this.refresh();
  }
  schedule() {
    this.timer = timers.setTimeout(() => {
      if (!this.key) return;
      if (nowMs() < this.target) { this.schedule(); return; }
      const key = this.key;
      this.key = null;
      try { this.callback.apply(this, this.args); }
      finally { rpc({ op: 'close', id: key }); }
    }, Math.max(1, Math.min(25, this.target - nowMs())));
    if (!this.referenced) this.timer.unref();
  }
  refresh() {
    this.close();
    const value = rpc({ op: 'register', seconds: this.delay / 1000 });
    this.key = value.id;
    this.target = value.target * 1000;
    this.schedule();
    return this;
  }
  close() {
    if (this.timer) timers.clearTimeout(this.timer);
    if (this.key) { const key = this.key; this.key = null; rpc({ op: 'close', id: key }); }
    return this;
  }
  ref() { this.referenced = true; this.timer?.ref(); return this; }
  unref() { this.referenced = false; this.timer?.unref(); return this; }
  hasRef() { return this.referenced; }
  [Symbol.dispose]() { this.close(); }
}

exports.setTimeout = (callback, delay, ...args) => new LogicalTimeout(callback, delay, args);
exports.clearTimeout = timer => timer instanceof LogicalTimeout ? timer.close() : timers.clearTimeout(timer);
exports.nowMs = nowMs;
exports.runtimeEnvironment = () => ({
  BENCHMARK_DEADLINE_DIR: directory,
  BENCHMARK_DEADLINE_HARNESS: 'openclaw',
  PYTHONPATH: '/opt/benchmark-deadlines',
  LD_PRELOAD: '/opt/benchmark-deadlines/timeout_deadline.so',
  NODE_OPTIONS: '--import=/opt/benchmark-deadlines/node-bootstrap.mjs',
});
