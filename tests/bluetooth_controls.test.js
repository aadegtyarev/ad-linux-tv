"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("src/ad_linux_tv/static/bluetooth_controls.js", "utf8");
const css = fs.readFileSync("src/ad_linux_tv/static/bluetooth_controls.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const hiddenSelectors = [...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)]
  .filter(match => /display:\s*none/.test(match[2])).flatMap(match => match[1].trim().split(","));
const lease = "a".repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
const settle = async () => { for (let n = 0; n < 60; n++) await Promise.resolve(); };

// Small DOM with real detach/focus and text-only semantics, not a markup parser.
class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = document; this.children = [];
    this.parentElement = null; this.dataset = {}; this.attributes = {}; this.value = ""; this.style = {};
    this.disabled = false; this.hidden = false; this._text = ""; this.classList = {add() {}};
  }
  append(child) { child.parentElement = this; this.children.push(child); }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  replaceChildren(...nodes) {
    if (this.children.some(child => child.contains(this.ownerDocument.activeElement)))
      this.ownerDocument.activeElement = this.ownerDocument.body;
    for (const child of this.children) child.parentElement = null;
    this.children = []; this._text = "";
    for (const node of nodes) this.append(node);
  }
  set textContent(text) { this.replaceChildren(); this._text = String(text); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(" "); }
  set innerHTML(value) { throw new Error(`unsafe markup: ${value}`); }
  setAttribute(key, value) { this.attributes[key] = value; }
  matches(selector) {
    const parts = selector.trim().split(/\s+/);
    if (parts.length > 1) {
      const last = parts.pop();
      if (!this.matches(last)) return false;
      for (let ancestor = this.parentElement; ancestor; ancestor = ancestor.parentElement)
        if (ancestor.matches(parts.join(" "))) return true;
      return false;
    }
    if (selector === "[hidden]") return this.hidden;
    if (selector === "[data-secret]") return this.dataset.secret !== undefined;
    if (selector.startsWith(".")) {
      const classes = (this.className || "").split(/\s+/);
      const not = selector.match(/:not\(\.([\w-]+)\)/);
      if (not && classes.includes(not[1])) return false;
      const positive = selector.replace(/:not\([^)]*\)/g, "");
      return [...positive.matchAll(/\.([\w-]+)/g)].every(match => classes.includes(match[1])) &&
        (!positive.includes(":empty") || (!this._text && !this.children.length));
    }
    return this.tagName.toLowerCase() === selector;
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  querySelectorAll(selector) {
    const selectors = selector.split(",").map(item => item.trim());
    return this.children.flatMap(child => [
      ...(selectors.some(selector => child.matches(selector)) ? [child] : []), ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  rendered() {
    if (!this.ownerDocument.body.contains(this)) return false;
    for (let node = this; node; node = node.parentElement)
      if (node.hidden || node.style.display === "none" || node.style.visibility === "hidden" ||
          hiddenSelectors.some(selector => node.matches(selector))) return false;
    return true;
  }
  focus() {
    const focusable = ["BUTTON", "INPUT", "SELECT"].includes(this.tagName) || typeof this.tabIndex === "number";
    if (focusable && !this.disabled && this.type !== "hidden" && this.rendered())
      this.ownerDocument.activeElement = this;
  }
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
}
class Document {
  constructor() { this.hidden = false; this.listeners = new Set(); this.body = new Element("body", this); this.activeElement = this.body; }
  createElement(tag) { return new Element(tag, this); }
  addEventListener(type, listener) { assert.equal(type, "visibilitychange"); this.listeners.add(listener); }
  removeEventListener(type, listener) { assert.equal(type, "visibilitychange"); this.listeners.delete(listener); }
  visibility(hidden) { this.hidden = hidden; for (const listener of [...this.listeners]) listener(); }
}
class Clock {
  constructor() { this.time = 0; this.id = 0; this.jobs = new Map(); }
  now() { return this.time; }
  setTimeout(fn, delay) { const id = ++this.id; this.jobs.set(id, {fn, at: this.time + delay}); return id; }
  clearTimeout(id) { this.jobs.delete(id); }
  async tick(delay) {
    const until = this.time + delay;
    for (;;) {
      const next = [...this.jobs].filter(([, job]) => job.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      this.time = Math.max(this.time, next[1].at); this.jobs.delete(next[0]); next[1].fn(); await settle();
    }
    this.time = until; await settle();
  }
}
function snapshot(changes = {}) {
  return {
    available: true, reason: "", revision: 7,
    adapter: {id: "adapter", powered: true, discovering: false},
    devices: [{id: "device", name: "Пульт", paired: true, connected: true, selected: true, input_available: true}],
    remote: {device_id: "device", connected: true, input_available: true, reason: "", bindings: {KEY_ENTER: "ok"}},
    operation: null, ...changes,
  };
}
const operation = (kind, changes = {}) => ({id: "operation", kind, phase: "waiting", device_id: "device", remaining_ms: 20000, error: "", ...changes});
const response = (state, extras = {}, status = 200) => ({ok: status >= 200 && status < 300, status, json: async () => clone({state, ...extras})});
function panel(state = snapshot()) {
  const document = new Document(); const root = document.createElement("section"); document.body.append(root);
  const clock = new Clock(); const calls = []; const replies = []; const invocations = [];
  const context = vm.createContext({console});
  vm.runInContext(source + "\nglobalThis.Controls = BluetoothControls;", context);
  const ui = {state, root, document, clock, calls, replies, invocations, auth: 0, changes: 0};
  ui.controls = new context.Controls(root, async (method, path, body) => {
    invocations.push({method, op: body?.op, at: clock.now(), active: ui.controls.active,
      generation: ui.controls.generation, epoch: ui.controls.transportEpoch});
    ui.onRequest?.(method, body);
    calls.push({method, path, ...(body ? {body: clone(body)} : {})});
    if (replies.length) return replies.shift()(method, body);
    if (ui.server) return ui.server(method, body);
    return response(ui.state, body?.op === "acquire" ? {lease} : {});
  }, {clock, onAuthLost: () => ui.auth++, onActionsChanged: () => ui.changes++});
  ui.find = key => root.querySelectorAll("button, input, select").find(element => element.dataset.btKey === key);
  ui.click = async key => { const button = ui.find(key); assert.ok(button, `missing ${key}`); assert.equal(button.disabled, false, `disabled ${key}`); button.onclick(); await settle(); };
  ui.reply = (nextState, extras = {}, status = 200) => replies.push(() => response(nextState, extras, status));
  ui.start = async () => { await ui.controls.activate(); await settle(); return ui; };
  ui.poll = async (nextState, extras = {}, status = 200) => { if (nextState) ui.reply(nextState, extras, status); await clock.tick(5000); };
  return ui;
}
async function pairing(kind, extras = {}) {
  const ui = await panel().start();
  const state = snapshot({operation: operation("pair")});
  ui.reply(state, {challenge: {id: "challenge", kind, remaining_ms: 10000, ...extras}});
  await ui.poll(); return ui;
}
function lastBody(ui) { return ui.calls.at(-1).body; }

// Wire compatibility and fixed-catalogue authority.
test("BluetoothControls activate uses envelope GET then exactly one acquire; idempotent activation", async () => {
  const ui = await panel().start();
  await ui.controls.activate();
  assert.deepEqual(ui.calls, [{method: "GET", path: "/api/bluetooth"}, {method: "POST", path: "/api/bluetooth", body: {op: "acquire"}}]);
  assert.equal(ui.controls.lease, lease);
  assert.ok(!ui.root.textContent.includes(lease));
  assert.ok(!JSON.stringify(ui.root.dataset).includes(lease));
  await ui.poll();
  assert.deepEqual(lastBody(ui), {op: "poll", lease});
});
test("BluetoothControls catalogues match parent-owned schema exactly", () => {
  const ui = panel();
  const schema = fs.readFileSync("src/ad_linux_tv/bluetooth_schema.py", "utf8");
  const actions = [...schema.split("ACTIONS = (")[1].split(")")[0].matchAll(/"([a-z_]+)"/g)].map(match => match[1]);
  const keys = [...schema.split("BUTTON_CODES =")[1].split("_ADDRESS")[0].matchAll(/"(KEY_[A-Z]+)"/g)].map(match => match[1]);
  assert.deepEqual(Object.keys(ui.controls.constructor.actions), actions);
  assert.deepEqual(Array.from(ui.controls.constructor.keys), keys);
});
for (const [key, op, deviceChanges] of [
  ["pair", "pair", {paired: false, connected: false}],
  ["connect", "connect", {connected: false}], ["disconnect", "disconnect", {}],
]) test(`BluetoothControls ${op} sends only frozen selected-device DTO`, async () => {
  const state = snapshot(); Object.assign(state.devices[0], deviceChanges);
  const ui = await panel(state).start(); await ui.click("device:device");
  ui.reply(snapshot({operation: operation(op, {phase: "accepted"})}), {}, 202);
  await ui.click(key);
  assert.deepEqual(lastBody(ui), {op, lease, device_id: "device"});
  assert.match(ui.root.textContent, /Запрос принят/);
});
test("BluetoothControls discover and cancel are explicit bounded operation DTOs", async () => {
  const ui = await panel().start();
  ui.reply(snapshot({operation: operation("discover"), adapter: {id: "adapter", powered: true, discovering: true}}), {}, 202);
  await ui.click("discover"); assert.deepEqual(lastBody(ui), {op: "discover", lease});
  assert.match(ui.root.textContent, /Поиск устройств идёт/);
  assert.equal(ui.find("learn"), undefined);
  await ui.click("cancel");
  assert.deepEqual(lastBody(ui), {op: "cancel", lease, operation_id: "operation"});
});
test("BluetoothControls forget requires owner confirmation and binds operation, not current selection", async () => {
  const ui = await panel().start(); assert.equal(ui.find("forget-confirm"), undefined);
  ui.reply(snapshot({operation: operation("forget", {phase: "confirm"})}), {confirmation_id: "confirmation"});
  await ui.click("forget_prepare");
  assert.deepEqual(lastBody(ui), {op: "forget_prepare", lease, device_id: "device"});
  assert.match(ui.root.textContent, /старые привязки этого устройства будут удалены/);
  assert.match(ui.root.textContent, /Общие кнопки ТВ-режима останутся без изменений/);
  assert.equal(ui.find("device:device").disabled, true);
  ui.reply(snapshot({operation: operation("forget", {phase: "accepted"})}), {}, 202);
  await ui.click("forget-confirm");
  assert.deepEqual(lastBody(ui), {op: "forget_confirm", lease, operation_id: "operation", confirmation_id: "confirmation"});
  assert.equal(ui.find("forget-confirm"), undefined);
  assert.equal(ui.controls.state.devices[0].paired, true);
});
test("BluetoothControls forget confirmation repeats only in owner poll and can be cancelled", async () => {
  const ui = await panel().start(); const state = snapshot({operation: operation("forget", {phase: "confirm"})});
  ui.reply(state, {confirmation_id: "confirmation"}); await ui.click("forget_prepare");
  await ui.poll(state, {confirmation_id: "confirmation"});
  assert.ok(ui.find("forget-confirm")); await ui.click("forget-cancel");
  assert.deepEqual(lastBody(ui), {op: "cancel", lease, operation_id: "operation"});
  await ui.poll(state, {confirmation_id: "confirmation"});
  assert.equal(ui.find("forget-confirm"), undefined, "cancelled operation cannot resurrect private confirmation");
});
test("BluetoothControls never converts 202 connect acceptance into observed connection", async () => {
  const state = snapshot(); state.devices[0].connected = false;
  const ui = await panel(state).start();
  ui.reply({...state, operation: operation("connect", {phase: "accepted"})}, {}, 202); await ui.click("connect");
  assert.equal(ui.controls.state.devices[0].connected, false);
  assert.match(ui.root.textContent, /Не подключено/);
  await ui.poll(snapshot()); assert.match(ui.root.textContent, /Подключено/);
});

// Every BlueZ KeyboardDisplay challenge form, ownership and secret erasure.
for (const [kind, value, answer] of [
  ["pin", "A!23", {pin: "A!23"}], ["passkey", "000123", {passkey: "000123"}],
]) test(`BluetoothControls ${kind} validates and sends an operation-bound secret, then erases detached input`, async () => {
  const ui = await pairing(kind); const input = ui.root.querySelector("input");
  assert.equal(input.type, "password"); assert.equal(input.autocomplete, "off");
  input.value = value; input.focus(); input.setSelectionRange(1, 2);
  ui.controls.render();
  assert.equal(input.value, "");
  const current = ui.root.querySelector("input"); assert.equal(current.value, value);
  assert.equal(ui.document.activeElement, current); assert.equal(current.selectionStart, 1);
  await ui.click("answer-submit");
  assert.deepEqual(lastBody(ui), {op: "answer", lease, operation_id: "operation", challenge_id: "challenge", answer});
  assert.equal(current.value, ""); assert.equal(ui.root.querySelector("input"), null);
});
for (const [kind, value] of [["pin", "bad pin"], ["pin", "я"], ["pin", "x".repeat(17)], ["passkey", "12345"], ["passkey", "１２３４５６"]])
  test(`BluetoothControls rejects invalid ${kind} ${JSON.stringify(value)} locally`, async () => {
    const ui = await pairing(kind); const count = ui.calls.length;
    const input = ui.root.querySelector("input"); input.value = value; await ui.click("answer-submit");
    assert.equal(ui.calls.length, count); assert.equal(input.value, "");
    assert.equal(ui.root.querySelector("input").value, "");
  });
for (const confirm of [true, false]) test(`BluetoothControls confirmation sends explicit ${confirm}`, async () => {
  const ui = await pairing("confirmation", {value: "123456"});
  assert.match(ui.root.textContent, /123456/);
  const secret = ui.root.querySelector("[data-secret]");
  await ui.click(confirm ? "answer-yes" : "answer-no");
  assert.deepEqual(lastBody(ui), {op: "answer", lease, operation_id: "operation", challenge_id: "challenge", answer: {confirm}});
  assert.equal(secret.textContent, ""); assert.ok(!ui.root.textContent.includes("123456"));
});
for (const kind of ["display_pin", "display_passkey"]) test(`BluetoothControls ${kind} is display-only and retired secrets leave no hidden DOM`, async () => {
  const ui = await pairing(kind, {value: "123456", entered: 2});
  assert.match(ui.root.textContent, /123456/); assert.equal(ui.root.querySelector("input"), null);
  assert.equal(ui.find("answer-submit"), undefined); assert.equal(ui.find("answer-yes"), undefined);
  const secret = ui.root.querySelector("[data-secret]"); const old = ui.controls.challenge;
  ui.controls.retire(); assert.equal(secret.textContent, ""); assert.equal(old.value, "");
  assert.ok(!ui.root.textContent.includes("123456")); assert.equal(ui.controls.challenge, null);
});
test("BluetoothControls GET, non-pair, terminal, expired and unknown challenges never expose secrets", async () => {
  const challenge = {id: "challenge", kind: "display_pin", remaining_ms: 10000, value: "SECRET"};
  for (const op of [null, operation("learn"), operation("pair", {phase: "finished"}), operation("pair", {remaining_ms: 0})]) {
    const ui = panel(snapshot({operation: op}));
    ui.reply(ui.state, {lease, challenge}); ui.reply(ui.state, {lease, challenge});
    await ui.start(); assert.ok(!ui.root.textContent.includes("SECRET"));
  }
  const ui = await pairing("unknown", {value: "SECRET"}); assert.ok(!ui.root.textContent.includes("SECRET"));
  await ui.poll(snapshot({operation: operation("pair")}), {challenge: {...challenge, remaining_ms: 0}});
  assert.ok(!ui.root.textContent.includes("SECRET"));
});
test("BluetoothControls cancel fences challenge resurrection and stale detached controls", async () => {
  const ui = await pairing("pin"); const input = ui.root.querySelector("input"); input.value = "SECRET";
  const oldAnswer = ui.find("answer-submit");
  const state = snapshot({operation: operation("pair")}); const challenge = {id: "challenge", kind: "display_pin", remaining_ms: 5000, value: "SECRET"};
  ui.reply(state, {challenge}); await ui.click("cancel");
  assert.equal(input.value, ""); assert.equal(ui.controls.challenge, null);
  await ui.poll(state, {challenge}); assert.ok(!ui.root.textContent.includes("SECRET"));
  const count = ui.calls.length; oldAnswer.onclick(); await settle(); assert.equal(ui.calls.length, count);
});
test("BluetoothControls replacement operation cannot retain challenge draft or old answer ownership", async () => {
  const ui = await pairing("pin"); const input = ui.root.querySelector("input"); input.value = "SECRET";
  const oldAnswer = ui.find("answer-submit");
  await ui.poll(snapshot({operation: operation("pair", {id: "replacement"})}),
    {challenge: {id: "new-challenge", kind: "pin", remaining_ms: 5000}});
  assert.equal(input.value, ""); assert.equal(ui.root.querySelector("input").value, "");
  const count = ui.calls.length; oldAnswer.onclick(); await settle(); assert.equal(ui.calls.length, count);
  ui.root.querySelector("input").value = "1234"; await ui.click("answer-submit");
  assert.equal(lastBody(ui).operation_id, "replacement"); assert.equal(lastBody(ui).challenge_id, "new-challenge");
});

test("BluetoothControls preserves saved mappings without exposing or mutating them", async () => {
  const ui = await panel().start();
  for (const key of ["action", "learn", "test", "bind", "reset", "unmap:KEY_ENTER", "select_remote"])
    assert.equal(ui.find(key), undefined);
  assert.deepEqual(clone(ui.controls.state.remote.bindings), {KEY_ENTER: "ok"});
  await ui.poll();
  assert.deepEqual(clone(ui.controls.state.remote.bindings), {KEY_ENTER: "ok"});
  assert.ok(!ui.calls.some(call => ["select_remote", "learn", "bind", "unmap", "reset"].includes(call.body?.op)));
});

// Lease, sequencing, auth and lifecycle failure matrix.
for (const error of ["busy", "stale", "invalid_lease"]) test(`BluetoothControls ${error} requires explicit acquire retry, never auto-reacquires`, async () => {
  const ui = panel(); ui.reply(ui.state); ui.reply(ui.state, {error}, 409); await ui.start();
  assert.equal(ui.controls.lease, null); assert.equal(ui.find("discover").disabled, true);
  await ui.poll(); assert.equal(ui.calls.at(-1).method, "GET");
  assert.equal(ui.calls.filter(call => call.body?.op === "acquire").length, 1);
  await ui.click("retry"); assert.equal(ui.controls.lease, lease);
  assert.equal(ui.calls.filter(call => call.body?.op === "acquire").length, 2);
});
test("BluetoothControls stale owner poll stops privileged polling and erases challenge", async () => {
  const ui = await pairing("display_pin", {value: "SECRET"});
  await ui.poll(snapshot(), {error: "stale"}, 409);
  assert.equal(ui.controls.lease, null); assert.equal(ui.controls.challenge, null);
  await ui.poll(); assert.equal(ui.calls.at(-1).method, "GET");
});
test("BluetoothControls serializes polling and mutations with no duplicate click queue", async () => {
  const ui = await panel().start(); const held = deferred(); ui.replies.push(() => held.promise);
  const button = ui.find("disconnect"); button.onclick(); button.onclick(); await settle();
  await ui.clock.tick(5000);
  assert.equal(ui.calls.length, 3);
  assert.equal(ui.calls.filter(call => call.body?.op === "disconnect").length, 1);
  held.resolve(response(snapshot())); await settle(); await ui.poll();
  assert.equal(lastBody(ui).op, "poll");
});
for (const cleanup of ["deactivate", "retire"]) test(`BluetoothControls ${cleanup} fences late acquire credential/body promises`, async () => {
  const ui = panel(); const body = deferred(); ui.reply(ui.state);
  ui.replies.push(() => ({ok: true, status: 200, json: () => body.promise}));
  const activation = ui.controls.activate(); await settle(); ui.controls[cleanup]();
  body.resolve({state: snapshot(), lease}); await activation; await settle();
  assert.equal(ui.controls.lease, null); assert.equal(ui.controls.state, null); assert.equal(ui.controls.actions().length, 0);
  await ui.clock.tick(20000); assert.equal(ui.calls.length, 2);
});
for (const cleanup of ["deactivate", "retire"]) test(`BluetoothControls ${cleanup} fences late owner secrets; release policy is exact`, async () => {
  const ui = await panel().start(); const held = deferred(); ui.replies.push(() => held.promise);
  await ui.clock.tick(5000); ui.controls[cleanup](); ui.controls[cleanup]();
  held.resolve(response(snapshot({operation: operation("pair")}), {challenge: {id: "challenge", kind: "display_pin", remaining_ms: 5000, value: "SECRET"}}));
  await settle(); assert.equal(ui.controls.state, null); assert.equal(ui.controls.challenge, null);
  assert.ok(!ui.root.textContent.includes("SECRET"));
  assert.equal(ui.calls.filter(call => call.body?.op === "release").length, cleanup === "deactivate" ? 1 : 0);
});
test("BluetoothControls new activation waits old transport then ignores old state", async () => {
  const ui = await panel().start(); const held = deferred(); ui.replies.push(() => held.promise);
  await ui.clock.tick(5000); ui.controls.retire(); const activation = ui.controls.activate(); await settle();
  assert.equal(ui.calls.length, 3);
  held.resolve(response(snapshot({revision: 999}), {lease: "b".repeat(32)})); await activation;
  assert.equal(ui.controls.state.revision, 7); assert.equal(ui.controls.lease, lease);
  assert.deepEqual(ui.calls.slice(-2).map(call => call.body?.op || call.method), ["GET", "acquire"]);
});
for (const status of [401, 403]) test(`BluetoothControls HTTP ${status} retires and notifies parent once, without body`, async () => {
  const ui = await pairing("display_pin", {value: "SECRET"});
  ui.replies.push(() => ({ok: false, status, json() { throw new Error("must not read auth body"); }}));
  await ui.poll(); assert.equal(ui.auth, 1); assert.equal(ui.controls.active, false);
  assert.equal(ui.controls.lease, null); assert.ok(!ui.root.textContent.includes("SECRET"));
  const count = ui.calls.length; await ui.clock.tick(20000); assert.equal(ui.calls.length, count);
  assert.equal(ui.calls.filter(call => call.body?.op === "release").length, 0);
});
for (const failure of ["reject", "body", "timeout"]) test(`BluetoothControls ${failure} retires uncertain transport without mutation replay`, async () => {
  const ui = await panel().start(); const held = deferred();
  ui.replies.push(() => failure === "reject" ? Promise.reject(new Error("secret backend exception")) :
    {ok: true, status: 202, json: () => failure === "body" ? Promise.reject(new Error("bad json")) : held.promise});
  await ui.click("disconnect"); if (failure === "timeout") await ui.clock.tick(8000);
  assert.equal(ui.controls.active, false); assert.equal(ui.controls.lease, null);
  assert.match(ui.root.textContent, /Результат неизвестен/); assert.ok(!ui.root.textContent.includes("exception"));
  held.resolve({state: snapshot(), lease}); await settle(); await ui.clock.tick(20000);
  assert.equal(ui.calls.filter(call => call.body?.op === "disconnect").length, 1);
  assert.equal(ui.controls.state, null);
});
test("BluetoothControls no polling when document or mount hidden; listener removed on cleanup", async () => {
  const ui = await panel().start(); assert.equal(ui.document.listeners.size, 1);
  ui.document.visibility(true); await settle(); assert.equal(ui.document.listeners.size, 0);
  const count = ui.calls.length; await ui.clock.tick(20000); assert.equal(ui.calls.length, count);
  ui.document.visibility(false); await ui.controls.activate();
  ui.root.hidden = true; await ui.clock.tick(5000);
  assert.equal(ui.controls.active, false); assert.equal(ui.controls.actions().length, 0);
});
test("BluetoothControls hidden activation and hidden late responses cannot expose secrets", async () => {
  const ui = panel(); ui.document.hidden = true; await ui.controls.activate(); assert.equal(ui.calls.length, 0);
  ui.document.hidden = false; await ui.start(); const held = deferred(); ui.replies.push(() => held.promise);
  await ui.clock.tick(5000); ui.root.hidden = true;
  held.resolve(response(snapshot({operation: operation("pair")}), {challenge: {id: "c", kind: "display_pin", remaining_ms: 5000, value: "SECRET"}}));
  await settle(); assert.equal(ui.controls.active, false); assert.ok(!ui.root.textContent.includes("SECRET"));
});

// Text safety, availability and composable TV/phone navigation.
test("BluetoothControls renders hostile names as text and translates unknown errors generically", async () => {
  const state = snapshot(); state.devices[0].name = '<img src=x onerror="evil()">';
  const ui = await panel(state).start(); assert.match(ui.root.textContent, /<img src=x/);
  await ui.poll(state, {error: "raw password / private path"}, 500);
  assert.ok(!ui.root.textContent.includes("raw password")); assert.match(ui.root.textContent, /Не удалось/);
});
for (const [changes, message] of [
  [{available: false, reason: "helper_unavailable"}, /администратору/],
  [{adapter: null}, /недоступен/], [{adapter: {id: "adapter", powered: false, discovering: false}}, /выключен/],
]) test(`BluetoothControls truthful availability ${JSON.stringify(changes)}`, async () => {
  const ui = await panel(snapshot(changes)).start(); assert.match(ui.root.textContent, message);
  assert.equal(ui.find("learn"), undefined);
  if (changes.adapter !== undefined || changes.available === false) assert.equal(ui.find("discover").disabled, true);
});
test("BluetoothControls never offers physical remote selection", async () => {
  const state = snapshot(); state.devices[0].selected = false;
  const ui = await panel(state).start(); await ui.click("device:device");
  assert.equal(ui.find("select_remote"), undefined);
  assert.equal(ui.find("learn"), undefined);
  assert.equal(ui.calls.filter(call => call.body?.op === "select_remote").length, 0);
});
test("BluetoothControls actions are visible enabled display order, update callback and semantic focus", async () => {
  const ui = await panel().start(); const external = ui.document.createElement("button"); ui.document.body.append(external); external.focus();
  ui.controls.render(); assert.equal(ui.document.activeElement, external);
  const button = ui.find("disconnect"); button.focus();
  const oldChanges = ui.changes; ui.controls.render();
  assert.equal(ui.document.activeElement.dataset.btKey, "disconnect"); assert.ok(ui.changes > oldChanges);
  assert.deepEqual(Array.from(ui.controls.actions(), item => item.dataset.btKey),
    ui.root.querySelectorAll("button, input, select").filter(item => !item.disabled).map(item => item.dataset.btKey));
  assert.equal(ui.root.onkeydown, undefined, "Back and keyboard are parent-owned");
  await ui.click("disconnect"); assert.equal(ui.document.activeElement.dataset.btKey, "disconnect");
  ui.controls.retire(); assert.equal(ui.controls.actions().length, 0);
});
test("BluetoothControls removed focused device falls back locally but never steals newly external focus", async () => {
  const ui = await panel().start(); ui.find("device:device").focus();
  await ui.poll(snapshot({devices: []})); assert.ok(ui.root.contains(ui.document.activeElement));
  const external = ui.document.createElement("input"); ui.document.body.append(external); external.focus();
  await ui.poll(); assert.equal(ui.document.activeElement, external);
});
test("BluetoothControls malformed response fails closed, no lease, no error interpolation", async () => {
  const ui = panel(); ui.replies.push(() => ({ok: true, status: 200, json: async () => ({devices: [], error: "SECRET"})}));
  await ui.start(); assert.equal(ui.controls.active, false); assert.equal(ui.controls.lease, null);
  assert.ok(!ui.root.textContent.includes("SECRET")); assert.equal(ui.calls.length, 1);
});
test("BluetoothControls CSS rules stay scoped to the component", () => {
  for (const rule of css.matchAll(/([^{}]+)\{/g)) {
    if (rule[1].trim().startsWith("@")) continue;
    for (const selector of rule[1].trim().split(",")) assert.ok(selector.trim().startsWith(".bluetooth-controls"), selector);
  }
});

test("BluetoothControls an unanswered timed-out transport cannot accumulate replacement requests", async () => {
  const ui = await panel().start(); const held = deferred(); ui.replies.push(() => held.promise);
  await ui.click("disconnect"); await ui.clock.tick(8000);
  const count = ui.calls.length;
  for (let n = 0; n < 3; n++) { await ui.controls.activate(); await settle(); }
  assert.equal(ui.calls.length, count);
  assert.equal(ui.controls.active, false);
  held.resolve(response(snapshot({revision: 999}))); await settle();
  await ui.controls.activate();
  assert.equal(ui.controls.state.revision, 7);
  assert.equal(ui.controls.lease, lease);
});
test("BluetoothControls retirement cancels a queued release when transport authority is lost", async () => {
  const ui = await panel().start(); const held = deferred(); ui.replies.push(() => held.promise);
  await ui.clock.tick(5000); ui.controls.deactivate(); ui.controls.retire();
  held.resolve(response(snapshot())); await settle();
  assert.equal(ui.calls.filter(call => call.body?.op === "release").length, 0);
  assert.equal(ui.controls.state, null);
});
test("BluetoothControls serial tail does not retain a private response envelope", async () => {
  const ui = await pairing("display_pin", {value: "SECRET"});
  assert.equal(await ui.controls.serial, undefined);
  ui.controls.retire(); assert.equal(await ui.controls.serial, undefined);
});
test("BluetoothControls read-only busy explanation survives inventory refresh", async () => {
  const ui = panel(); ui.reply(ui.state); ui.reply(ui.state, {error: "busy"}, 409); await ui.start();
  await ui.poll(); assert.match(ui.root.textContent, /занят другим управлением/);
  assert.equal(ui.calls.at(-1).method, "GET");
});
test("BluetoothControls answered challenge cannot be resurrected by a stale owner poll", async () => {
  const ui = await pairing("confirmation", {value: "123456"});
  const state = snapshot({operation: operation("pair")});
  const challenge = {id: "challenge", kind: "confirmation", remaining_ms: 5000, value: "123456"};
  ui.reply(state, {challenge}, 202); await ui.click("answer-yes");
  assert.equal(ui.find("answer-yes"), undefined);
  await ui.poll(state, {challenge}); assert.ok(!ui.root.textContent.includes("123456"));
});
test("BluetoothControls accepted forget cannot offer the consumed confirmation a second time", async () => {
  const ui = await panel().start(); const state = snapshot({operation: operation("forget", {phase: "confirm"})});
  ui.reply(state, {confirmation_id: "confirmation"}); await ui.click("forget_prepare");
  ui.reply(state, {confirmation_id: "confirmation"}, 202); await ui.click("forget-confirm");
  assert.equal(ui.find("forget-confirm"), undefined);
  await ui.poll(state, {confirmation_id: "confirmation"}); assert.equal(ui.find("forget-confirm"), undefined);
});
for (const change of [state => { state.devices[0].connected = "true"; }, state => { state.adapter.powered = "true"; },
  state => { state.operation = operation("pair", {remaining_ms: -1}); }, state => { state.remote.bindings = []; }])
  test("BluetoothControls malformed typed state cannot become observed success", async () => {
    const state = snapshot(); change(state); const ui = await panel(state).start();
    assert.equal(ui.controls.active, false); assert.equal(ui.controls.state, null);
    assert.equal(ui.calls.length, 1);
  });

test("BluetoothControls pairing target replacement within the same operation fences old secrets", async () => {
  const ui = await pairing("pin"); const old = ui.root.querySelector("input"); old.value = "SECRET";
  const state = snapshot({operation: operation("pair", {device_id: "replacement"})});
  state.devices.push({...state.devices[0], id: "replacement"});
  await ui.poll(state, {challenge: {id: "challenge", kind: "display_pin", value: "SECRET", remaining_ms: 5000}});
  assert.equal(ui.controls.challenge, null); assert.equal(old.value, ""); assert.ok(!ui.root.textContent.includes("SECRET"));
});
test("BluetoothControls owns descendants only, leaving mount attributes and outside listeners alone", async () => {
  const ui = panel(); ui.root.className = "parent-mount"; ui.root.dataset.parent = "kept";
  const external = () => {}; ui.document.addEventListener("visibilitychange", external);
  await ui.start(); ui.controls.retire();
  assert.equal(ui.root.className, "parent-mount"); assert.equal(ui.root.dataset.parent, "kept");
  assert.equal(ui.root.children[0].className, "bluetooth-controls");
  assert.ok(ui.document.listeners.has(external)); assert.equal(ui.document.listeners.size, 1);
});


// Review P1: authority is checked at actual invocation, not one microtask earlier.
for (const cleanup of ["retire", "deactivate", "reactivate"]) {
  for (const op of ["discover", "pair", "connect", "disconnect", "select_remote", "answer", "cancel",
    "forget_prepare", "forget_confirm", "learn", "test", "bind", "unmap", "reset"]) {
    test(`BluetoothControls ${op} cannot dispatch in a retired microtask (${cleanup})`, async () => {
      for (let turns = 0; turns <= 3; turns++) {
        const ui = await panel().start(); const generation = ui.controls.generation;
        const state = snapshot({operation: operation(op === "answer" ? "pair" : op === "forget_confirm" ? "forget" : "learn")});
        ui.controls.state = state;
        ui.controls.challenge = {id: "challenge", operation_id: "operation", kind: "pin", remaining_ms: 10000};
        ui.controls.confirmation = {id: "confirmation", operation_id: "operation"};
        ui.controls.observation = {id: "observation", operation_id: "operation", key: "KEY_ENTER", action: "ok", complete: true, tested: false};
        const fields = {answer: {pin: "1234"}, operation_id: "operation", challenge_id: "challenge"};
        const byOp = {answer: fields, cancel: {operation_id: "operation"},
          forget_confirm: {operation_id: "operation", confirmation_id: "confirmation"},
          test: {operation_id: "operation", observation_id: "observation"},
          bind: {operation_id: "operation", observation_id: "observation"},
          unmap: {key: "KEY_ENTER", revision: 7}, reset: {revision: 7}, learn: {action: "ok"}};
        void ui.controls.mutate(op, byOp[op] || (op === "discover" ? {} : {device_id: "device"}));
        for (let n = 0; n < turns; n++) await Promise.resolve();
        const dispatched = ui.calls.filter(call => call.body?.op === op).length;
        if (cleanup === "reactivate") { ui.controls.deactivate(); void ui.controls.activate(); }
        else ui.controls[cleanup]();
        await settle();
        assert.equal(ui.calls.filter(call => call.body?.op === op).length, dispatched, `${op}, turn ${turns}`);
        for (const call of ui.invocations.filter(call => call.op === op)) {
          assert.equal(call.active, true); assert.equal(call.generation, generation);
        }
      }
    });
  }
  for (const start of ["activate", "retry", "poll", "readonly"]) {
    test(`BluetoothControls ${start} dispatch is microtask-fenced (${cleanup})`, async () => {
      for (let turns = 0; turns <= 18; turns++) {
        const ui = panel();
        if (start !== "activate") {
          if (["retry", "readonly"].includes(start)) { ui.reply(ui.state); ui.reply(ui.state, {error: "busy"}, 409); }
          await ui.start();
        }
        if (start === "activate") void ui.controls.activate();
        else if (start === "retry") void ui.controls.retry();
        else {
          // Invoke the scheduled deadline without draining its promise turns.
          const [id, job] = [...ui.clock.jobs].find(([, job]) => job.at === 5000);
          ui.clock.time = 5000; ui.clock.jobs.delete(id); job.fn();
        }
        for (let n = 0; n < turns; n++) await Promise.resolve();
        const before = ui.invocations.length;
        if (cleanup === "reactivate") { ui.controls.deactivate(); void ui.controls.activate(); }
        else ui.controls[cleanup]();
        await settle();
        const later = ui.invocations.slice(before).filter(call => call.op !== "release");
        assert.deepEqual(later.map(call => call.op || call.method), cleanup === "reactivate" ? ["GET", "acquire"] : [],
          `${start}, turn ${turns}`);
        assert.ok(later.every(call => call.active));
      }
    });
  }
}
test("BluetoothControls release honors transport epoch at actual invocation, including the intervening turn", async () => {
  for (let turns = 0; turns <= 3; turns++) {
    const ui = await panel().start(); const epoch = ui.controls.transportEpoch;
    ui.controls.deactivate();
    for (let n = 0; n < turns; n++) await Promise.resolve();
    const count = ui.calls.filter(call => call.body?.op === "release").length;
    ui.controls.retire(); await settle();
    assert.equal(ui.calls.filter(call => call.body?.op === "release").length, count, `turn ${turns}`);
    assert.ok(ui.invocations.filter(call => call.op === "release").every(call => call.epoch === epoch));
  }
});

// Review P1: fake owner leases expire after15s; ONLY poll renews them.
function leaseServer(ui, delays = {}) {
  const log = []; let owned = false, expiry, expiresAt = null, active = 0, maxActive = 0, expirations = 0;
  const renew = () => {
    ui.clock.clearTimeout(expiry); expiresAt = ui.clock.now() + 15000; owned = true;
    expiry = ui.clock.setTimeout(() => { owned = false; expirations++; }, 15000);
  };
  ui.server = (method, body) => {
    const at = ui.clock.now(); active++; maxActive = Math.max(maxActive, active);
    let status = 200, extras = {};
    if (body?.op === "acquire") { renew(); extras = {lease}; }
    else if (method === "POST") {
      if (!owned || body.lease !== lease) { status = 409; extras = {error: "stale"}; }
      else if (body.op === "poll") renew();
      else if (body.op === "unmap") { delete ui.state.remote.bindings[body.key]; ui.state.revision++; }
    }
    log.push({op: body?.op || method, at, expiresAt, status});
    const envelope = clone({state: ui.state, ...extras});
    const result = {ok: status < 300, status, json: async () => { active--; return envelope; }};
    return delays[body?.op] ? new Promise(resolve => ui.clock.setTimeout(() => resolve(result), delays[body.op])) : result;
  };
  return {log, get owned() { return owned; }, get expiresAt() { return expiresAt; },
    get maxActive() { return maxActive; }, get expirations() { return expirations; }};
}
test("BluetoothControls mutations at4/8/12s never debounce poll deadlines or renew the lease themselves", async () => {
  const state = snapshot(); state.remote.bindings = {KEY_ENTER: "ok", KEY_UP: "up", KEY_DOWN: "down"};
  const ui = panel(state); const server = leaseServer(ui); await ui.start();
  for (const key of ["KEY_ENTER", "KEY_UP", "KEY_DOWN"]) {
    await ui.clock.tick(4000); void ui.controls.mutate("unmap", {key, revision:ui.state.revision}); await settle();
  }
  await ui.clock.tick(4000);
  assert.deepEqual(server.log.filter(call => call.op === "unmap").map(call => call.at), [4000, 8000, 12000]);
  assert.deepEqual(server.log.filter(call => call.op === "poll").map(call => call.at), [5000, 10000, 15000]);
  assert.deepEqual(server.log.filter(call => call.op === "unmap").map(call => call.expiresAt), [15000, 20000, 25000]);
  assert.equal(server.owned, true); assert.equal(server.expirations, 0); assert.equal(server.maxActive, 1);
  assert.equal(ui.controls.lease, lease);
});
test("BluetoothControls seven-second mutation overlapping heartbeat is followed immediately by owner poll", async () => {
  const ui = panel(); const server = leaseServer(ui, {unmap: 7000}); await ui.start();
  await ui.clock.tick(4000); void ui.controls.mutate("unmap", {key:"KEY_ENTER", revision:7}); await settle();
  await ui.clock.tick(6999); assert.equal(server.log.filter(call => call.op === "poll").length, 0);
  assert.equal(server.expiresAt, 15000); assert.equal(ui.controls.pending, true);
  await ui.clock.tick(1);
  assert.deepEqual(server.log.filter(call => call.op === "poll").map(call => call.at), [11000]);
  assert.equal(server.expiresAt, 26000); assert.equal(server.maxActive, 1);
  await ui.clock.tick(5000); assert.equal(server.owned, true); assert.equal(server.expirations, 0);
  assert.equal(ui.controls.lease, lease);
});
for (const queued of [false, true]) test(`BluetoothControls overdue heartbeat has priority before a ${queued ? "queued" : "new"} mutation`, async () => {
  const ui = panel(); const server = leaseServer(ui); await ui.start();
  const lane = deferred();
  if (queued) { ui.controls.serial = lane.promise; void ui.controls.mutate("unmap", {key: "KEY_ENTER", revision: 7}); }
  // Simulate delayed browser timers, or a request waiting for the serial slot.
  ui.clock.time = 6000;
  if (queued) lane.resolve(); else void ui.controls.mutate("unmap", {key: "KEY_ENTER", revision: 7});
  await settle();
  assert.deepEqual(server.log.slice(-2).map(call => [call.op, call.at]), [["poll", 6000], ["unmap", 6000]]);
  assert.equal(server.maxActive, 1); assert.equal(server.expirations, 0);
  await ui.clock.tick(10000); assert.equal(server.owned, true);
});
for (const status of [200, 202, 409, 503]) test(`BluetoothControls mutation HTTP${status} retaining ownership cannot postpone heartbeat`, async () => {
  const ui = await panel().start(); await ui.clock.tick(4000);
  ui.reply(snapshot(), status >= 400 ? {error: "failed"} : {}, status); void ui.controls.mutate("reset", {revision:7}); await settle();
  await ui.clock.tick(1000);
  assert.equal(lastBody(ui).op, "poll"); assert.equal(ui.invocations.at(-1).at, 5000);
});
test("BluetoothControls priority poll revalidates queued revision rather than silently retrying mutation", async () => {
  const ui = await panel().start(); ui.clock.time = 6000;
  ui.reply(snapshot({revision: 8})); void ui.controls.mutate("reset", {revision:7}); await settle();
  assert.equal(lastBody(ui).op, "poll"); assert.equal(ui.calls.filter(call => call.body?.op === "reset").length, 0);
  assert.match(ui.root.textContent, /Назначения изменились/);
});
test("BluetoothControls priority poll cannot send an answer for a replacement challenge or operation", async () => {
  const ui = await pairing("pin"); ui.clock.time = 11000;
  const input = ui.root.querySelector("input"); input.value = "1234";
  ui.reply(snapshot({operation: operation("pair", {id: "replacement"})}),
    {challenge: {id: "replacement-challenge", kind: "pin", remaining_ms: 10000}});
  await ui.click("answer-submit");
  assert.equal(ui.calls.filter(call => call.body?.op === "answer").length, 0);
  assert.equal(input.value, ""); assert.equal(ui.controls.challenge.id, "replacement-challenge");
});
test("BluetoothControls priority poll stale lease suppresses queued mutation without reacquisition", async () => {
  const ui = await panel().start(); ui.clock.time = 6000;
  ui.reply(snapshot(), {error: "stale"}, 409); void ui.controls.mutate("reset", {revision:7}); await settle();
  assert.equal(ui.controls.lease, null); assert.equal(lastBody(ui).op, "poll");
  assert.equal(ui.calls.filter(call => call.body?.op === "reset").length, 0);
  assert.equal(ui.calls.filter(call => call.body?.op === "acquire").length, 1);
});
test("BluetoothControls unsettled transport still expires honestly, retires locally and never retries mutation", async () => {
  const ui = panel(); const server = leaseServer(ui, {poll: 20000}); await ui.start();
  await ui.clock.tick(20000);
  assert.equal(server.owned, false); assert.equal(server.expirations, 1);
  assert.equal(ui.controls.active, false); assert.equal(ui.controls.lease, null);
  assert.equal(server.log.filter(call => call.op === "poll").length, 1);
  assert.equal(server.log.filter(call => call.op === "acquire").length, 1);
});

// Review P1: the real stylesheet participates in this bounded fake focus model.
test("BluetoothControls fake focus rejects CSS-hidden, disconnected, disabled and non-focusable nodes", () => {
  const ui = panel(); const p = ui.document.createElement("p"); p.tabIndex = -1; p.className = "bt-feedback";
  ui.root.children[0].append(p); p.focus(); assert.notEqual(ui.document.activeElement, p);
  p.className += " bt-focus-anchor"; p.focus(); assert.equal(ui.document.activeElement, p);
  const outside = ui.document.createElement("button"); ui.document.body.append(outside); outside.focus();
  p.hidden = true; p.focus(); assert.equal(ui.document.activeElement, outside);
  p.hidden = false; p.style.display = "none"; p.focus(); assert.equal(ui.document.activeElement, outside);
  p.style.display = ""; p.parentElement.hidden = true; p.focus(); assert.equal(ui.document.activeElement, outside);
  const detached = ui.document.createElement("button"); detached.focus(); assert.equal(ui.document.activeElement, outside);
  const plain = ui.document.createElement("p"); ui.document.body.append(plain); plain.focus(); assert.equal(ui.document.activeElement, outside);
  outside.disabled = true; ui.document.activeElement = ui.document.body; outside.focus(); assert.equal(ui.document.activeElement, ui.document.body);
});
for (const key of ["disconnect", "answer:challenge"]) test(`BluetoothControls empty-feedback poll keeps rendered pending focus and restores ${key}`, async () => {
  const ui = key.startsWith("answer") ? await pairing("pin") : await panel().start();
  const element = ui.find(key); element.focus(); assert.equal(ui.controls.message, "");
  if (element.tagName === "INPUT") element.value = "1234";
  const held = deferred(); ui.replies.push(() => held.promise); await ui.clock.tick(5000);
  const anchor = ui.document.activeElement;
  assert.ok(ui.root.contains(anchor)); assert.equal(anchor.dataset.btKey, key);
  assert.equal(anchor.tagName, "P"); assert.equal(anchor.textContent, ""); assert.equal(anchor.rendered(), true);
  assert.ok(anchor.className.includes("bt-focus-anchor"));
  const state = key.startsWith("answer") ? snapshot({operation: operation("pair")}) : snapshot();
  held.resolve(response(state, key.startsWith("answer") ? {challenge: {id: "challenge", kind: "pin", remaining_ms: 10000}} : {}));
  await settle(); assert.equal(ui.document.activeElement, ui.find(key)); assert.equal(ui.find(key).rendered(), true);
  if (element.tagName === "INPUT") { assert.equal(element.value, ""); assert.equal(ui.find(key).value, "1234"); }
});
test("BluetoothControls successful blank response preserves pending focus after nonempty feedback", async () => {
  const ui = await panel().start(); ui.controls.message = "Запрос принят."; ui.controls.render();
  ui.find("disconnect").focus(); await ui.poll();
  assert.equal(ui.document.activeElement, ui.find("disconnect")); assert.equal(ui.controls.message, "");
});
test("BluetoothControls external focus acquired during a pending poll is not stolen by its reply", async () => {
  const ui = await panel().start(); ui.find("disconnect").focus();
  const held = deferred(); ui.replies.push(() => held.promise); await ui.clock.tick(5000);
  const external = ui.document.createElement("button"); ui.document.body.append(external); external.focus();
  held.resolve(response(snapshot())); await settle(); assert.equal(ui.document.activeElement, external);
});

for (const cleanup of ["retire", "deactivate", "reactivate"])
  test(`BluetoothControls priority-poll continuation cannot dispatch a retired mutation (${cleanup})`, async () => {
    for (let turns = 0; turns <= 18; turns++) {
      const ui = await panel().start(); ui.clock.time = 6000;
      const held = deferred(); ui.replies.push(() => held.promise); void ui.controls.mutate("reset", {revision: 7});
      await settle(); assert.equal(lastBody(ui).op, "poll"); held.resolve(response(snapshot()));
      for (let n = 0; n < turns; n++) await Promise.resolve();
      const count = ui.calls.filter(call => call.body?.op === "reset").length;
      if (cleanup === "reactivate") { ui.controls.deactivate(); void ui.controls.activate(); }
      else ui.controls[cleanup]();
      await settle(); assert.equal(ui.calls.filter(call => call.body?.op === "reset").length, count, `turn ${turns}`);
    }
  });
test("BluetoothControls actual dispatch rechecks authority after an integration render callback retires it", async () => {
  const ui = await panel().start(); let armed = false;
  ui.controls.options.onActionsChanged = () => {
    if (armed && ui.controls.pending && ui.controls.selected !== null) { armed = false; ui.controls.retire(); }
  };
  // Retire at the before-dispatch render, after the initial pending render.
  const render = ui.controls.render.bind(ui.controls); let renders = 0;
  ui.controls.render = () => { if (++renders === 2) armed = true; render(); };
  void ui.controls.mutate("select_remote", {device_id: "device"}); await settle();
  assert.equal(ui.controls.active, false);
  assert.equal(ui.calls.filter(call => call.body?.op === "select_remote").length, 0);
});
test("BluetoothControls focus remains on rendered anchor until the full Response body completes", async () => {
  const ui = await panel().start(); ui.find("disconnect").focus(); const body = deferred();
  ui.replies.push(() => ({ok: true, status: 200, json: () => body.promise})); await ui.clock.tick(5000);
  assert.equal(ui.controls.pending, true); assert.equal(ui.document.activeElement.rendered(), true);
  assert.equal(ui.document.activeElement.dataset.btKey, "disconnect"); assert.equal(ui.document.activeElement.tagName, "P");
  // A real browser Response.json() may require an event-loop turn, unlike a
  // resolved-Promise-only fixture wait. Restore only after the body is ready.
  await ui.clock.tick(1); body.resolve({state: snapshot()}); await settle();
  assert.equal(ui.controls.pending, false); assert.equal(ui.document.activeElement, ui.find("disconnect"));
});

for (const kind of ["pair", "connect", "disconnect", "forget"]) test(`finished ${kind} with pending proof stays exclusive and cancellable without reviving private controls`, async () => {
  const ui = kind === "pair" ? await pairing("pin") : await panel().start();
  const staleInput = ui.find("answer:challenge");
  if (staleInput) staleInput.value = "synthetic-secret";
  const pending = snapshot({operation: operation(kind, {phase:"finished",error:"uncertain",remaining_ms:9000})});
  await ui.poll(pending, {challenge:{id:"challenge",kind:"pin",remaining_ms:5000},
    observation:{id:"observation",key:"KEY_ENTER",action:"ok",complete:true,tested:false},confirmation_id:"confirmation"});
  assert.equal(ui.find("cancel").disabled, false);
  for (const key of ["discover", "disconnect", "forget_prepare", "learn", "reset"])
    if (ui.find(key)) assert.equal(ui.find(key).disabled, true, key);
  assert.equal(ui.find("answer:challenge"), undefined);
  assert.equal(ui.find("forget-confirm"), undefined);
  assert.equal(ui.controls.challenge, null);
  assert.equal(ui.controls.observation, null);
  assert.equal(ui.controls.confirmation, null);
  assert.ok(ui.root.textContent.includes("ожидаем подтверждение состояния"));
  if (staleInput) assert.equal(staleInput.value, "");
  ui.reply(snapshot({operation:operation(kind,{phase:"finished",error:"uncertain",remaining_ms:0})}));
  await ui.click("cancel");
  assert.deepEqual(lastBody(ui), {op:"cancel",lease,operation_id:"operation"});
  assert.equal(ui.find("cancel"), undefined);
  assert.equal(ui.find("discover").disabled, false);
  assert.equal(ui.controls.challenge, null);
});

test("adapter names are text, selection is explicit and the identifier is revalidated", async () => {
  const adapters = [
    {id:"adapter", name:"<USB>", label:"…33:44:55:60", powered:true, discovering:false, selectable:true},
    {id:"usb", name:"<USB>", label:"…33:44:55:61", powered:false, discovering:false, selectable:true},
  ];
  const state = snapshot({adapters, adapter_preference:false});
  const ui = await panel(state).start();
  assert.match(ui.root.textContent, /названия|Названия/);
  assert.match(ui.find("adapter:usb").textContent, /<USB>.*…33:44:55:61/);
  await ui.click("adapter:usb");
  assert.deepEqual(lastBody(ui), {op:"select_adapter", lease, adapter_id:"usb", revision:7});
});

test("external discovery disables adapter changes", async () => {
  const adapters = [
    {id:"adapter", name:"Built-in", label:"…33:44:55:60", powered:true, discovering:true, selectable:true},
    {id:"usb", name:"USB", label:"…33:44:55:61", powered:false, discovering:false, selectable:true},
  ];
  const ui = await panel(snapshot({adapters, adapter_preference:true})).start();
  assert.equal(ui.find("adapter:usb").disabled, true);
  assert.equal(ui.find("adapter:auto").disabled, true);
  assert.match(ui.root.textContent, /Поиск Bluetooth уже идёт/);
  const offState = snapshot({adapters, adapter_preference:true,
    adapter:{id:"usb", powered:false, discovering:false}});
  const off = await panel(offState).start();
  assert.equal(off.find("adapter:power").disabled, true);
});

for (const [label, fields, expected] of [
  ["both", {name:"Actual", bluez_name:"Actual", alias:"Nickname"}, "Actual (псевдоним: Nickname)"],
  ["same", {name:"Same", bluez_name:"Same", alias:"Same"}, "Same"],
  ["only alias", {name:"Alias", bluez_name:"", alias:"Alias"}, "Alias"],
  ["only name", {name:"Real", bluez_name:"Real", alias:""}, "Real"],
  ["neither", {name:"", bluez_name:"", alias:""}, "Без имени"],
  ["old server", {name:"Legacy"}, "Legacy"],
]) test(`device names ${label} remain compatible and are displayed as text`, async () => {
  const state = snapshot(); Object.assign(state.devices[0], fields);
  const ui = await panel(state).start();
  assert.equal(ui.find("device:device").textContent, expected);
});

test("late real name appears during discovery alongside an address-like alias", async () => {
  const initial = snapshot({operation:operation("discover", {device_id:null})});
  Object.assign(initial.devices[0], {name:"22:33:44:55:66:77", bluez_name:"", alias:"22:33:44:55:66:77"});
  const ui = await panel(initial).start();
  assert.equal(ui.find("device:device").textContent, "22:33:44:55:66:77");
  const next = structuredClone(initial);
  Object.assign(next.devices[0], {name:"<Real>", bluez_name:"<Real>"});
  await ui.poll(next);
  assert.equal(ui.find("device:device").textContent, "<Real> (псевдоним: 22:33:44:55:66:77)");
  assert.equal(ui.find("device:device").disabled, true);
});

test("malformed separate name fields fail closed", async () => {
  for (const fields of [{bluez_name:"only"}, {bluez_name:"x", alias:42},
    {bluez_name:"x", alias:"я".repeat(81)}]) {
    const state = snapshot(); Object.assign(state.devices[0], fields);
    const ui = await panel(state).start();
    assert.equal(ui.controls.state, null);
  }
});

test("off adapter needs explicit power; missing preference never selects fallback", async () => {
  const adapters = [{id:"usb", name:"", label:"…33:44:55:61", powered:false, discovering:false, selectable:true}];
  const state = snapshot({adapters, adapter_preference:true, adapter:{id:"usb", powered:false, discovering:false}});
  const ui = await panel(state).start();
  await ui.click("adapter:power");
  assert.deepEqual(lastBody(ui), {op:"power_on", lease, adapter_id:"usb"});
  const missing = await panel(snapshot({adapters:[], adapter_preference:true, adapter:null, available:false})).start();
  assert.match(missing.root.textContent, /Выбранный адаптер недоступен/);
  assert.equal(missing.find("adapter:power"), undefined);
});

test("selected Bluetooth device offers phone shortcut handoff without changing device state", async () => {
  const ui = panel(); let opened = 0;
  ui.controls.options.openShortcuts = () => opened++;
  await ui.start();
  assert.match(ui.root.textContent, /всех устройств ввода/);
  const before = ui.calls.length;
  await ui.click("shortcuts");
  assert.equal(opened, 1); assert.equal(ui.calls.length, before);
  await ui.poll(snapshot({operation: operation("pair")}));
  assert.equal(ui.find("shortcuts").disabled, true);
  const tv = await panel().start();
  assert.equal(tv.find("shortcuts"), undefined);
});
