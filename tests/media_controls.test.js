"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("phone media panel follows Firefox state and disables unsupported controls", async () => {
  class Element {
    constructor() {
      this.hidden = false;
      this.disabled = false;
      this.value = "0";
      this.listeners = {};
      this.classes = new Set();
      this.classList = {add: value => this.classes.add(value), remove: value => this.classes.delete(value)};
    }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    setAttribute(name, value) { this[name] = value; }
  }
  const ids = ["#media-panel", "#remote-face", "#media-title", "#media-elapsed",
    "#media-duration", "#media-position", "#media-previous", "#media-play", "#media-next"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  let state = {available:true,title:"A very long track name",playing:true,position:30,duration:120,
    can_play:true,can_pause:true,can_seek:true,can_next:false,can_previous:true};
  const calls = [];
  const context = {
    document:{querySelector:id => elements[id]},
    setInterval:() => 1, clearInterval:() => {},
    request:async (method, path, body) => {
      calls.push({method,path,body});
      if (method === "POST" && body.action === "pause") state = {...state,playing:false};
      return {ok:true,status:200,json:async () => state};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/media_controls.js", "utf8"), context);
  const media = vm.runInContext("new PhoneMediaControls(request, () => {})", context);
  await media.refresh();
  assert.equal(elements["#media-panel"].hidden, false);
  assert.equal(elements["#media-title"].textContent, "A very long track name");
  assert.equal(elements["#media-next"].disabled, true);
  assert.equal(elements["#media-previous"].disabled, false);
  assert.equal(elements["#media-position"].value, 30);
  assert.equal(elements["#media-duration"].textContent, "2:00");
  elements["#media-position"].value = "45";
  elements["#media-position"].onchange();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.at(-1).body.position, 45);
  elements["#media-play"].onclick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.at(-1).body.action, "pause");
  assert.equal(elements["#media-play"].textContent, "▶");
  state = {available:false};
  await media.refresh();
  assert.equal(elements["#media-panel"].hidden, true);
  assert.equal(elements["#remote-face"].classes.has("has-media"), false);
});
