"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {createTabController} = require("../extension/tabs.js");
const {createBridgeController} = require("../extension/bridge.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");
const {launcher, ready} = require("./helpers/launcher_mock.js");

async function orderedOKHome(lostFocus) {
  const ui = launcher();
  await ready();
  const serviceId = lostFocus ? "svc-5" : "svc-0";
  if (lostFocus) {
    ui.elements["#tiles"].children[5].focus();
    ui.doc.activeElement = ui.doc.body;
  }
  let listener;
  const browser = {runtime:{
    onMessage:{addListener:fn => {listener = fn;}},
    sendMessage:async () => {},
  }};
  const content = {location:{href:LAUNCHER}, document:ui.doc, browser,
    Event:function (type) { return {type}; },
    KeyboardEvent:function (type, options) { return {...options, type}; }, setInterval() {}};
  vm.runInNewContext(fs.readFileSync("extension/launcher.js", "utf8"), content);
  const mock = browserMock([{id:1, windowId:1, url:LAUNCHER}]);
  mock.fetcher = async () => ({ok:true, json:async () => ({services:[{
    id:serviceId, url:`https://services.example/${serviceId}`,
  }]})});
  mock.api.tabs.sendMessage = async (tabId, message) => {
    let response;
    const keep = listener(message, {tab:{id:tabId}, url:LAUNCHER}, value => { response = value; });
    if (keep && typeof keep.then === "function") await keep;
    return response;
  };
  const queue = [
    {id:`integrated-ok-${lostFocus}`, command:"ok"},
    {id:`integrated-home-${lostFocus}`, command:"home"},
  ];
  let offset = 0;
  const wire = async (url, options = {}) => {
    if (url.endsWith("/poll")) return {ok:true, json:async () => [queue[offset]]};
    if (url.endsWith("/media")) return {ok:true};
    offset++;
    return {ok:true};
  };
  const bridge = createBridgeController(createTabController(mock.api, mock.fetcher), wire, {error() {}});
  await bridge.wake();
  const service = [...mock.tabs.values()].find(tab => tab.url === `https://services.example/${serviceId}`);
  assert.ok(service, `selected ${serviceId} should open inline`);
  await bridge.wake();
  assert.equal((await mock.api.tabs.query({active:true}))[0].url, LAUNCHER);
  assert.equal(offset, 2);
  assert.equal(ui.calls.filter(call => call.url === "/api/command").length, 0);
}

test("integrated bridge OK then Home preserves order with initial DOM focus", async () => {
  await orderedOKHome(false);
});

test("integrated bridge OK then Home preserves order after DOM focus loss", async () => {
  await orderedOKHome(true);
});
