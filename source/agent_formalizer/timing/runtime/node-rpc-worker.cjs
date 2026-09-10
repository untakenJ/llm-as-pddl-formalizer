'use strict';
// A worker services local IPC while the caller waits synchronously for a lease.
// It neither runs model requests nor changes any clock.
const { parentPort } = require('node:worker_threads');
const net = require('node:net');
parentPort.on('message', ({ request, shared, directory }) => {
  const state = new Int32Array(shared, 0, 2);
  const bytes = new Uint8Array(shared, 8);
  let finished = false;
  const done = (value, failed = false) => {
    if (finished) return;
    finished = true;
    const data = Buffer.from(value);
    bytes.set(data.subarray(0, bytes.length));
    Atomics.store(state, 1, Math.min(data.length, bytes.length));
    Atomics.store(state, 0, failed ? 2 : 1);
    Atomics.notify(state, 0);
    socket.destroy();
  };
  const socket = net.createConnection(`${directory}/broker.sock`);
  let reply = '';
  socket.setTimeout(2500, () => done('deadline IPC timeout', true));
  socket.on('connect', () => socket.write(JSON.stringify(request) + '\n'));
  socket.on('data', chunk => {
    reply += chunk.toString();
    if (reply.length > bytes.length) done('deadline IPC oversized reply', true);
    else if (reply.includes('\n')) done(reply.split('\n')[0]);
  });
  socket.on('error', () => done('deadline IPC error', true));
  socket.on('end', () => { if (!finished) done('deadline IPC EOF', true); });
});
