"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController} = require("../extension/tabs.js");
const {createBridgeController} = require("../extension/bridge.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");

let sequence = 1000;
function item(command, extra = {}) {
  return {id:`bridge-command-${++sequence}`, command, ...extra};
}

test("overlapping wakes share one poll and one in-flight execution", async () => {
  let release;
  let polls = 0;
  const calls = [];
  const tabs = {restore:async () => {}, execute:async () => new Promise(resolve => {
    release = () => resolve({outcome:"completed"});
  })};
  const fetcher = async (url, options = {}) => {
    calls.push([url, options]);
    if (url.endsWith("/poll")) {
      polls++;
      return {ok:true, json:async () => [item("home")]};
    }
    return {ok:true};
  };
  const bridge = createBridgeController(tabs, fetcher, {error() {}});
  const first = bridge.wake();
  const second = bridge.wake();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(polls, 1);
  release();
  await Promise.all([first, second]);
  assert.equal(JSON.parse(calls[1][1].body).outcome, "completed");
});

test("ACK loss redelivery acknowledges completed ID without repeating effect", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const operation = item("open", {service_id:"one"});
  let ackAttempts = 0;
  const fetcher = async url => {
    if (url.endsWith("/poll")) return {ok:true, json:async () => [operation]};
    ackAttempts++;
    return {ok:ackAttempts > 1};
  };
  const first = createTabController(mock.api, mock.fetcher);
  await createBridgeController(first, fetcher, {error() {}}).wake();
  const creations = mock.calls.filter(call => call[0] === "create").length;
  const reloaded = createTabController(mock.api, mock.fetcher);
  await createBridgeController(reloaded, fetcher, {error() {}}).wake();
  assert.equal(ackAttempts, 2);
  assert.equal(mock.calls.filter(call => call[0] === "create").length, creations);
  const restarted = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  await restarted.api.storage.local.set({...mock.storage.local});
  const afterRestart = createTabController(restarted.api, restarted.fetcher);
  await createBridgeController(afterRestart, fetcher, {error() {}}).wake();
  assert.equal(ackAttempts, 3);
  assert.equal(restarted.calls.filter(call => call[0] === "create").length, 0);
});

test("OK resolves selected service inline before following Home", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const queue = [item("ok"), item("home")];
  let offset = 0;
  const wire = async (url, options = {}) => {
    if (url.endsWith("/poll")) return {ok:true, json:async () => queue[offset] ? [queue[offset]] : []};
    const ack = JSON.parse(options.body);
    assert.equal(ack.outcome, "completed");
    offset++;
    return {ok:true};
  };
  const controller = createTabController(mock.api, mock.fetcher);
  const bridge = createBridgeController(controller, wire, {error() {}});
  await bridge.wake();
  const opened = controller.getState().managed.one.tabId;
  assert.equal(mock.tabs.get(opened).url, "https://same.example/watch/one");
  await bridge.wake();
  assert.ok(!mock.tabs.has(opened));
  assert.equal((await mock.api.tabs.query({active:true}))[0].url, LAUNCHER);
  assert.equal(offset, 2);
});
