"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {validateView,createViewPolicy} = require("../extension/view_policy.js");
const {createTabController} = require("../extension/tabs.js");
const {browserMock} = require("./helpers/browser_mock.js");
const {LAUNCHER} = require("../extension/tab_storage.js");

function APIs(calls = []) {
  const listeners = new Set();
  const currentSettings={mode:"automatic",scope:"per-tab",defaultZoomFactor:1};
  return {listeners,runtime:{getBrowserInfo:async()=>({version:"157.0.2"})},
    tabs:{getZoomSettings:async id=>{calls.push(["settings",id]); return {...currentSettings};},
      setZoomSettings:async(id,settings)=>{
        const hydrated={defaultZoomFactor:null,...settings};
        calls.push(["scope",id,hydrated]);
        if (Object.entries(hydrated).some(([key,value])=>currentSettings[key]!==value))
          throw new Error(`Unsupported zoom settings: ${JSON.stringify(hydrated)}`);
      },
      setZoom:async(id,zoom)=>calls.push(["zoom",id,zoom])},
    webRequest:{onBeforeSendHeaders:{
      addListener(fn,filter,extra) { listeners.add(fn); calls.push(["header",filter,extra]); },
      removeListener(fn) { listeners.delete(fn); calls.push(["unhook"]); },
    }}};
}

test("view schema is bounded, default is no-op, and mobile is not arbitrary script/headers", async () => {
  assert.equal(validateView(undefined),undefined);
  assert.deepEqual(validateView({mode:"mobile"}),{mode:"mobile",zoom:200});
  for (const raw of [null,true,[],{}, {mode:"auto"},{mode:"mobile",zoom:null},
    {mode:"mobile",zoom:301},{mode:"desktop",zoom:true},{mode:"mobile",headers:{}},
    {mode:"mobile",script:"not allowed"}]) assert.throws(()=>validateView(raw));
  const calls = [], api = APIs(calls), tab={id:5,windowId:1};
  const policy = createViewPolicy(api,()=>true);
  await policy.bind(tab,undefined); await policy.zoom(tab,undefined);
  assert.deepEqual(calls,[]);
});

test("mobile hook is native-tab-filtered and never reads auth header values", async () => {
  const calls=[],api=APIs(calls),tab={id:5,windowId:1};
  let owned=true;
  const policy=createViewPolicy(api,()=>owned);
  await policy.bind(tab,{mode:"mobile"});
  assert.deepEqual(calls[0],["header",{urls:["http://*/*","https://*/*"],tabId:5,windowId:1},["blocking","requestHeaders"]]);
  const listener=[...api.listeners][0];
  const cookie={name:"Cookie",get value(){throw new Error("credentials must not be read");}};
  const auth={name:"Authorization",get value(){throw new Error("credentials must not be read");}};
  const response=listener({tabId:5,requestHeaders:[cookie,auth,{name:"User-Agent",value:"desktop"}]});
  assert.equal(response.requestHeaders[0],cookie); assert.equal(response.requestHeaders[1],auth);
  assert.match(response.requestHeaders[2].value,/Android 13; Mobile; rv:157\.0/);
  const inaccessible={tabId:6,get requestHeaders(){throw new Error("unowned metadata read");}};
  assert.deepEqual(listener(inaccessible),{});
  owned=false;
  assert.deepEqual(listener({tabId:5,get requestHeaders(){throw new Error("retired metadata read");}}),{});
});

test("changing to desktop/unowned retires old hook before any future header access", async () => {
  const api=APIs(),tab={id:5,windowId:1}; let owned=true;
  const policy=createViewPolicy(api,()=>owned);
  await policy.bind(tab,{mode:"mobile"});
  const stale=[...api.listeners][0];
  await policy.bind(tab,{mode:"desktop",zoom:125});
  assert.equal(api.listeners.size,0);
  assert.deepEqual(stale({tabId:5,get requestHeaders(){throw new Error("stale");}}),{});
  owned=false;
  await assert.rejects(policy.bind(tab,{mode:"mobile"}),/unowned/);
  await assert.rejects(policy.zoom(tab,{mode:"desktop"}),/unowned/);
});

test("zoom is per-tab only and never falls back to per-origin when settings fail", async () => {
  const calls=[],api=APIs(calls),tab={id:5,windowId:1};
  const policy=createViewPolicy(api,()=>true);
  await policy.zoom(tab,{mode:"desktop",zoom:150});
  assert.deepEqual(calls,[["settings",5],["zoom",5,1.5]]);
  calls.length=0;
  api.tabs.getZoomSettings=async id=>{calls.push(["settings",id]); return {mode:"automatic",scope:"per-origin",defaultZoomFactor:1};};
  await assert.rejects(policy.zoom(tab,{mode:"mobile"}),/unsupported zoom settings/);
  assert.deepEqual(calls,[["settings",5]]);
  calls.length=0;
  api.tabs.getZoomSettings=async()=>{throw new Error("settings unavailable");};
  await assert.rejects(policy.zoom(tab,{mode:"mobile"}),/settings unavailable/);
  assert.deepEqual(calls,[]);
});

test("retired ownership during settings read prevents zoom", async () => {
  const calls=[],api=APIs(calls),tab={id:5,windowId:1}; let owned=true;
  api.tabs.getZoomSettings=async id=>{calls.push(["settings",id]); owned=false; return {mode:"automatic",scope:"per-tab"};};
  const policy=createViewPolicy(api,()=>owned);
  await assert.rejects(policy.zoom(tab,{mode:"desktop",zoom:125}),/retired zoom target/);
  assert.deepEqual(calls,[["settings",5]]);
});

test("unavailable restored view never blocks legacy Home or claims its capability", async () => {
  const mock=browserMock([{id:1,windowId:1,url:LAUNCHER},{id:2,windowId:1,url:"https://same.example/one"}]);
  mock.storage.session.managedTabs={one:{tabId:2,windowId:1,view:{mode:"mobile",zoom:200}}};
  const controller=createTabController(mock.api,mock.fetcher);
  await controller.restore();
  assert.ok(!controller.capabilities().includes("tab_view_v1"));
  assert.equal((await controller.execute({id:"view-recover-home",command:"home"})).outcome,"completed");
  assert.equal(mock.tabs.has(2),false);
});

test("owned mobile navigation installs header before first request and removes it on Home", async () => {
  const services=[{id:"one",url:"https://same.example/one",view:{mode:"mobile"}}];
  const mock=browserMock([{id:1,windowId:1,url:LAUNCHER}],services), extra=APIs(mock.calls);
  Object.assign(mock.api.tabs,extra.tabs); mock.api.webRequest=extra.webRequest; mock.api.runtime=extra.runtime;
  const controller=createTabController(mock.api,mock.fetcher);
  await controller.restore();
  assert.equal((await controller.execute({id:"view-open-one",command:"open",service_id:"one"})).outcome,"completed");
  const created=mock.calls.find(call=>call[0]==="create");
  assert.equal(created[2].url,"about:blank");
  const header=mock.calls.findIndex(call=>call[0]==="header");
  const navigate=mock.calls.findIndex(call=>call[0]==="update" && call[2].url===services[0].url);
  assert.ok(header>=0 && navigate>header);
  const settings=mock.calls.findIndex(call=>call[0]==="settings");
  const zoomed=mock.calls.findIndex(call=>call[0]==="zoom");
  assert.ok(settings>header && zoomed>settings && navigate>zoomed);
  assert.equal(mock.calls.find(call=>call[0]==="zoom")[2],2);
  assert.ok(controller.capabilities().includes("tab_view_v1"));
  assert.equal((await controller.execute({id:"view-home-00",command:"home"})).outcome,"completed");
  assert.equal(extra.listeners.size,0);
});
