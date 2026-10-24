"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function launcher() {
  const events = {};
  const calls = [];
  const doc = {
    activeElement: null,
    addEventListener: (name, fn) => (events[name] = fn),
    dispatchEvent(event) { event.target = this; events[event.type](event); },
    querySelectorAll: () => [],
  };
  class Element {
    constructor(id) { this.id = id; this.children = []; this.dataset = {}; }
    addEventListener(name, fn) { this[`on${name}`] = fn; }
    replaceChildren() { this.children = []; }
    append(child) { child.parent = this; this.children.push(child); }
    focus() { doc.activeElement = this; this.onfocus?.(); this.parent?.onfocusin?.({target:this}); }
    click() { this.onclick?.(); }
  }
  const elements = Object.fromEntries(["#tiles", "#error", "#address", "#qr", "#page", "#next", "#prev"]
    .map(id => [id, new Element(id)]));
  doc.querySelector = id => elements[id];
  doc.createElement = name => new Element(name);
  const services = Array.from({length: 25}, (_, id) => ({id:`svc-${id}`, name:`Service ${id}`}));
  const context = {
    document: doc, innerWidth: 1920,
    getComputedStyle: () => ({gridTemplateColumns:"300px 300px 300px 300px"}),
    setInterval() {}, console,
    fetch: async (url, options) => {
      calls.push({url, options});
      return {ok:true, status:200, json:async () => url === "/api/services"
        ? {services, page_size:12, remote_address:"http://192.168.1.4:8765/remote"}
        : {extension_online:true}};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/layout.js", "utf8"), context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/launcher_ui.js", "utf8"), context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/app.js", "utf8"), context);
  return {doc, elements, events, calls, services};
}

async function ready() { await new Promise(resolve => setImmediate(resolve)); }

test("launcher focus uses actual columns and carries arrows across pages", async () => {
  const ui = launcher();
  await ready();
  assert.equal(ui.elements["#tiles"].children.length, 12);
  assert.equal(ui.elements["#page"].textContent, "1 / 3");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "4");
  ui.elements["#next"].onclick();
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "12");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "16");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
});

test("Tab/click focus remains the item activated by bridge OK", async () => {
  const ui = launcher();
  await ready();
  ui.elements["#tiles"].children[3].focus();
  ui.doc.dispatchEvent({type:"keydown", key:"Enter", isTrusted:false, preventDefault(){}});
  await ready();
  const command = ui.calls.find(call => call.url === "/api/command");
  assert.equal(JSON.parse(command.options.body).service_id, "svc-3");
  ui.elements["#next"].focus();
  ui.doc.dispatchEvent({type:"keydown", key:"Enter", isTrusted:false, preventDefault(){}});
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "12");
});
