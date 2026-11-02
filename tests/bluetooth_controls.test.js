"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("src/ad_linux_tv/static/bluetooth_controls.js", "utf8");
const lease = "a".repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
const settle = async () => { for (let n = 0; n < 60; n++) await Promise.resolve(); };

// Small DOM with real detach/focus and text-only semantics, not a markup parser.
class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = document; this.children = [];
    this.parentElement = null; this.dataset = {}; this.attributes = {}; this.value = "";
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
    if (selector === "[hidden]") return this.hidden;
    if (selector === "[data-secret]") return this.dataset.secret !== undefined;
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
  focus() { if (!this.disabled) this.ownerDocument.activeElement = this; }
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
  constructor() { this.now = 0; this.id = 0; this.jobs = new Map(); }
  setTimeout(fn, delay) { const id = ++this.id; this.jobs.set(id, {fn, at: this.now + delay}); return id; }
  clearTimeout(id) { this.jobs.delete(id); }
  async tick(delay) {
    const until = this.now + delay;
    for (;;) {
      const next = [...this.jobs].filter(([, job]) => job.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      this.now = next[1].at; this.jobs.delete(next[0]); next[1].fn(); await settle();
    }
    this.now = until; await settle();
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
  const clock = new Clock(); const calls = []; const replies = [];
  const context = vm.createContext({console});
  vm.runInContext(source + "\nglobalThis.Controls = BluetoothControls;", context);
  const ui = {state, root, document, clock, calls, replies, auth: 0, changes: 0};
  ui.controls = new context.Controls(root, async (method, path, body) => {
    calls.push({method, path, ...(body ? {body: clone(body)} : {})});
    if (replies.length) return replies.shift()(method, body);
    return response(ui.state, body?.op === "acquire" ? {lease} : {});
  }, {clock, onAuthLost: () => ui.auth++, onActionsChanged: () => ui.changes++});
  ui.find = key => root.querySelectorAll("button, input, select").find(element => element.dataset.btKey === key);
  ui.click = async key => { const button = ui.find(key); assert.ok(button, `missing ${key}`); assert.equal(button.disabled, false, `disabled ${key}`); button.onclick(); await settle(); };
  ui.reply = (nextState, extras = {}, status = 200) => replies.push(() => response(nextState, extras, status));
  ui.start = async () => { await ui.controls.activate(); await settle(); return ui; };
  ui.poll = async (nextState, extras = {}, status = 200) => { if (nextState) ui.reply(nextState, extras, status); await clock.tick(5000); };
  return ui;
}
async function learning(extras = {}) {
  const ui = await panel().start();
  const state = snapshot({operation: operation("learn")});
  ui.reply(state, {observation: {id: "observation", key: "KEY_PLAYPAUSE", action: "ok", complete: true, tested: false, ...extras}});
  await ui.click("learn"); return ui;
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
  ["select_remote", "select_remote", {selected: false}],
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
  assert.equal(ui.find("learn").disabled, true);
  await ui.click("cancel");
  assert.deepEqual(lastBody(ui), {op: "cancel", lease, operation_id: "operation"});
});
test("BluetoothControls forget requires owner confirmation and binds operation, not current selection", async () => {
  const ui = await panel().start(); assert.equal(ui.find("forget-confirm"), undefined);
  ui.reply(snapshot({operation: operation("forget", {phase: "confirm"})}), {confirmation_id: "confirmation"});
  await ui.click("forget_prepare");
  assert.deepEqual(lastBody(ui), {op: "forget_prepare", lease, device_id: "device"});
  assert.match(ui.root.textContent, /Сопряжение и его назначения будут удалены/);
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

// Staged observations are server-owned; no printable-key textbox or inferred ACK success.
test("BluetoothControls learn selects a fixed action and uses server observation for once-only test and bind", async () => {
  const ui = await panel().start(); const selector = ui.find("action"); selector.value = "play_pause"; selector.onchange();
  const state = snapshot({operation: operation("learn")});
  const observation = {id: "observation", key: "KEY_PLAYPAUSE", action: "play_pause", complete: true, tested: false};
  ui.reply(state, {observation}); await ui.click("learn");
  assert.deepEqual(lastBody(ui), {op: "learn", lease, action: "play_pause"});
  assert.equal(ui.calls.filter(call => call.body?.op === "test").length, 0);
  ui.reply(state, {observation}, 202); await ui.click("test");
  assert.deepEqual(lastBody(ui), {op: "test", lease, operation_id: "operation", observation_id: "observation"});
  assert.equal(ui.find("test").disabled, true);
  await ui.poll(state, {observation}); assert.equal(ui.find("test").disabled, true);
  ui.reply(snapshot({revision: 8})); await ui.click("bind");
  assert.deepEqual(lastBody(ui), {op: "bind", lease, operation_id: "operation", observation_id: "observation"});
  assert.equal(ui.controls.state.revision, 8); assert.equal(ui.find("bind"), undefined);
});
test("BluetoothControls incomplete learning cannot test or save", async () => {
  const ui = await learning({complete: false}); assert.equal(ui.find("test").disabled, true);
  assert.equal(ui.find("bind").disabled, true); assert.match(ui.root.textContent, /Отпустите кнопку/);
});
test("BluetoothControls already-tested observation cannot test again", async () => {
  const ui = await learning({tested: true}); assert.equal(ui.find("test").disabled, true);
});
for (const changes of [{key: "KEY_A"}, {action: "shutdown"}, {key: "<script>"}, {complete: "true"}])
  test(`BluetoothControls rejects unsafe observation ${JSON.stringify(changes)}`, async () => {
    const ui = await learning(changes); assert.equal(ui.controls.observation, null); assert.equal(ui.find("test"), undefined);
    assert.equal(ui.root.querySelector("input"), null);
  });
test("BluetoothControls bind attempt does not replay when server keeps the old observation", async () => {
  const ui = await learning(); const state = snapshot({operation: operation("learn")});
  const observation = clone(ui.controls.observation); delete observation.operation_id;
  ui.reply(state, {observation}, 202); await ui.click("bind");
  assert.equal(ui.find("bind").disabled, true);
  await ui.poll(state, {observation}); assert.equal(ui.find("bind").disabled, true);
});
test("BluetoothControls reset and unmap carry current saved revision and no arbitrary key", async () => {
  const ui = await panel().start();
  ui.reply(snapshot({revision: 8})); await ui.click("unmap:KEY_ENTER");
  assert.deepEqual(lastBody(ui), {op: "unmap", lease, key: "KEY_ENTER", revision: 7});
  await ui.click("reset"); assert.deepEqual(lastBody(ui), {op: "reset", lease, revision: 8});
});
test("BluetoothControls revision mismatch displays current bindings without retry", async () => {
  const ui = await panel().start(); const state = snapshot({revision: 9}); state.remote.bindings = {KEY_BACK: "back"};
  ui.reply(state, {error: "revision_mismatch"}, 409); await ui.click("reset");
  assert.equal(ui.find("unmap:KEY_ENTER"), undefined); assert.ok(ui.find("unmap:KEY_BACK"));
  assert.match(ui.root.textContent, /Назначения изменились/);
  await ui.poll(); assert.equal(ui.calls.filter(call => call.body?.op === "reset").length, 1);
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
  [{remote: {device_id: null, connected: false, input_available: false, reason: "unsupported", bindings: {}}}, /не поддерживается/],
]) test(`BluetoothControls truthful availability ${JSON.stringify(changes)}`, async () => {
  const ui = await panel(snapshot(changes)).start(); assert.match(ui.root.textContent, message);
  assert.equal(ui.find("learn").disabled, true);
  if (changes.adapter !== undefined || changes.available === false) assert.equal(ui.find("discover").disabled, true);
});
test("BluetoothControls candidate selection initiates attachment validation, but learning needs verified input", async () => {
  const state = snapshot(); state.devices[0].selected = false; state.devices[0].input_available = false;
  state.remote.input_available = false;
  const ui = await panel(state).start(); await ui.click("device:device");
  assert.equal(ui.find("select_remote").disabled, false); assert.equal(ui.find("learn").disabled, true);
  ui.reply({...state, operation: operation("select_remote", {phase: "accepted"})}, {}, 202);
  await ui.click("select_remote");
  assert.deepEqual(lastBody(ui), {op: "select_remote", lease, device_id: "device"});
  assert.equal(ui.controls.state.devices[0].selected, false);
  assert.match(ui.root.textContent, /Запрос принят/);
  assert.equal(ui.find("learn").disabled, true);
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
  const css = fs.readFileSync("src/ad_linux_tv/static/bluetooth_controls.css", "utf8");
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

for (const change of [
  state => { state.devices = []; state.remote.device_id = null; },
  state => { state.remote.input_available = false; },
  state => { state.remote.connected = false; },
  state => { state.remote.device_id = "replacement"; },
  state => { state.devices[0].input_available = false; },
]) test("BluetoothControls learning retires on selected-device loss or attachment replacement", async () => {
  const ui = await learning(); const state = snapshot({operation: operation("learn")}); change(state);
  const observation = {id: "observation", key: "KEY_PLAYPAUSE", action: "ok", complete: true, tested: false};
  const oldTest = ui.find("test"); await ui.poll(state, {observation});
  assert.equal(ui.controls.observation, null); assert.equal(ui.find("test"), undefined);
  const count = ui.calls.length; oldTest.onclick(); await settle(); assert.equal(ui.calls.length, count);
  await ui.poll(snapshot({operation: operation("learn")}), {observation});
  assert.equal(ui.find("test"), undefined, "same retired operation cannot recover private ownership");
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

for (const error of ["unsupported", "helper_unavailable", "identity_unproven"])
  test(`BluetoothControls rejected candidate ${error} preserves observed saved selection and bindings`, async () => {
    const state = snapshot(); state.devices.push({id: "candidate", name: "Другой пульт", paired: true, connected: true,
      selected: false, input_available: false});
    const ui = await panel(state).start(); await ui.click("device:candidate");
    ui.reply(state, {error}, 503); await ui.click("select_remote");
    assert.deepEqual(lastBody(ui), {op: "select_remote", lease, device_id: "candidate"});
    assert.equal(ui.controls.state.devices[0].selected, true);
    assert.equal(ui.controls.state.devices[1].selected, false);
    assert.equal(ui.controls.state.remote.device_id, "device");
    assert.deepEqual(clone(ui.controls.state.remote.bindings), {KEY_ENTER: "ok"});
    assert.ok(ui.root.textContent.includes(ui.controls.text(error)));
  });
for (const changes of [{paired: false}, {connected: false}, {selected: true}])
  test(`BluetoothControls candidate selection is gated for ${JSON.stringify(changes)}`, async () => {
    const state = snapshot(); Object.assign(state.devices[0], {selected: false, input_available: false}, changes);
    const ui = await panel(state).start(); await ui.click("device:device");
    assert.equal(ui.find("select_remote").disabled, true);
  });
for (const error of ["busy", "stale"])
  test(`BluetoothControls lease ${error} disables even a paired connected eligible candidate`, async () => {
    const state = snapshot(); state.devices[0].selected = false; state.devices[0].input_available = false;
    const ui = panel(state); ui.reply(state); ui.reply(state, {error}, 409); await ui.start(); await ui.click("device:device");
    assert.equal(ui.find("select_remote").disabled, true);
  });
