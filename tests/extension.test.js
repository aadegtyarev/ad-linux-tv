"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController} = require("../extension/tabs.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");
let sequence = 0;
const command = (controller, name, extra = {}) => controller.execute({
  id:`test-command-${String(++sequence).padStart(6, "0")}`, command:name, ...extra,
});

test("session ownership separates same-origin services and protects unrelated tabs", async () => {
  const mock = browserMock([
    {id:1, windowId:1, url:LAUNCHER},
    {id:2, windowId:1, url:"https://same.example/watch/unrelated", active:true},
  ]);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  await command(controller, "home");
  assert.ok(mock.tabs.has(2));
  await command(controller, "open", {service_id:"one"});
  const first = controller.getState().managed.one.tabId;
  await command(controller, "open", {service_id:"two"});
  const second = controller.getState().managed.two.tabId;
  assert.notEqual(first, second);
  assert.equal(mock.calls.filter(call => call[0] === "fetch" && call[1].endsWith("/api/services")).length, 2);
  mock.tabs.get(first).url = "https://login.example/redirect";
  await mock.api.tabs.update(second, {active:true});
  await command(controller, "home");
  assert.ok(mock.tabs.has(2));
  assert.ok(mock.tabs.has(first));
  assert.ok(!mock.tabs.has(second));
  await controller.onRemoved(second);
  assert.equal(mock.storage.session.managedTabs.two, undefined);
});

test("event-page reload preserves managed redirects within the browser session", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const first = createTabController(mock.api, mock.fetcher);
  await first.restore();
  await command(first, "open", {service_id:"one"});
  const id = first.getState().managed.one.tabId;
  mock.tabs.get(id).windowId = 2;
  await command(first, "open", {service_id:"one"});
  assert.equal(first.getState().managed.one.windowId, 2);
  assert.ok(mock.calls.some(call => call[0] === "window" && call[1] === 2));
  mock.tabs.get(id).url = "https://login.example/redirect";
  const restored = createTabController(mock.api, mock.fetcher);
  await restored.restore();
  assert.equal(restored.getState().managed.one.tabId, id);
  await command(restored, "back");
  await command(restored, "refresh");
  assert.deepEqual(mock.calls.filter(call => ["back", "reload"].includes(call[0])).map(call => call[0]), ["back", "reload"]);
});

test("browser restart clears ownership so a reused ID stays unmanaged", async () => {
  const prior = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const beforeRestart = createTabController(prior.api, prior.fetcher);
  await beforeRestart.restore();
  await command(beforeRestart, "open", {service_id:"one"});
  const reusedId = beforeRestart.getState().managed.one.tabId;
  const restarted = browserMock([
    {id:1, windowId:1, url:LAUNCHER},
    {id:reusedId, windowId:1, url:"https://same.example/unrelated", active:true},
  ]);
  await restarted.api.storage.local.set({managedTabs:{one:{tabId:reusedId, windowId:1}}});
  const controller = createTabController(restarted.api, restarted.fetcher);
  await controller.restore();
  assert.deepEqual(controller.getState().managed, {});
  await command(controller, "back");
  await command(controller, "refresh");
  await command(controller, "home");
  assert.equal(restarted.tabs.get(reusedId).url, "https://same.example/unrelated");
  assert.ok(!restarted.calls.some(call => ["remove", "back", "reload"].includes(call[0]) && call[1] === reusedId));
  await command(controller, "open", {service_id:"one"});
  assert.equal(restarted.tabs.get(reusedId).url, "https://same.example/unrelated");
  assert.notEqual(controller.getState().managed.one.tabId, reusedId);
});
