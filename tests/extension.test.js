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
  assert.ok(!mock.tabs.has(first));
  assert.equal(mock.calls.filter(call => call[0] === "fetch" && call[1].endsWith("/api/services")).length, 2);
  await mock.api.tabs.update(second, {active:true});
  await command(controller, "home");
  assert.ok(mock.tabs.has(2));
  assert.ok(!mock.tabs.has(second));
  assert.deepEqual(controller.getState().managed, {});
  await controller.onRemoved(second);
  assert.equal(mock.storage.session.managedTabs.two, undefined);
});

test("switching and Home close every managed service tab", async () => {
  const catalog = ["kinopoisk", "kion", "youtube", "vk", "music", "browser"]
    .map(id => ({id, url:`https://service.example/${id}`}));
  const mock = browserMock([
    {id:1, windowId:1, url:LAUNCHER},
    {id:2, windowId:1, url:"https://personal.example/", active:true},
  ], catalog);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  let previous = null;
  for (const service of catalog) {
    await command(controller, "open", {service_id:service.id});
    const current = controller.getState().managed[service.id].tabId;
    if (previous !== null) assert.ok(!mock.tabs.has(previous));
    assert.equal(Object.keys(controller.getState().managed).length, 1);
    previous = current;
  }
  await command(controller, "home");
  assert.ok(!mock.tabs.has(previous));
  assert.ok(mock.tabs.has(2));
  assert.deepEqual(controller.getState().managed, {});
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

test("player volume targets only the active managed service tab and reports its result", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  await command(controller, "open", {service_id:"one"});
  const managed = controller.getState().managed.one.tabId;
  const read = await command(controller, "player_get");
  assert.equal(read.volume, 75);
  const set = await command(controller, "player_set", {volume:40});
  assert.equal(set.volume, 75);
  const scripts = mock.calls.filter(call => call[0] === "script");
  assert.deepEqual(scripts.map(call => call[1].target), [
    {tabId:managed, allFrames:true}, {tabId:managed, allFrames:true},
  ]);
  assert.deepEqual(scripts[1][1].args, ["set", 40]);
  const paused = await command(controller, "player_pause");
  assert.equal(paused.volume, 75);
  assert.deepEqual(mock.calls.filter(call => call[0] === "script").at(-1)[1].args,
    ["pause", null]);
  mock.tabs.get(managed).audible = true;
  assert.deepEqual(await command(controller, "player_pause"),
    {outcome:"failed", reason:"operation"});
  mock.tabs.get(managed).audible = false;
  mock.setScriptingResults([{result:null}, {result:32}]);
  assert.equal((await command(controller, "player_get")).volume, 32);
  mock.setScriptingResults([{result:null}]);
  assert.deepEqual(await command(controller, "player_get"), {outcome:"failed", reason:"no_media"});
  await mock.api.tabs.create({url:"https://unrelated.example/", active:true});
  const before = mock.calls.filter(call => call[0] === "script").length;
  assert.deepEqual(await command(controller, "player_set", {volume:0}),
    {outcome:"failed", reason:"no_media"});
  assert.equal(mock.calls.filter(call => call[0] === "script").length, before);
});

test("volume normalization injects only into the active launcher-owned tab", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  await command(controller, "open", {service_id:"one"});
  const managed = controller.getState().managed.one.tabId;
  await controller.normalizeMedia(managed);
  const scripts = mock.calls.filter(call => call[0] === "script");
  assert.equal(scripts.length, 1);
  assert.deepEqual(scripts[0][1].target, {tabId:managed, allFrames:true});
  await mock.api.tabs.create({url:"https://unrelated.example/",active:true});
  await controller.normalizeMedia(managed);
  assert.equal(mock.calls.filter(call => call[0] === "script").length, 1);
});
