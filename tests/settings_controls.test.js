"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function panel() {
  const roles = ["pin-form", "pin-mode", "pin-fields", "pin", "pin-confirm", "magnifier",
    "proxy-form", "proxy-mode", "proxy-fields", "proxy-protocol", "proxy-host", "proxy-port",
    "proxy-restart", "restart", "settings-status"];
  const fields = Object.fromEntries(roles.map(role => [role, {value:"", hidden:false, dataset:{},
    textContent:"", setAttribute() {}}]));
  const pinExtra = {hidden:false};
  const proxyExtras = Array.from({length:3}, () => ({hidden:false}));
  const root = {
    querySelector(selector) { return fields[selector.match(/data-role="([^"]+)"/)[1]]; },
    querySelectorAll(selector) {
      if (selector === '[data-role="pin-fields"]') return [fields["pin-fields"], pinExtra];
      if (selector === '[data-role="proxy-fields"]') return [fields["proxy-fields"], ...proxyExtras];
      return Object.values(fields);
    },
  };
  const calls = [];
  const context = {};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/settings_controls.js", "utf8") +
    "\nglobalThis.SettingsControls = SettingsControls;", context);
  const state = {require_pin:false, magnifier:false, proxy:{mode:"system"}, proxy_restart_required:false};
  const controls = new context.SettingsControls(root, async (method, action) => {
    calls.push({method, action});
    return {ok:true, json:async () => state};
  });
  return {controls, fields, calls, state, pinExtra, proxyExtras};
}

test("settings form keeps hidden fields out of default view and sends confirmed PIN", async () => {
  const ui = panel();
  await ui.controls.refresh();
  assert.equal(ui.fields["pin-fields"].hidden, true);
  assert.equal(ui.fields["proxy-fields"].hidden, true);
  ui.fields["pin-mode"].value = "on";
  ui.fields["pin-mode"].onchange();
  assert.equal(ui.pinExtra.hidden, false);
  ui.fields.pin.value = "1234";
  ui.fields["pin-confirm"].value = "4321";
  await ui.controls.savePin();
  assert.equal(ui.calls.length, 1);
  ui.fields["pin-confirm"].value = "1234";
  await ui.controls.savePin();
  assert.equal(ui.calls[1].action.setting, "pin");
  assert.equal(ui.calls[1].action.value.pin, "1234");
  assert.equal(ui.fields.pin.value, "");
});

test("proxy form sends custom endpoint and magnifier toggles", async () => {
  const ui = panel();
  await ui.controls.refresh();
  ui.fields["proxy-mode"].value = "custom";
  ui.fields["proxy-mode"].onchange();
  assert.ok(ui.proxyExtras.every(field => field.hidden === false));
  ui.fields["proxy-protocol"].value = "socks5";
  ui.fields["proxy-host"].value = " proxy.example ";
  ui.fields["proxy-port"].value = "1080";
  await ui.controls.saveProxy();
  assert.equal(ui.calls.at(-1).action.value.host, "proxy.example");
  assert.equal(ui.calls.at(-1).action.value.port, 1080);
  await ui.controls.change("magnifier", true);
  assert.equal(ui.calls.at(-1).action.value, true);
});
