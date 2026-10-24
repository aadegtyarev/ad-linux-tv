"use strict";
const fs = require("node:fs");
const vm = require("node:vm");

function launcher({hostname = "192.168.1.4"} = {}) {
  const events = {};
  const calls = [];
  const doc = {
    activeElement: null,
    addEventListener: (name, fn) => {
      const previous = events[name];
      events[name] = previous ? event => { previous(event); fn(event); } : fn;
    },
    dispatchEvent(event) { event.target = this; events[event.type](event); },
    querySelectorAll: () => [],
  };
  class Element {
    constructor(id) { this.id = id; this.children = []; this.dataset = {}; }
    addEventListener(name, fn) { this[`on${name}`] = fn; }
    contains(target) { return target === this || this.children.some(child => child.contains(target)); }
    replaceChildren() {
      if (this.contains(doc.activeElement)) doc.activeElement = doc.body;
      this.children = [];
    }
    append(child) { child.parent = this; this.children.push(child); }
    focus() { doc.activeElement = this; this.onfocus?.(); this.parent?.onfocusin?.({target:this}); }
    click() { this.onclick?.(); }
  }
  doc.body = new Element("body");
  doc.documentElement = new Element("html");
  doc.activeElement = doc.body;
  const elements = Object.fromEntries(
    ["#tiles", "#system-button", ".pagination", "#config-status", "#bridge-status", "#command-status", "#address", "#qr", "#pairing-pin", "#page", "#next", "#prev", "#home", "#settings", "#confirm-kde", "#system-status", "#settings-back", "#open-kde", "#cancel-kde", "#confirm-kde-yes"]
      .map(id => [id, new Element(id)])
  );
  elements["#settings"].hidden = true;
  elements["#confirm-kde"].hidden = true;
  elements["#pairing-pin"].hidden = true;
  doc.querySelector = id => elements[id];
  doc.createElement = name => new Element(name);
  let serviceData = Array.from({length:25}, (_, id) => ({id:`svc-${id}`, name:`Service ${id}`}));
  let remoteAddress = "http://192.168.1.4:8765/remote";
  let bridgeData = {extension_online:true, pending_commands:0, last_command_failure:null};
  let timer;
  const context = {
    document:doc, innerWidth:1920, location:{hostname},
    getComputedStyle:() => ({gridTemplateColumns:"300px 300px 300px 300px"}),
    setInterval(callback) { timer = callback; }, console,
    fetch:async (url, options) => {
      calls.push({url, options});
      return {ok:true, status:200, json:async () => url === "/api/services"
        ? {services:serviceData, page_size:12, remote_address:remoteAddress}
        : url === "/api/local-pin" ? {pin:"1234"} : bridgeData};
    },
  };
  vm.createContext(context);
  for (const file of ["layout.js", "launcher_ui.js", "app.js"]) {
    vm.runInContext(fs.readFileSync(`src/ad_linux_tv/static/${file}`, "utf8"), context);
  }
  return {
    doc, elements, events, calls, context,
    get services() { return serviceData; },
    set services(value) { serviceData = value; },
    get remoteAddress() { return remoteAddress; },
    set remoteAddress(value) { remoteAddress = value; },
    set status(value) { bridgeData = value; },
    refresh() { timer(); },
  };
}

async function ready() { await new Promise(resolve => setImmediate(resolve)); }
module.exports = {launcher, ready};
