"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {LAUNCHER} = require("../extension/tab_storage.js");

test("background listeners precede async initialization and filter launcher URL", () => {
  const events = {message:null, removed:null, updated:null, activated:null, alarm:null, startup:null, installed:null};
  let wakes = 0;
  const normalized = [];
  const browser = {
    runtime: {onMessage:{addListener:fn => {events.message = fn;}},
      onStartup:{addListener:fn => {events.startup = fn;}},
      onInstalled:{addListener:fn => {events.installed = fn;}}},
    tabs: {onRemoved:{addListener:fn => {events.removed = fn;}},
      onUpdated:{addListener:fn => {events.updated = fn;}},
      onActivated:{addListener:fn => {events.activated = fn;}}},
    alarms: {onAlarm:{addListener:fn => {events.alarm = fn;}}, create() {}},
  };
  const tabs = {onRemoved:async () => {}, normalizeMedia:async id => {normalized.push(id);}, ensureLauncher:async () => {}};
  const context = {browser, LAUNCHER, createTabController:() => tabs,
    createBridgeController:() => ({wake:() => {wakes++;}})};
  vm.runInNewContext(fs.readFileSync("extension/background.js", "utf8"), context);
  assert.ok(Object.values(events).every(Boolean));
  events.message({type:"launcher-pulse"}, {url:"http://127.0.0.1:8765/remote"});
  assert.equal(wakes, 0);
  events.message({type:"launcher-pulse"}, {url:LAUNCHER});
  events.alarm({name:"bridge-poll"});
  assert.equal(wakes, 2);
  events.updated(3, {audible:true});
  events.activated({tabId:4});
  assert.deepEqual(normalized, [3, 4]);
});

test("content-script messages answer through sendResponse only for handled commands", () => {
  let listener;
  const events = [];
  const document = {
    activeElement:{dataset:{serviceId:"svc-7"}},
    documentElement:{dataset:{bridgeServiceId:"svc-7"}},
    dispatchEvent:event => events.push(event.key || event.type),
  };
  const browser = {runtime:{
    onMessage:{addListener:fn => {listener = fn;}},
    sendMessage:async () => {},
  }};
  const context = {location:{href:LAUNCHER}, document, browser,
    Event:function (type) { return {type}; },
    KeyboardEvent:function (type, options) { return {...options, type}; }, setInterval() {}};
  vm.runInNewContext(fs.readFileSync("extension/launcher.js", "utf8"), context);
  const invoke = message => {
    let response;
    const keepChannel = listener(message, {}, value => { response = value; });
    return {keepChannel, response};
  };
  const selected = invoke({command:"ok"});
  assert.equal(selected.keepChannel, false);
  assert.equal(selected.response.service_id, "svc-7");
  assert.deepEqual(events, ["ad-linux-tv-select-for-bridge"]);
  const arrow = invoke({command:"left"});
  assert.equal(arrow.response.service_id, null);
  assert.deepEqual(events, ["ad-linux-tv-select-for-bridge", "ArrowLeft"]);
  const ignored = invoke({command:"unsupported"});
  assert.equal(ignored.keepChannel, false);
  assert.equal(ignored.response, undefined);
});

test("content script ignores other ports and localhost paths", () => {
  for (const href of ["http://127.0.0.1:8765/remote", "http://127.0.0.1:9999/"]) {
    let registered = false;
    let pulses = 0;
    const context = {location:{href}, browser:{runtime:{
      onMessage:{addListener() { registered = true; }},
      sendMessage() { pulses++; return Promise.resolve(); },
    }}, document:{}, setInterval() {}};
    vm.runInNewContext(fs.readFileSync("extension/launcher.js", "utf8"), context);
    assert.equal(registered, false);
    assert.equal(pulses, 0);
  }
});
