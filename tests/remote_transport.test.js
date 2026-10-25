"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {RemoteTransport} = require("../src/ad_linux_tv/static/remote_transport.js");

test("phone actions share one ordered socket and do not replay after disconnect", async () => {
  const sockets = [];
  class FakeSocket {
    static OPEN = 1;
    constructor(url, protocol) {
      this.url = url;
      this.protocol = protocol;
      this.readyState = 0;
      this.sent = [];
      sockets.push(this);
      queueMicrotask(() => { this.readyState = 1; this.onopen(); });
    }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.readyState = 3; this.onclose?.(); }
    reply(id, status, body) { this.onmessage({data:JSON.stringify({id, status, body})}); }
  }
  const previous = global.WebSocket;
  global.WebSocket = FakeSocket;
  try {
    const transport = new RemoteTransport({href:"http://192.168.1.111:8765/remote"});
    const first = transport.request("csrf-value", "POST", "/api/pointer", {dx:1,dy:0});
    const second = transport.request("csrf-value", "POST", "/api/pointer", {click:true});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets.length, 1);
    assert.equal(sockets[0].url, "ws://192.168.1.111:8765/api/remote-ws");
    assert.equal(sockets[0].protocol, "csrf.csrf-value");
    assert.deepEqual(sockets[0].sent.map(item => item.body), [{dx:1,dy:0},{click:true}]);
    sockets[0].reply(sockets[0].sent[0].id, 200, {});
    assert.equal((await first).status, 200);
    sockets[0].close();
    await assert.rejects(second, /closed/);
    const third = transport.request("csrf-value", "GET", "/api/status");
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets.length, 2);
    assert.deepEqual(sockets[1].sent.map(item => item.path), ["/api/status"]);
    sockets[1].reply(sockets[1].sent[0].id, 200, {extension_online:true});
    assert.deepEqual(await (await third).json(), {extension_online:true});
    transport.close();
  } finally {
    global.WebSocket = previous;
  }
});
