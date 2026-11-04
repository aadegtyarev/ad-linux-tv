"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {host, settle} = require("./helpers/bluetooth_host_mock.js");

for (const kind of ["tv", "phone"]) test(`${kind}: collapsed Bluetooth acquires only on explicit opening and releases on exit/visibility`, async () => {
  const ui = host(kind); await settle();
  assert.equal(ui.details.open, false);
  assert.equal(ui.bluetoothCalls().length, 0);
  ui.run(kind === "tv" ? "openSettings()" : 'showPage("settings")'); await settle();
  assert.equal(ui.bluetoothCalls().length, 0, "ordinary settings never reserve Bluetooth");
  ui.toggle(true); await settle();
  assert.deepEqual(ui.ops(), ["acquire"]);
  assert.ok(ui.root.textContent.includes("Пульт"));
  assert.ok(!ui.ops().includes("discover"), "opening is not automatic discovery");
  if (kind === "tv") for (const call of ui.bluetoothCalls()) {
    assert.equal(call.options.headers["X-TV-Launcher"], "1");
    assert.equal(call.options.headers.Origin, undefined, "browser owns Origin");
  }
  ui.document.hidden = true; ui.event("visibilitychange"); await settle();
  assert.deepEqual(ui.ops(), ["acquire", "release"]);
  assert.ok(!ui.root.textContent.includes("Пульт"));
  ui.document.hidden = false; ui.event("visibilitychange"); await settle();
  assert.deepEqual(ui.ops(), ["acquire", "release", "acquire"]);
  ui.run(kind === "tv" ? "closeSettings()" : 'showPage("menu")'); await settle();
  assert.deepEqual(ui.ops(), ["acquire", "release", "acquire", "release"]);
  ui.toggle(false); await settle();
  assert.equal(ui.ops().filter(op => op === "release").length, 2, "no double release");
});

for (const kind of ["tv", "phone"]) test(`${kind}: shared Bluetooth panel shows Name and Alias`, async () => {
  const ui = host(kind); await settle();
  Object.assign(ui.state.devices[0], {name:"Remote", bluez_name:"Remote", alias:"Nickname"});
  ui.run(kind === "tv" ? "openSettings()" : 'showPage("settings")');
  ui.toggle(true); await settle();
  assert.ok(ui.root.textContent.includes("Remote (псевдоним: Nickname)"));
});

for (const kind of ["tv", "phone"]) test(`${kind}: Bluetooth management remains without remote mapping controls`, async () => {
  const ui = host(kind); await settle();
  ui.state.remote = {device_id:"device", connected:true, input_available:false, reason:"helper_unavailable", bindings:{KEY_ENTER:"ok"}};
  ui.state.devices[0].selected = true;
  ui.run(kind === "tv" ? "openSettings()" : 'showPage("settings")'); ui.toggle(true); await settle();
  const keys = ui.root.querySelectorAll("button, input, select").map(n => n.dataset.btKey);
  for (const removed of ["select_remote", "action", "learn", "test", "bind", "reset", "unmap:KEY_ENTER"])
    assert.ok(!keys.includes(removed), removed);
  assert.ok(keys.includes("discover"));
  assert.ok(keys.includes("disconnect"));
  assert.ok(keys.includes("forget_prepare"));
  assert.deepEqual(ui.ops(), ["acquire"]);
  assert.deepEqual(ui.state.remote.bindings, {KEY_ENTER:"ok"});
});

test("TV: dynamic rendered actions exclude detached, disabled, closed and hidden nodes", async () => {
  const ui = host("tv"); await settle(); ui.run("openSettings()");
  const summary = ui.details.querySelector("summary");
  assert.ok(ui.run("settingsActions()").includes(summary));
  ui.toggle(true); await settle();
  const discover = ui.root.querySelectorAll("button").find(n => n.dataset.btKey === "discover");
  assert.ok(ui.run("settingsActions()").includes(discover));
  ui.run("tvBluetoothPanel.render()");
  assert.ok(!ui.run("settingsActions()").includes(discover), "rerendered stale nodes are not kept");
  const current = ui.root.querySelectorAll("button").find(n => n.dataset.btKey === "discover");
  current.disabled = true;
  assert.ok(!ui.run("settingsActions()").includes(current));
  ui.toggle(false); await settle();
  assert.ok(!ui.run("settingsActions()").some(n => ui.root.contains(n)));
  summary.focus();
  ui.event("keydown", {key:"ArrowDown"});
  assert.notEqual(ui.document.activeElement, summary);
  assert.ok(ui.run("settingsActions()").includes(ui.document.activeElement));
  // An empty action list is safe for keyboard and bridge OK.
  for (const action of ui.run("settingsActions()")) action.disabled = true;
  assert.doesNotThrow(() => ui.event("keydown", {key:"ArrowDown"}));
  assert.doesNotThrow(() => ui.event("ad-linux-tv-select-for-bridge"));
});

test("TV: text/password caret, up/down navigation, Back/F8 and reserved F9/F12 survive", async () => {
  const ui = host("tv"); await settle();
  const f8 = ui.event("keydown", {key:"F8"}); assert.equal(f8.prevented, true);
  for (const role of ["pin", "proxy-host"]) {
    const field = ui.one(`[data-role="${role}"]`); field.focus();
    assert.equal(ui.document.activeElement, field);
    for (const key of ["ArrowLeft", "ArrowRight", "Home", "BrowserHome"]) {
      assert.ok(!ui.event("keydown", {key}).prevented);
      assert.equal(ui.document.activeElement, field);
    }
    ui.event("keydown", {key:"ArrowDown"});
    assert.notEqual(ui.document.activeElement, field);
  }
  for (const key of ["F9", "F12"]) assert.ok(!ui.event("keydown", {key}).prevented);
  ui.toggle(true); await settle();
  ui.event("keydown", {key:"Escape"}); await settle();
  assert.equal(ui.one("#settings").hidden, true);
  assert.equal(ui.ops().at(-1), "release");
});

for (const reason of ["transport", "auth", "native"]) test(`phone: ${reason} retires immediately without release/reacquire or stale callbacks`, async () => {
  const ui = host("phone"); await settle(); ui.run('showPage("settings")'); ui.toggle(true); await settle();
  assert.deepEqual(ui.ops(), ["acquire"]);
  ui.bootstrap = false;
  if (reason === "transport") ui.transport.close();
  else if (reason === "auth") ui.run("requireLogin()");
  else ui.context.window.adLinuxTvRemoteLifecycle.suspend();
  await settle();
  assert.equal(ui.details.open, false);
  assert.ok(!ui.root.textContent.includes("Пульт"));
  assert.deepEqual(ui.ops(), ["acquire"], "retirement cannot send privileged release on dead authority");
  ui.document.hidden = true; ui.event("visibilitychange");
  ui.document.hidden = false; ui.event("visibilitychange");
  ui.context.window.adLinuxTvRemoteLifecycle.resume(); await settle();
  assert.deepEqual(ui.ops(), ["acquire"]);
  if (reason === "native") {
    ui.toggle(true); await settle();
    assert.deepEqual(ui.ops(), ["acquire"], "fixed native suspend cannot be undone by DOM toggles");
  }
});

test("phone: component 403 invokes real login retirement and clears the open section", async () => {
  const ui = host("phone"); await settle(); ui.run('showPage("settings")'); ui.toggle(true); await settle();
  ui.status = 403; ui.bootstrap = false;
  await ui.run('phoneBluetoothPanel.receive("POST", {op:"poll",lease:phoneBluetoothPanel.lease}, phoneBluetoothPanel.generation)');
  await settle();
  assert.equal(ui.details.open, false);
  assert.equal(ui.run("csrf"), "");
  assert.equal(ui.ops().filter(op => op === "acquire").length, 1);
  assert.ok(!ui.ops().includes("release"));
});
