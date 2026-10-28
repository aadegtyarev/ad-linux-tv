"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync("src/ad_linux_tv/static/remote.html", "utf8");
const apk = "/download/ad-linux-tv-remote-0.2.5-code6.apk";

// Parse the actual template hierarchy: visibility includes hidden ancestors.
// No navigation, network, timers, browser profile or actuator is used here.
function fixture({fragment = "", session = false, appInfo, navigator} = {}) {
  const nodes = [], stack = [];
  const matchSelector = (node, selector) => selector.startsWith("#") ? node.attrs.id === selector.slice(1)
    : selector.startsWith(".") ? (node.attrs.class || "").split(" ").includes(selector.slice(1))
      : selector.startsWith("[") ? (() => {
        const [,name,value] = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/) || [];
        return name in node.attrs && (value === undefined || node.attrs[name] === value);
      })() : node.tag === selector;
  for (const token of html.matchAll(/<\/?([a-z][\w-]*)\b([^>]*)>/gi)) {
    const [text,tag,raw] = token;
    if (text.startsWith("</")) { while (stack.length && stack.pop().tag !== tag) {} continue; }
    const attrs = {};
    for (const attr of raw.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attrs[attr[1]] = attr[2] ?? "";
    const node = {tag,attrs,parent:stack.at(-1),hidden:"hidden" in attrs,dataset:{},value:"",listeners:{},
      classList:{add(){},remove(){}},style:{},children:[],
      setAttribute(name,value){ this.attrs[name] = value; }, removeAttribute(name){ delete this.attrs[name]; },
      addEventListener(name,fn){ (this.listeners[name] ||= []).push(fn); },
      focus(){},blur(){},replaceChildren(){},append(){},
      closest(selector){ for(let n=this;n;n=n.parent) if(matchSelector(n,selector)) return n; return null; },
    };
    nodes.push(node);
    if (!/^(meta|link|input|br|img|path)$/.test(tag)) stack.push(node);
  }
  const all = selector => nodes.filter(n => matchSelector(n,selector));
  const one = selector => all(selector)[0];
  const events = {}, calls = [], bootstrap = [];
  const context = {URL,URLSearchParams,console,encodeURIComponent,
    ...(navigator === undefined ? {} : {navigator}),
    setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},
    window:{location:{href:`http://192.168.1.111:8765/remote${fragment}`,replace(){throw Error("redirect");}},
      adLinuxTvAppInfo:appInfo,addEventListener(){},scrollTo(){}},
    document:{querySelector:s=>s==="#phone-settings-controls" ? null : one(s),querySelectorAll:all,
      addEventListener(name,fn){ (events[name] ||= []).push(fn); },createElement:()=>({})},
    fetch:async(path,options)=>{ bootstrap.push({path,options}); return {ok:session,status:session?200:401,json:async()=>({csrf:"fixture-only"})}; },
    // These collaborators are inert: assertions target actual remote orchestration,
    // existing transport binding parser and actual template targets/listeners.
    PhoneMediaControls:class {start(){} stop(){} reconcile(){}},
    RemotePowerControls:class {start(){} stop(){} dismiss(){} renderTimer(){} refresh(){}},
    AudioLevelsControls:class {render(){} actions(){return [];}},
    createPhoneTouchpad:()=>({reset(){},stop(){},isIdle:()=>true}),
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/remote_transport.js","utf8"),context);
  context.record = (method,path,body) => {calls.push({method,path,body}); return Promise.resolve({ok:false,status:503,json:async()=>({})});};
  vm.runInContext("RemoteTransport.prototype.request = function(csrf,method,path,body) { return record(method,path,body); };",context);
  const load = () => vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/remote.js","utf8"),context);
  const visible = node => { for(let n=node;n;n=n.parent) if(n.hidden) return false; return true; };
  return {context,nodes,one,all,events,calls,bootstrap,load,visible,
    dispatch(target,type,key){ const e={target,key,preventDefault(){}}; for(const fn of events[type] || []) fn(e); for(const fn of target.listeners[type] || []) fn(e); target[`on${type}`]?.(e); },
  };
}
const settle = () => new Promise(resolve=>setImmediate(resolve));

test("ordinary browser APK is visible before PIN and on PIN-free/restored MAIN, not menu-only",async()=>{
  for(const session of [false,true]) {
    const f=fixture({session}); f.load(); await settle();
    assert.equal(f.one("#controls").hidden,!session);
    assert.equal(f.one("#login-panel").hidden,session);
    const entry=f.all("[data-apk-browser]").find(n=>n.attrs.class==="remote-apk-entry");
    const main=f.one(".remote-apk-main");
    assert.equal(f.visible(entry),!session);
    assert.equal(f.visible(main),session);
    assert.equal(f.bootstrap.length,1);
    assert.equal(f.bootstrap[0].path,"/api/session");
    await vm.runInContext('activateRemote("fixture-only",true)',f.context);
    assert.equal(f.visible(main),true,"PIN-free auto-entry and saved-session activation keep the MAIN link");
    await vm.runInContext('restoreLogin()',f.context); await settle();
    if(session) assert.equal(f.visible(main),true,"restored MAIN link is visible");
    f.one("#show-menu").onclick();
    assert.ok(f.all("[data-apk-browser]").some(n=>f.visible(n) && n.tag==="p"));
    vm.runInContext('showPage("remote")',f.context);
    assert.equal(f.visible(main),true);
  }
});

test("old/new bound pages and late metadata keep APK links suppressed; invalid binding fails closed",async()=>{
  const id="12345678-1234-1234-1234-123456789abc";
  for(const appInfo of [undefined,{version:"0.2.5",build:6}]) {
    const f=fixture({fragment:`#device=${id}`,session:true,appInfo}); f.load(); await settle();
    assert.ok(f.all("[data-apk-browser]").every(n=>!f.visible(n)));
    assert.equal(f.bootstrap[0].path,`/api/session?device=${id}`);
    f.context.window.adLinuxTvAppInfo={version:"0.2.5",build:6};
    vm.runInContext('showPage("menu")',f.context);
    const guidance=f.one("[data-apk-bound]");
    assert.ok(f.visible(guidance));
    assert.equal(guidance.closest("a"),null);
    assert.ok(f.all("[data-apk-browser]").every(n=>!f.visible(n)));
    const before=f.calls.length;
    f.dispatch(guidance,"pointerdown"); f.dispatch(guidance,"click"); f.dispatch(guidance,"keydown","Enter");
    assert.equal(f.calls.length,before);
    assert.equal(f.context.window.location.href,`http://192.168.1.111:8765/remote#device=${id}`);
  }
  for(const fragment of ["#device=bad","#device=", "#device=ABCDEF00-1234-1234-1234-123456789abc"]) {
    const f=fixture({fragment}); assert.throws(f.load,/invalid device binding/);
    assert.ok(f.all("[data-apk-browser]").every(n=>!f.visible(n)));
    assert.equal(f.bootstrap.length,0);
  }
});

test("fixed explicit safe browser attachment navigation carries no credentials and never wakes/controls",async()=>{
  const f=fixture({session:true}); f.load(); await settle();
  const links=f.all("a").filter(n=>n.attrs.href===apk);
  assert.equal(links.length,3);
  for(const link of links) {
    assert.equal(link.attrs.target,"_blank","503 opens separately, retaining the remote");
    assert.equal(link.attrs.rel,"noopener noreferrer");
    assert.equal(link.attrs.referrerpolicy,"no-referrer");
    assert.ok("data-no-wake" in link.attrs);
    const before=f.calls.length;
    vm.runInContext('displayAsleep = true; lastWakeHint = -Infinity',f.context);
    for(const type of ["pointerdown","click","keydown","keyup"]) f.dispatch(link,type,"Enter");
    assert.equal(f.calls.length,before,"APK activation is not input, playback, power or wake");
    assert.equal(link.onclick,undefined);
  }
  assert.ok(f.bootstrap.every(c=>!c.path.includes("download")));
  assert.ok(f.calls.every(c=>!c.path.includes("download")));
  // Negative control proves the real generic wake listener was exercised above.
  f.dispatch(f.one("#show-keyboard"),"pointerdown");
  assert.ok(f.calls.some(c=>c.method==="POST" && c.path==="/api/display-timer" && c.body.wake));
});

test("desktop/unknown browser preserves invitation; app metadata alone is not platform identity",async()=>{
  for(const appInfo of [undefined,{version:"0.2.5",build:6}]) {
    const f=fixture({session:true,appInfo}); f.load(); await settle();
    assert.ok(f.visible(f.one(".remote-apk-main")));
    assert.equal(f.one("[data-apk-bound]").hidden,true);
  }
  assert.match(html,/На Android вы можете/);
  assert.match(html,/В браузере пульт работает без приложения/);
  assert.match(html,/Если файл недоступен, закройте новую вкладку/);
});

test("iOS invitations stay hidden before PIN, on MAIN/menu and after session restoration",async()=>{
  const ios = [
    {userAgent:"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Version/18.0 Mobile Safari/604.1",platform:"iPhone",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) CriOS/130.0 Mobile Safari/604.1",platform:"iPhone",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) Mobile Safari/604.1",platform:"iPad",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (iPod touch; CPU iPhone OS 15_0 like Mac OS X)",platform:"iPod",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Version/18.0 Safari/605.1.15",platform:"MacIntel",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Safari/605.1.15",platform:"",maxTouchPoints:5},
    {platform:"MacIntel",maxTouchPoints:5},
  ];
  for(const navigator of ios) for(const session of [false,true]) {
    const f=fixture({navigator,session}); f.load(); await settle();
    const hidden=()=>assert.ok(f.all("[data-apk-browser]").every(n=>n.hidden));
    hidden(); assert.equal(f.one("#controls").hidden,!session);
    assert.equal(f.bootstrap[0].path,"/api/session","platform does not alter bootstrap/binding");
    await vm.runInContext('activateRemote("fixture-only",true)',f.context); hidden();
    assert.equal(f.one("#controls").hidden,false,"web controls remain available");
    f.one("#show-menu").onclick(); hidden();
    assert.equal(f.one("[data-apk-bound]").hidden,true,"no Android-only guidance on iOS");
    f.context.window.adLinuxTvAppInfo={version:"0.2.5",build:6};
    await vm.runInContext('restoreLogin()',f.context); await settle(); hidden();
    vm.runInContext('showPage("remote")',f.context); hidden();
  }
});

test("Android and desktop hints keep MAIN invitation, while bound Android guidance remains",async()=>{
  const platforms = [
    {userAgent:"Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile Safari/537.36",platform:"Linux armv8l",maxTouchPoints:5},
    {userAgent:"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/605.1.15",platform:"MacIntel",maxTouchPoints:0},
    {userAgent:"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",platform:"Win32",maxTouchPoints:10},
    {userAgent:"Mozilla/5.0 (X11; Linux x86_64)",platform:"Linux x86_64",maxTouchPoints:0},
    {platform:"MacIntel",maxTouchPoints:1},
    {},
  ];
  for(const navigator of platforms) {
    const f=fixture({navigator,session:true}); f.load(); await settle();
    assert.ok(f.visible(f.one(".remote-apk-main")));
    assert.equal(f.one("[data-apk-bound]").hidden,true);
  }
  const android=platforms[0],id="12345678-1234-1234-1234-123456789abc";
  const bound=fixture({navigator:android,session:true,fragment:`#device=${id}`});bound.load();await settle();
  bound.one("#show-menu").onclick();assert.ok(bound.visible(bound.one("[data-apk-bound]")));
  const iosBound=fixture({navigator:{userAgent:"iPhone"},session:true,fragment:`#device=${id}`});iosBound.load();await settle();
  iosBound.one("#show-menu").onclick();assert.equal(iosBound.one("[data-apk-bound]").hidden,true);
  assert.equal(iosBound.bootstrap[0].path,`/api/session?device=${id}`);
  const invalid=fixture({navigator:{userAgent:"iPhone"},fragment:"#device=bad"});assert.throws(invalid.load,/invalid device binding/);assert.equal(invalid.bootstrap.length,0);
});
