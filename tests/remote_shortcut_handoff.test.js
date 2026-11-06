"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

// Exercise the actual remote.js wiring independently of Bluetooth's lease tests.
test("Bluetooth handoff opens and focuses the same phone wizard", async () => {
  const source = fs.readFileSync("src/ad_linux_tv/static/remote.js", "utf8");
  const start = source.indexOf('const phoneBluetoothDetails =');
  const end = source.indexOf('if (phoneSettingsPanel) phoneSettingsPanel.bindMagnifierShortcut', start);
  assert.ok(start >= 0 && end > start);
  let focused = 0, scrolled = 0, restartFocused = 0, restartScrolled = 0;
  const summary = {focus: () => focused++};
  const restartLink = {addEventListener: (_event, callback) => {restartLink.click = callback;}};
  const restartButton = {closest:()=>null, focus:()=>restartFocused++,
    scrollIntoView:()=>restartScrolled++};
  const bluetooth = {open:true, addEventListener(){}};
  const shortcuts = {open:false, addEventListener(){}, querySelector:() => summary,
    scrollIntoView: () => scrolled++};
  const nodes = {"#phone-bluetooth-details":bluetooth, "#phone-shortcuts-details":shortcuts,
    "#phone-bluetooth-controls":{}, "#phone-shortcut-controls":{querySelector:()=>restartLink},
    "#remote-settings-page":{hidden:false}};
  const context = {
    document:{hidden:false, querySelector: selector => nodes[selector]},
    controls:{hidden:false}, csrf:"fixture", remoteSuspended:false,
    remoteFetch:async()=>({ok:true}), requireLogin(){}, phoneSettingsPanel:null,
    phoneSettingsRoot:{querySelector:()=>restartButton},
    phoneBluetoothPanel:null, phoneShortcutPanel:null,
  };
  let bt, keys;
  context.BluetoothControls = class {
    constructor(_root, _request, options) { this.options=options; this.closed=0; bt=this; }
    deactivate() { this.closed++; }
    activate() {}
    retire() {}
  };
  context.TvShortcutControls = class {
    constructor() { this.opened=0; keys=this; }
    deactivate() {}
    activate() { this.opened++; }
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start,end), context);
  bt.options.openShortcuts();
  assert.equal(bluetooth.open,false);
  assert.equal(bt.closed,1);
  assert.equal(shortcuts.open,true);
  assert.equal(keys.opened,1);
  assert.equal(focused,1);
  assert.equal(scrolled,1);
  restartLink.click();
  assert.equal(restartFocused,1);
  assert.equal(restartScrolled,1);
});
