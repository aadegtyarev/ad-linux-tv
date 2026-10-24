"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("paired phone remote loads audio and sends bounded volume with CSRF", async () => {
  const calls = [];
  class Element {
    constructor() { this.dataset = {}; this.children = []; this.value = ""; this.hidden = false; }
    replaceChildren() { this.children = []; }
    append(item) { this.children.push(item); }
  }
  const ids = ["#message", "#login", "#login-panel", "#controls", "#status", "#pin",
    "#services", "#audio-output", "#audio-volume", "#audio-volume-value", "#audio-status",
    "#audio-mute", "#audio-refresh", "#open", "#text-form", "#remote-text", "#url-form",
    "#remote-url", "#key-backspace", "#key-enter", "#key-tab", "#key-shift-tab", "#key-address"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const context = {
    document: {querySelector: id => elements[id], querySelectorAll: () => [], createElement: () => new Element()},
    setInterval: () => 1, clearInterval: () => {}, setTimeout, URL, console,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      const data = url === "/api/login" ? {csrf:"test-csrf"}
        : url === "/api/services" ? {services:[{id:"browser",name:"Браузер"}]}
          : url === "/api/audio" ? {outputs:[{id:"hdmi",name:"HDMI"}],selected:"hdmi",volume:100,muted:false}
            : {extension_online:true,pending_commands:0,last_command_failure:null};
      return {ok:true,status:200,json:async () => data};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/remote.js", "utf8"), context);
  elements["#pin"].value = "test-pin";
  await elements["#login"].onsubmit({preventDefault(){}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements["#audio-output"].value, "hdmi");
  elements["#audio-volume"].value = "55";
  await elements["#audio-volume"].onchange();
  const request = calls.find(call => call.url === "/api/audio" && call.options.method === "POST");
  assert.equal(request.options.headers["X-CSRF-Token"], "test-csrf");
  assert.equal(JSON.parse(request.options.body).volume, 55);
});
