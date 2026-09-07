'use strict';
// In-process watchdogs: no Worker, Atomics.wait, RPC or file read on a stream event.
const fs = require('node:fs');
const net = require('node:net');
const timers = require('node:timers');
const directory = process.env.BENCHMARK_DEADLINE_DIR;
let state = JSON.parse(fs.readFileSync(`${directory}/clock.json`, 'utf8'));
const live = new Set();
const contexts = new Set();
let snapshot = null, activeTools = 0, concurrentWork = false;
const physical = () => Number(process.hrtime.bigint()) / 1e9;
const nowMs = () => (state.logical + (state.paused ? 0 : Math.max(0, physical() - state.anchor))) * 1000;
let resolveReady, rejectReady, connected = false;
const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
const socket = net.createConnection(`${directory}/checkpoint.sock`);
let buffer = '';

function fail(error) {
  rejectReady(error);
  // Never silently continue with unprotected native deadlines.
  process.stderr.write(`benchmark call checkpoint control failed: ${error.message}\n`);
  process.exitCode = 70;
  socket.destroy();
  for (const timer of live) timer.close();
  process.exit(70);
}
socket.on('error', fail);
socket.on('close', () => { if (connected) fail(new Error('checkpoint channel closed')); });
socket.on('data', chunk => {
  buffer += chunk.toString();
  if (buffer.length > 65536) return fail(new Error('checkpoint message too large'));
  let newline;
  while ((newline = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
    try {
      const message = JSON.parse(line);
      if (!['hello', 'checkpoint', 'prepare', 'settle', 'resume'].includes(message.op)) throw new Error('unknown checkpoint operation');
      state = message;
      if (message.op === 'hello') {
        connected = true; socket.unref(); resolveReady();
        continue;
      }
      if (message.op === 'checkpoint') {
        snapshot = [...contexts].map(context => [context, JSON.stringify(context)]);
        concurrentWork = activeTools > 1;
      }
      if (message.op === 'prepare' && message.rollback) {
        if (snapshot === null || concurrentWork || snapshot.some(([context, saved]) => JSON.stringify(context) !== saved)) {
          socket.write(JSON.stringify({ sequence: message.sequence, error: 'checkpoint_business_state_changed' }) + '\n');
          continue;
        }
      }
      if (message.op === 'resume') snapshot = null;
      for (const timer of [...live]) timer.schedule();
      // Native callbacks due at settlement run before ACK. Promise rejection
      // handlers get a turn before the host can open the delivery barrier.
      setImmediate(() => {
        let target = null;
        for (const timer of live) target = target === null ? timer.target / 1000 : Math.min(target, timer.target / 1000);
        socket.write(JSON.stringify({ sequence: message.sequence, target, timers: live.size }) + '\n');
      });
    } catch (error) { fail(error); }
  }
});

class CheckpointTimeout {
  constructor(callback, delay, args) {
    if (typeof callback !== 'function') throw new TypeError('callback must be a function');
    this.callback = callback; this.args = args;
    const ms = Number(delay);
    this.delay = Number.isFinite(ms) && ms >= 1 && ms <= 2147483647 ? Math.trunc(ms) : 1;
    this.referenced = true;
    this.refresh();
  }
  schedule() {
    if (this.timer) timers.clearTimeout(this.timer);
    this.timer = null;
    if (!live.has(this)) return;
    const remaining = this.target - nowMs();
    // A deadline already due at the checkpoint must remain in its snapshot.
    // Firing it before settlement would erase the host's cancellation evidence.
    if (remaining <= 0 && (!state.paused || state.op === 'settle')) {
      live.delete(this);
      this.callback.apply(this, this.args);
      return;
    }
    // A referenced native timer keeps the awaiting CLI alive during escrow;
    // there is no polling. Settlement/resume explicitly re-arms it.
    this.timer = timers.setTimeout(() => this.schedule(), state.paused ? 2147483647 : Math.max(1, remaining));
    if (!this.referenced) this.timer.unref();
  }
  refresh() {
    this.close(); this.target = nowMs() + this.delay; live.add(this); this.schedule(); return this;
  }
  close() { if (this.timer) timers.clearTimeout(this.timer); this.timer = null; live.delete(this); return this; }
  ref() { this.referenced = true; this.timer?.ref(); return this; }
  unref() { this.referenced = false; this.timer?.unref(); return this; }
  hasRef() { return this.referenced; }
  [Symbol.dispose]() { this.close(); }
}

exports.ready = () => ready;
exports.watchContext = context => { contexts.add(context); return () => contexts.delete(context); };
exports.enterTool = () => {
  activeTools += 1;
  if (snapshot && activeTools > 1) concurrentWork = true;
  return () => { activeTools -= 1; };
};
exports.setTimeout = (callback, delay, ...args) => new CheckpointTimeout(callback, delay, args);
exports.clearTimeout = timer => timer instanceof CheckpointTimeout ? timer.close() : timers.clearTimeout(timer);
exports.nowMs = nowMs;
exports.runtimeEnvironment = () => ({
  BENCHMARK_DEADLINE_DIR: directory,
  BENCHMARK_DEADLINE_HARNESS: 'openclaw',
  BENCHMARK_EXTERNAL_CALL_TIMING: 'call-checkpoint-v1',
  PYTHONPATH: '/opt/benchmark-deadlines',
  LD_PRELOAD: '/opt/benchmark-deadlines/timeout_deadline.so',
  NODE_OPTIONS: '--import=/opt/benchmark-deadlines/node-bootstrap.mjs',
});
