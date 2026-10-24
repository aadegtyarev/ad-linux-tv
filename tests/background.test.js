"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {LAUNCHER} = require("../extension/tabs.js");

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
