"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("paired phone remote loads audio and sends bounded volume with CSRF", async () => {
  const calls = [];
  let savedSession = false;
  let holdMove = false;
  let preferredAddress = "http://192.168.1.111:8765/remote";
  let timerData = {minutes:0,remaining_seconds:0,asleep:false,error:null,phase:"idle"};
  const redirects = [];
  let delayStatus = false;
  const releaseStatuses = [];
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
    "#services", "#history-back", "#history-forward", "#remote-face", "#remote-keyboard-page", "#remote-timer-page", "#remote-menu-page", "#remote-settings-page", "#show-keyboard", "#show-timer", "#remote-timer-badge", "#show-menu", "#show-settings", "#back-to-menu", "#show-system", "#audio-output", "#audio-volume", "#audio-volume-value", "#audio-status",
    "#audio-mute", "#audio-refresh", "#audio-test", "#phone-output-volume", "#phone-output-value", "#phone-browser-volume", "#phone-browser-value", "#phone-browser-hint", "#phone-browser-mute", "#phone-player-volume", "#phone-player-value", "#phone-player-hint", "#menu-tab", "#menu-shift-tab", "#open", "#text-form", "#remote-text", "#url-form",
    "#remote-url", "#key-backspace", "#key-enter", "#key-tab", "#key-shift-tab", "#key-address", "#phone-timer-status", "#remote-share-page", "#show-share", "#share-qr", "#share-status", "#share-url", "#pad-tab", "#pad-shift-tab", "#pad-enter", "#touch-action-text", '[data-c="home"]'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  elements["#remote-timer-badge"].hidden = true;
  const timerButtons = [0, 15, 30, 60, 90, 120].map(minutes => {
    const button = new Element();
    button.dataset.phoneTimer = String(minutes);
    return button;
  });
  const context = {
    document: {addEventListener() {}, querySelector: id => elements[id], querySelectorAll: selector => selector === "[data-phone-timer]" ? timerButtons : [], createElement: () => new Element()},
    window: {scrollTo() {}, location:{href:"http://192.168.1.111:8765/remote", replace:url => redirects.push(url)}},
    setInterval: () => 1, clearInterval: () => {}, setTimeout, clearTimeout, URL, console,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      if (url === "/api/pointer" && holdMove && JSON.parse(options.body).dx !== undefined) {
        await new Promise(resolve => { releaseMoves.push(resolve); });
      }
      if (url === "/api/status") {
        const address = preferredAddress;
        if (delayStatus) await new Promise(resolve => { releaseStatuses.push(resolve); });
        return {ok:true,status:200,json:async () => ({extension_online:true,pending_commands:0,
          last_command_failure:null,preferred_remote_address:address})};
      }
      if (url === "/api/session") return {ok:savedSession, status:savedSession ? 200 : 401, json:async () => ({csrf:"test-csrf"})};
      if (url === "/api/command" && options.method === "POST")
        return {ok:true, status:202, json:async () => ({id:"test-command"})};
      const data = url === "/api/login" ? {csrf:"test-csrf"}
        : url === "/api/services" ? {services:[{id:"browser",name:"Браузер"}],remote_address:"http://192.168.1.111:8765/remote"}
          : url === "/api/audio" ? {outputs:[{id:"hdmi",name:"HDMI"}],selected:"hdmi",volume:100,muted:false,browser_volume:75,browser_muted:true}
            : url === "/api/display-timer" ? timerData
            : {extension_online:true,pending_commands:0,last_command_failure:null,preferred_remote_address:preferredAddress};
      return {ok:true,status:200,json:async () => data};
    },
  };
  context.RemoteTransport = class {
    request(csrf, method, path, body) {
      const options = method === "POST" ? {
        method, body:JSON.stringify(body), headers:{"X-CSRF-Token":csrf},
      } : {};
      return context.fetch(path, options);
    }
    close() {}
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/audio_levels.js", "utf8"), context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/pointer_acceleration.js", "utf8"), context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/remote.js", "utf8"), context);
  vm.runInContext("pointerAccelerationLevel = 0", context);
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
  vm.runInContext("requireLogin()", context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements["#controls"].hidden, false);
  assert.equal(elements["#login-panel"].hidden, true);
  const commandsBeforeTimer = calls.filter(call => call.url === "/api/command").length;
  elements["#show-timer"].onclick();
  assert.equal(elements["#remote-timer-page"].hidden, false);
  assert.equal(elements["#remote-face"].hidden, true);
  assert.equal(calls.filter(call => call.url === "/api/command").length, commandsBeforeTimer);
  await timerButtons[1].onclick();
  const timerRequest = calls.find(call => call.url === "/api/display-timer" && call.options.method === "POST");
  assert.equal(timerRequest.options.headers["X-CSRF-Token"], "test-csrf");
  assert.equal(JSON.parse(timerRequest.options.body).minutes, 15);
  assert.equal(elements["#audio-output"].value, "hdmi");
  assert.equal(elements["#phone-browser-mute"].textContent, "Включить");
  assert.equal(elements["#phone-browser-mute"].disabled, false);
  elements["#phone-browser-mute"].onclick();
  await new Promise(resolve => setImmediate(resolve));
  const unmute = calls.find(call => call.url === "/api/audio" &&
    JSON.parse(call.options.body || "{}").browser_muted === false);
  assert.equal(unmute.options.headers["X-CSRF-Token"], "test-csrf");
  elements["#audio-volume"].value = "55";
  await elements["#audio-volume"].onchange();
  const request = calls.find(call => call.url === "/api/audio" &&
    JSON.parse(call.options.body || "{}").volume === 55);
  assert.equal(request.options.headers["X-CSRF-Token"], "test-csrf");
  assert.equal(JSON.parse(request.options.body).volume, 55);
  await elements["#audio-test"].onclick();
  assert.equal(JSON.parse(calls.at(-1).options.body).test, true);
  const touchpad = elements["#remote-touchpad"];
  const touch = (pointerId, x, y, arrow = null) => ({pointerId, clientX:x, clientY:y,
    target:{closest: () => arrow ? {dataset:{arrow}} : null}, preventDefault(){}});
  touchpad.listeners.pointerdown(touch(1, 100, 100, "up"));
  touchpad.listeners.pointerup(touch(1, 100, 100, "up"));
  assert.equal(elements["#touch-action-text"].textContent, "Выбрать");
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(8, 150, 150));
  touchpad.listeners.pointerup(touch(8, 150, 150));
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(3, 50, 50));
  touchpad.listeners.pointermove(touch(3, 70, 55));
  assert.equal(elements["#touch-action-text"].textContent, "Клик");
  touchpad.listeners.pointerup(touch(3, 70, 55));
  await new Promise(resolve => setImmediate(resolve));
  touchpad.listeners.pointerdown(touch(2, 100, 100));
  touchpad.listeners.pointerup(touch(2, 100, 100));
  await new Promise(resolve => setImmediate(resolve));
  const pointerActions = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body));
  assert.deepEqual(pointerActions, [{dx:60, dy:15}, {click:true}]);
  await elements["#pad-tab"].onclick();
  await elements["#pad-shift-tab"].onclick();
  await elements["#pad-enter"].onclick();
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
  assert.deepEqual(scrolls, [-24, -4]);
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
  assert.equal(countWhileHeld, 5);
  holdMove = false;
  for (const release of releaseMoves) release();
  await new Promise(resolve => setTimeout(resolve, 70));
  const countAfter = calls.filter(call => call.url === "/api/pointer" &&
    JSON.parse(call.options.body).dx !== undefined).length;
  assert.ok(countAfter <= 5);
  const movedPixels = calls.filter(call => call.url === "/api/pointer")
    .map(call => JSON.parse(call.options.body).dx || 0).reduce((total, dx) => total + dx, 0);
  assert.equal(movedPixels, 60 + 30 + 1200);
  await elements["#history-back"].onclick();
  await elements["#history-forward"].onclick();
  await elements["#menu-tab"].onclick();
  await elements["#menu-shift-tab"].onclick();
  const history = calls.filter(call => call.url === "/api/input" && call.options.method === "POST")
    .map(call => JSON.parse(call.options.body).key);
  assert.deepEqual(history, ["up", "enter", "tab", "shift-tab", "enter", "browser-back", "browser-forward", "tab", "shift-tab"]);
  elements["#show-menu"].onclick();
  await new Promise(resolve => setTimeout(resolve, 350));
  const html = fs.readFileSync("src/ad_linux_tv/static/remote.html", "utf8");
  assert.equal((html.match(/type="range"/g) || []).length, 5);
  assert.equal(elements["#remote-face"].hidden, true);
  assert.equal(elements["#remote-menu-page"].hidden, false);
  elements["#show-settings"].onclick();
  assert.equal(elements["#remote-settings-page"].hidden, false);
  elements["#back-to-menu"].onclick();
  assert.equal(elements["#remote-menu-page"].hidden, false);
  await elements["#show-share"].onclick();
  assert.equal(elements["#remote-share-page"].hidden, false);
  assert.equal(elements["#share-url"].href, "http://192.168.1.111:8765/remote");
  assert.ok(elements["#share-qr"].src.startsWith("/api/qr?refresh="));
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
  await elements['[data-c="home"]'].onclick();
  const escape = calls.find(call => call.url === "/api/input" &&
    JSON.parse(call.options.body || "{}").key === "escape");
  assert.ok(escape);
  timerData = {minutes:15,remaining_seconds:120,asleep:false,error:null,phase:"countdown"};
  await vm.runInContext("refreshDisplayTimer()", context);
  assert.equal(elements["#remote-timer-badge"].hidden, false);
  assert.equal(elements["#remote-timer-badge"].textContent, "2:00");
  timerData = {minutes:0,remaining_seconds:0,asleep:false,error:null,phase:"idle"};
  await vm.runInContext("refreshDisplayTimer()", context);
  assert.equal(elements["#remote-timer-badge"].hidden, true);
  delayStatus = true;
  preferredAddress = "http://192.168.1.113:8765/remote";
  const stale = vm.runInContext("refreshStatus()", context);
  delayStatus = false;
  preferredAddress = "http://192.168.1.111:8765/remote";
  await vm.runInContext("refreshStatus()", context);
  for (const release of releaseStatuses) release();
  await stale;
  assert.deepEqual(redirects, []);
  preferredAddress = "http://attacker.example:8765/remote";
  await vm.runInContext("refreshStatus()", context);
  assert.deepEqual(redirects, []);
  preferredAddress = "http://192.168.1.112:8765/remote";
  await vm.runInContext("refreshStatus()", context);
  assert.deepEqual(redirects, ["http://192.168.1.112:8765/remote"]);
});
