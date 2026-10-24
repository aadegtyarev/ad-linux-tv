"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {LAUNCHER} = require("../extension/tab_storage.js");

test("background listeners precede async initialization and filter launcher URL", () => {
  const events = {message:null, removed:null, alarm:null, startup:null, installed:null};
  let wakes = 0;
  const browser = {
    runtime: {onMessage:{addListener:fn => {events.message = fn;}},
      onStartup:{addListener:fn => {events.startup = fn;}},
      onInstalled:{addListener:fn => {events.installed = fn;}}},
    tabs: {onRemoved:{addListener:fn => {events.removed = fn;}}},
    alarms: {onAlarm:{addListener:fn => {events.alarm = fn;}}, create() {}},
  };
  const tabs = {onRemoved:async () => {}, ensureLauncher:async () => {}};
  const context = {browser, LAUNCHER, createTabController:() => tabs,
    createBridgeController:() => ({wake:() => {wakes++;}})};
  vm.runInNewContext(fs.readFileSync("extension/background.js", "utf8"), context);
  assert.ok(Object.values(events).every(Boolean));
  events.message({type:"launcher-pulse"}, {url:"http://127.0.0.1:8765/remote"});
  assert.equal(wakes, 0);
  events.message({type:"launcher-pulse"}, {url:LAUNCHER});
  events.alarm({name:"bridge-poll"});
  assert.equal(wakes, 2);
});

test("launcher content script returns tile selection without enqueueing Open", () => {
  let listener;
  const events = [];
  const document = {
    activeElement:{dataset:{serviceId:"svc-7"}},
    dispatchEvent:event => events.push(event.key),
  };
  const browser = {runtime:{
    onMessage:{addListener:fn => {listener = fn;}},
    sendMessage:async () => {},
  }};
  const context = {location:{href:LAUNCHER}, document, browser,
    KeyboardEvent:function (_type, options) { return options; }, setInterval() {}};
  vm.runInNewContext(fs.readFileSync("extension/launcher.js", "utf8"), context);
  assert.equal(listener({command:"ok"}).service_id, "svc-7");
  assert.deepEqual(events, []);
  document.activeElement = {id:"next"};
  assert.equal(listener({command:"ok"}).service_id, null);
  assert.deepEqual(events, ["Enter"]);
  listener({command:"left"});
  assert.deepEqual(events, ["Enter", "ArrowLeft"]);
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
