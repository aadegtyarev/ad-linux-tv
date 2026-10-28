"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {RemoteTransport} = require("../src/ad_linux_tv/static/remote_transport.js");

test("native device identity binds websocket bootstrap without putting bearer data in URL", () => {
  const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const transport = new RemoteTransport({href:`http://192.168.1.20:8765/remote#device=${id}`});
  assert.equal(transport.expectedDevice, id);
  assert.equal(transport.address, `ws://192.168.1.20:8765/api/remote-ws?device=${id}`);
  assert.throws(() => new RemoteTransport({href:"http://192.168.1.20:8765/remote#device=bad"}));
});

test("familiar phone layout reserves countdown space without stacking primary controls", () => {
  const css = fs.readFileSync("src/ad_linux_tv/static/style.css", "utf8");
  assert.match(css, /#show-timer\{position:relative;padding:4px 2px 16px\}/);
  assert.match(css, /\.remote-timer-badge\{position:absolute;bottom:3px/);
  assert.match(css, /\.remote-media-actions button\{width:44px;height:44px\}/);
  assert.match(css, /\.remote-face\{height:calc\(100dvh - 70px/);
  const page = fs.readFileSync("src/ad_linux_tv/static/remote.html", "utf8");
  assert.doesNotMatch(page, /user-scalable=no|maximum-scale=1/);
});
