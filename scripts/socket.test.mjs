import assert from 'node:assert/strict';
import { test } from 'node:test';
import { subscribeSocket } from '../src/socket.js';

test('missing orders stop retries, transient outages reconnect, cleanup stops callbacks', t => {
  const instances = [];
  class FakeSocket {
    constructor(url) { this.url = url; instances.push(this); }
    close() { this.onclose?.({ code: 1000 }); }
  }
  const originalSocket = globalThis.WebSocket;
  globalThis.WebSocket = FakeSocket;
  t.after(() => { globalThis.WebSocket = originalSocket; });
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const statuses = [], messages = [];
  const stop = subscribeSocket('ws://test/track/order', value => messages.push(value), value => statuses.push(value));
  instances[0].onopen();
  instances[0].onmessage({ data: '{"status":"packing"}' });
  instances[0].onclose({ code: 1006 });
  t.mock.timers.tick(1500);
  assert.equal(instances.length, 2);
  instances[1].onclose({ code: 1008 });
  t.mock.timers.tick(10000);
  assert.equal(instances.length, 2);
  assert.deepEqual(messages, [{ status: 'packing' }]);
  assert.deepEqual(statuses, [true, false, false]);
  stop();

  const dispose = subscribeSocket('ws://test/ops', value => messages.push(value));
  const socket = instances.at(-1);
  socket.onclose({ code: 1006 });
  dispose();
  socket.onmessage({ data: '{"status":"late callback"}' });
  t.mock.timers.tick(10000);
  assert.equal(instances.length, 3);
  assert.equal(messages.length, 1);
});
