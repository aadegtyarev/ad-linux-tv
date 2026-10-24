"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController, LAUNCHER} = require("../extension/tabs.js");
const {createBridgeController, BRIDGE, BRIDGE_VALUE} = require("../extension/bridge.js");
const {browserMock} = require("./helpers/browser_mock.js");

test("stored tab ownership separates same-origin services and protects unrelated tabs", async () => {
  const mock = browserMock([
    {id:1, windowId:1, url:LAUNCHER},
    {id:2, windowId:1, url:"https://same.example/watch/unrelated", active:true},
  ]);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  await controller.execute({command:"home"});
  assert.ok(mock.tabs.has(2));
  await controller.execute({command:"open", service_id:"one"});
  const first = controller.getState().managed.one.tabId;
  await controller.execute({command:"open", service_id:"two"});
  const second = controller.getState().managed.two.tabId;
  assert.notEqual(first, second);
  mock.tabs.get(first).url = "https://login.example/redirect";
  await mock.api.tabs.update(second, {active:true});
  await controller.execute({command:"home"});
  assert.ok(mock.tabs.has(2));
  assert.ok(mock.tabs.has(first));
  assert.ok(!mock.tabs.has(second));
  await controller.onRemoved(second);
  assert.equal(mock.storage.managedTabs.two, undefined);
});

test("restored owned redirects support back and refresh without origin claiming", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const firstController = createTabController(mock.api, mock.fetcher);
  await firstController.restore();
  await firstController.execute({command:"open", service_id:"one"});
  const id = firstController.getState().managed.one.tabId;
  mock.tabs.get(id).windowId = 2;
  await firstController.execute({command:"open", service_id:"one"});
  assert.equal(firstController.getState().managed.one.windowId, 2);
  assert.ok(mock.calls.some(call => call[0] === "window" && call[1] === 2));
  mock.tabs.get(id).url = "https://login.example/redirect";
  const restored = createTabController(mock.api, mock.fetcher);
  await restored.restore();
  assert.equal(restored.getState().managed.one.tabId, id);
  await restored.execute({command:"back"});
  await restored.execute({command:"refresh"});
  assert.deepEqual(mock.calls.filter(call => ["back", "reload"].includes(call[0])).map(call => call[0]), ["back", "reload"]);
});

test("bridge polls are single-flight and acknowledge only completed commands", async () => {
  let release;
  let polls = 0;
  const calls = [];
  const tabs = {restore:async () => {}, execute:async () => new Promise(resolve => { release = resolve; })};
  const fetcher = async (url, options = {}) => {
    calls.push([url, options]);
    if (url.endsWith("/poll")) {
      polls++;
      return {ok:true, json:async () => [{id:"queued-1", command:"home"}]};
    }
    return {ok:true};
  };
  const bridge = createBridgeController(tabs, fetcher);
  const first = bridge.wake();
  const second = bridge.wake();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(polls, 1);
  assert.equal(calls[0][1].headers[BRIDGE], BRIDGE_VALUE);
  release();
  await Promise.all([first, second]);
  assert.equal(calls[1][1].body, JSON.stringify({id:"queued-1"}));
  const failing = createBridgeController(
    {restore:async () => {}, execute:async () => {throw Error("fail");}}, fetcher, {error() {}}
  );
  calls.length = 0;
  await failing.wake();
  assert.equal(calls.length, 1);
});
