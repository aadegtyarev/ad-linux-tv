"use strict";
// Actual hosted templates and orchestration, synthetic DOM/network/timers only.
const fs = require("node:fs");
const vm = require("node:vm");
const settle = async () => { for (let n = 0; n < 100; n++) await Promise.resolve(); };
function host(kind) {
  const calls = [], listeners = {}, timers = new Map();
  let timerId = 0;
  const document = {hidden:false, activeElement:null,
    addEventListener(type, fn) { (listeners[type] ||= new Set()).add(fn); },
    removeEventListener(type, fn) { listeners[type]?.delete(fn); },
  };
  class Element {
    constructor(tag, attrs = {}) {
      this.tagName = tag.toUpperCase(); this.attrs = attrs; this.children = []; this.parentElement = null;
      this.ownerDocument = document; this.hidden = "hidden" in attrs; this.open = "open" in attrs;
      this.disabled = "disabled" in attrs; this.dataset = {}; this.style = {}; this.value = attrs.value || "";
      this.type = attrs.type || (tag === "input" ? "text" : ""); this.events = {}; this._text = "";
      this.min = attrs.min; this.max = attrs.max; this.step = attrs.step; this.selectedIndex = 0;
      this.classes = new Set((attrs.class || "").split(/\s+/));
      this.classList = {add: n => this.classes.add(n), remove: n => this.classes.delete(n)};
      for (const [key, value] of Object.entries(attrs)) if (key.startsWith("data-"))
        this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    }
    get options() { return this.children.filter(n => n.tagName === "OPTION"); }
    get isConnected() { return document.body.contains(this); }
    contains(node) { return node === this || this.children.some(child => child.contains(node)); }
    append(child) { child.parentElement = this; this.children.push(child); }
    replaceChildren(...children) { for (const child of this.children) child.parentElement = null; this.children = []; for (const child of children) this.append(child); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(n => n.textContent).join(" "); }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    addEventListener(type, fn) { (this.events[type] ||= []).push(fn); }
    matches(selector) {
      if (selector === "[hidden]") return this.hidden;
      if (selector === "details:not([open])") return this.tagName === "DETAILS" && !this.open;
      if (selector[0] === "#") return this.attrs.id === selector.slice(1);
      if (selector[0] === ".") return this.classes.has(selector.slice(1));
      if (selector[0] === "[") {
        const [, name, value] = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/) || [];
        if (name === "data-secret") return this.dataset.secret !== undefined;
        return name in this.attrs && (value === undefined || this.attrs[name] === value);
      }
      return this.tagName.toLowerCase() === selector;
    }
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
    querySelectorAll(selector) {
      const selectors = selector.split(",").map(s => s.trim());
      return this.children.flatMap(child => [...(selectors.some(s => child.matches(s)) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    getClientRects() {
      if (!this.isConnected || this.closest("[hidden]")) return [];
      const details = this.parentElement?.closest("details:not([open])");
      return details && this.tagName !== "SUMMARY" ? [] : [{}];
    }
    focus() { if (!this.disabled && this.getClientRects().length) document.activeElement = this; }
    blur() { document.activeElement = document.body; }
    click() { if (!this.disabled) this.onclick?.({preventDefault(){}}); }
    setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  }
  document.body = new Element("body"); document.documentElement = new Element("html");
  document.activeElement = document.body;
  document.createElement = tag => new Element(tag);
  document.querySelector = selector => document.body.querySelector(selector);
  document.querySelectorAll = selector => selector === "#settings [data-timer]"
    ? document.querySelector("#settings").querySelectorAll("[data-timer]") : document.body.querySelectorAll(selector);
  const stack = [document.body];
  const html = fs.readFileSync(`src/ad_linux_tv/static/${kind === "tv" ? "index" : "remote"}.html`, "utf8");
  for (const [text, tag, raw] of html.matchAll(/<\/?([a-z][\w-]*)\b([^>]*)>/gi)) {
    if (text.startsWith("</")) { while (stack.length > 1 && stack.pop().tagName !== tag.toUpperCase()) {} continue; }
    const attrs = {};
    for (const [, name, value] of raw.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attrs[name] = value ?? "";
    const element = new Element(tag, attrs); stack.at(-1).append(element);
    if (!/^(meta|link|input|br|img|path)$/.test(tag)) stack.push(element);
  }
  const state = {available:true,reason:"",revision:0,adapter:{id:"adapter",powered:true,discovering:false},
    devices:[{id:"device",name:"Пульт",paired:true,connected:true,selected:false,input_available:false}],remote:null,operation:null};
  const ui = {calls, document, state, bootstrap:true, status:200, closes:0};
  const reply = (status, body) => ({ok:status >= 200 && status < 300,status,json:async()=>body});
  const request = async (path, options = {}) => {
    calls.push({path, options});
    const body = options.body ? JSON.parse(options.body) : null;
    if (path === "/api/bluetooth") return reply(ui.status, {state:ui.state, ...(body?.op === "acquire" ? {lease:"a".repeat(32)} : {})});
    if (path === "/api/session") return reply(ui.bootstrap ? 200 : 401, {csrf:"synthetic-csrf"});
    if (path === "/api/services") return reply(200, {services:[],page_size:12});
    if (path === "/api/audio") return reply(200, {outputs:[],volume:100});
    return reply(200, {});
  };
  const windowEvents = {};
  const context = {document, console, URL, URLSearchParams, performance:{now:()=>0}, location:{hostname:"127.0.0.1"},
    window:{location:{href:"http://127.0.0.1:8765/remote",reload(){},replace(){}},scrollTo(){},
      addEventListener(type, fn) { (windowEvents[type] ||= []).push(fn); }},
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
    setInterval:()=>++timerId, clearInterval(){}, fetch:request,
    AudioLevelsControls:class {sliders(){return [];} actions(){return [];} render(){}},
    SettingsControls:class {field(){return null;} refresh(){} bindMagnifierShortcut(){}},
    PhoneMediaControls:class {start(){} stop(){} reconcile(){}},
    RemotePowerControls:class {start(){} stop(){} dismiss(){} refresh(){} renderTimer(){}},
    createPhoneTouchpad:()=>({stop(){},reset(){},isIdle:()=>true}),
    createLauncherUI:()=>({update(){},selectForBridge(){return "";}}),
    RemoteTransport:class {
      constructor(location, options) { ui.transport = this; this.onClose = options.onClose; this.live = false; }
      request(csrf, method, path, body) { this.live = true; return request(path, {method, ...(body === null ? {} : {body:JSON.stringify(body)})}); }
      close() { if (this.live) { this.live = false; ++ui.closes; this.onClose(); } }
    },
  };
  vm.createContext(context);
  for (const file of ["bluetooth_controls.js", kind === "tv" ? "app.js" : "remote.js"])
    vm.runInContext(fs.readFileSync(`src/ad_linux_tv/static/${file}`, "utf8"), context);
  ui.context = context;
  ui.one = selector => document.querySelector(selector);
  ui.details = ui.one(`#${kind === "tv" ? "tv" : "phone"}-bluetooth-details`);
  ui.root = ui.one(`#${kind === "tv" ? "tv" : "phone"}-bluetooth-controls`);
  ui.run = source => vm.runInContext(source, context);
  ui.event = (type, props = {}) => { const event = {type,preventDefault(){this.prevented=true;},...props}; for (const fn of [...(listeners[type] || [])]) fn(event); return event; };
  ui.toggle = open => { ui.details.open = open; for (const fn of ui.details.events.toggle || []) fn(); };
  ui.bluetoothCalls = () => calls.filter(item => item.path === "/api/bluetooth");
  ui.ops = () => ui.bluetoothCalls().filter(item => item.options.body).map(item => JSON.parse(item.options.body).op);
  return ui;
}
module.exports = {host, settle};
