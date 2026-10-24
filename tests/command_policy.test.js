"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController} = require("../extension/tabs.js");
const {createBridgeController} = require("../extension/bridge.js");
const {createCommandLedger, LIMIT} = require("../extension/command_ledger.js");
const {browserMock} = require("./helpers/browser_mock.js");
const {LAUNCHER} = require("../extension/tab_storage.js");

let sequence = 2000;
function command(controller, name, extra = {}, id = `policy-command-${++sequence}`) {
  return controller.execute({id, command:name, ...extra});
}

test("Back without history is a successful no-op and FIFO continues", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const controller = createTabController(mock.api, mock.fetcher);
  await controller.restore();
  await command(controller, "open", {service_id:"one"});
  const id = controller.getState().managed.one.tabId;
  mock.api.tabs.goBack = async tabId => {
    mock.calls.push(["back", tabId]);
    throw Error("Cannot go back");
  };
  assert.deepEqual(await command(controller, "back"), {outcome:"completed"});
  assert.deepEqual(await command(controller, "home"), {outcome:"completed"});
  assert.ok(!mock.tabs.has(id));
});

test("preparation failures dead-letter after three attempts and release FIFO", async () => {
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  const controller = createTabController(mock.api, async () => ({ok:false}));
  const queue = [
    {id:"retry-open-command-1", command:"open", service_id:"one"},
    {id:"retry-home-command-2", command:"home"},
  ];
  let offset = 0;
  const acknowledgements = [];
  const wire = async (url, options = {}) => {
    if (url.endsWith("/poll")) return {ok:true, json:async () => [queue[offset]]};
    acknowledgements.push(JSON.parse(options.body));
    offset++;
    return {ok:true};
  };
  const bridge = createBridgeController(controller, wire, {error() {}});
  await bridge.wake();
  await bridge.wake();
  await bridge.wake();
  assert.equal(acknowledgements[0].reason, "retry_exhausted");
  await bridge.wake();
  assert.equal(acknowledgements[1].outcome, "completed");
  assert.equal(offset, 2);
});

test("claimed command is not repeated after context loss; ledger evicts old terminal IDs", async () => {
  const memory = {};
  const storage = {get:async key => ({[key]:memory[key]}), set:async value => Object.assign(memory, value)};
  const ledger = createCommandLedger(storage);
  const id = "claimed-command-0001";
  await ledger.begin(id);
  await ledger.claim(id);
  const reloaded = createCommandLedger(storage);
  assert.deepEqual(await reloaded.begin(id), {outcome:"uncertain", reason:"interrupted"});
  for (let index = 0; index < LIMIT + 5; index++) {
    const next = `eviction-command-${String(index).padStart(4, "0")}`;
    await reloaded.begin(next);
    await reloaded.claim(next);
    await reloaded.complete(next);
  }
  assert.equal(Object.keys(reloaded.getState()).length, LIMIT);
  assert.equal(reloaded.getState()["eviction-command-0000"], undefined);
  assert.equal(reloaded.getState()[`eviction-command-${String(LIMIT + 4).padStart(4, "0")}`].state, "completed");
});
