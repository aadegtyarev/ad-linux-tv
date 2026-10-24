"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("paired phone remote loads audio and sends bounded volume with CSRF", async () => {
  const calls = [];
  let savedSession = false;
  let holdMove = false;
  const releaseMoves = [];
  class Element {
    constructor() { this.dataset = {}; this.children = []; this.value = ""; this.hidden = false; this.listeners = {}; this.style = {}; this.classes = new Set(); this.classList = {add: value => this.classes.add(value), remove: value => this.classes.delete(value)}; }
    replaceChildren() { this.children = []; }
    append(item) { this.children.push(item); }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    setPointerCapture() {}
    getBoundingClientRect() { return {left:0, top:0, width:300, height:300}; }
    setAttribute(name, value) { this[name] = value; }
    focus() {}
  }
  const ids = ["#message", "#connecting", "#login-error", "#login", "#login-panel", "#controls", "#status", "#command-status", "#remote-touchpad", "#touch-indicator", "#touch-indicator-2", "#pin", "#pin-visibility",
    "#services", "#history-back", "#history-forward", "#video-fullscreen", "#video-exit", "#remote-face", "#remote-keyboard-page", "#remote-menu-page", "#show-keyboard", "#show-menu", "#show-system", "#audio-output", "#audio-volume", "#audio-volume-value", "#audio-status",
    "#audio-mute", "#audio-refresh", "#audio-test", "#browser-volume", "#browser-volume-value", "#browser-volume-hint", "#open", "#text-form", "#remote-text", "#url-form",
    "#remote-url", "#key-backspace", "#key-enter", "#key-tab", "#key-shift-tab", "#key-address"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const context = {
    document: {addEventListener() {}, querySelector: id => elements[id], querySelectorAll: () => [], createElement: () => new Element()},
    window: {scrollTo() {}},
    setInterval: () => 1, clearInterval: () => {}, setTimeout, clearTimeout, URL, console,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      if (url === "/api/pointer" && holdMove && JSON.parse(options.body).dx !== undefined) {
        await new Promise(resolve => { releaseMoves.push(resolve); });
      }
      if (url === "/api/session") return {ok:savedSession, status:savedSession ? 200 : 401, json:async () => ({csrf:"test-csrf"})};
      const data = url === "/api/login" ? {csrf:"test-csrf"}
        : url === "/api/services" ? {services:[{id:"browser",name:"Браузер"}]}
          : url === "/api/audio" ? {outputs:[{id:"hdmi",name:"HDMI"}],selected:"hdmi",volume:100,muted:false,browser_volume:75}
            : {extension_online:true,pending_commands:0,last_command_failure:null};
      return {ok:true,status:200,json:async () => data};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/remote.js", "utf8"), context);
  elements["#pin"].value = "test-pin";
  elements["#pin"].type = "password";
  elements["#pin-visibility"].onclick();
  assert.equal(elements["#pin"].type, "text");
  assert.equal(elements["#pin"].value, "test-pin");
  elements["#pin-visibility"].onclick();
  assert.equal(elements["#pin"].type, "password");
  await elements["#login"].onsubmit({preventDefault(){}});
  await new Promise(resolve => setImmediate(resolve));
  const loginsBeforeRestore = calls.filter(call => call.url === "/api/login").length;
  elements["#controls"].hidden = true;
  elements["#connecting"].hidden = false;
  savedSession = true;
  await vm.runInContext("restoreLogin()", context);
  assert.equal(elements["#controls"].hidden, false);
  assert.equal(elements["#connecting"].hidden, true);
  assert.equal(calls.filter(call => call.url === "/api/login").length, loginsBeforeRestore);
  assert.equal(elements["#audio-output"].value, "hdmi");
  elements["#audio-volume"].value = "55";
  await elements["#audio-volume"].onchange();
  const request = calls.find(call => call.url === "/api/audio" && call.options.method === "POST");
  assert.equal(request.options.headers["X-CSRF-Token"], "test-csrf");
  assert.equal(JSON.parse(request.options.body).volume, 55);
  elements["#browser-volume"].value = "60";
  await elements["#browser-volume"].onchange();
  const browser = calls.find(call => call.url === "/api/audio" &&
    JSON.parse(call.options.body || "{}").browser_volume === 60);
  assert.equal(browser.options.headers["X-CSRF-Token"], "test-csrf");
  await elements["#audio-test"].onclick();
  assert.equal(JSON.parse(calls.at(-1).options.body).test, true);
  const touchpad = elements["#remote-touchpad"];
  const touch = (pointerId, x, y, arrow = null) => ({pointerId, clientX:x, clientY:y,
    target:{closest: () => arrow ? {dataset:{arrow}} : null}, preventDefault(){}});
  touchpad.listeners.pointerdown(touch(1, 100, 100, "up"));
  touchpad.listeners.pointerup(touch(1, 100, 100, "up"));
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(8, 150, 150));
  touchpad.listeners.pointerup(touch(8, 150, 150));
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(3, 50, 50));
  touchpad.listeners.pointermove(touch(3, 70, 55));
  touchpad.listeners.pointerup(touch(3, 70, 55));
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(2, 100, 100));
  touchpad.listeners.pointerup(touch(2, 100, 100));
  await new Promise(resolve => setImmediate(resolve));
  const pointerActions = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body));
  assert.deepEqual(pointerActions, [{dx:60, dy:15}, {click:true}]);
  touchpad.listeners.pointerdown(touch(4, 100, 100));
  touchpad.listeners.pointerdown(touch(5, 120, 100));
  assert.equal(elements["#touch-indicator"].hidden, false);
  assert.equal(elements["#touch-indicator-2"].hidden, false);
  touchpad.listeners.pointermove(touch(4, 100, 114));
  touchpad.listeners.pointermove(touch(5, 120, 114));
  touchpad.listeners.pointerup(touch(4, 100, 114));
  touchpad.listeners.pointermove(touch(5, 130, 130));
  touchpad.listeners.pointerup(touch(5, 130, 130));
  await new Promise(resolve => setTimeout(resolve, 70));
  const scrolls = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body).scroll).filter(value => value !== undefined);
  assert.deepEqual(scrolls, [-42]);
  assert.equal(elements["#touch-indicator-2"].hidden, true);
  assert.equal(elements["#touch-indicator"].hidden, true);
  touchpad.listeners.pointerdown(touch(6, 50, 50));
  touchpad.listeners.pointermove(touch(6, 70, 50));
  touchpad.listeners.pointercancel(touch(6, 70, 50));
  await new Promise(resolve => setTimeout(resolve, 70));
  const moves = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body).dx).filter(value => value !== undefined);
  assert.deepEqual(moves, [60, 30]);
  holdMove = true;
  touchpad.listeners.pointerdown(touch(7, 20, 20));
  touchpad.listeners.pointermove(touch(7, 40, 20));
  await new Promise(resolve => setTimeout(resolve, 60));
  for (let x = 50; x <= 420; x += 10) touchpad.listeners.pointermove(touch(7, x, 20));
  touchpad.listeners.pointerup(touch(7, 420, 20));
  const countWhileHeld = calls.filter(call => call.url === "/api/pointer" &&
    JSON.parse(call.options.body).dx !== undefined).length;
  assert.ok(countWhileHeld <= 6);
  holdMove = false;
  for (const release of releaseMoves) release();
  await new Promise(resolve => setTimeout(resolve, 70));
  const countAfter = calls.filter(call => call.url === "/api/pointer" &&
    JSON.parse(call.options.body).dx !== undefined).length;
  assert.ok(countAfter <= 7);
  const movedPixels = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body).dx || 0).reduce((total, dx) => total + dx, 0);
  assert.equal(movedPixels, 60 + 30 + 1200);
  await elements["#history-back"].onclick();
  await elements["#history-forward"].onclick();
  await elements["#video-fullscreen"].onclick();
  await elements["#video-exit"].onclick();
  const history = calls.filter(call => call.url === "/api/input" && call.options.method === "POST")
    .map(call => JSON.parse(call.options.body).key);
  assert.deepEqual(history, ["up", "ok", "browser-back", "browser-forward", "video-fullscreen", "escape"]);
  elements["#show-menu"].onclick();
  assert.equal(elements["#remote-face"].hidden, true);
  assert.equal(elements["#remote-menu-page"].hidden, false);
  elements["#show-keyboard"].onclick();
  assert.equal(elements["#remote-keyboard-page"].hidden, false);
  await elements["#show-system"].onclick();
  const home = calls.find(call => call.url === "/api/command" &&
    JSON.parse(call.options.body || "{}").command === "home");
  const system = calls.find(call => call.url === "/api/input" &&
    JSON.parse(call.options.body || "{}").key === "system");
  assert.ok(home);
  assert.ok(system);
  assert.equal(system.options.headers["X-CSRF-Token"], "test-csrf");
});
