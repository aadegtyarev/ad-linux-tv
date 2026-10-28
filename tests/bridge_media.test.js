"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController} = require("../extension/tabs.js");
const {createBridgeController} = require("../extension/bridge.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");
const state = id => ({media_id:id.repeat(32),playing:true,position:12,duration:900,can_seek:true});
const request = (id, mediaId = "a") => ({id,command:"media",action:"seek",
  media_id:mediaId.repeat(32),position:30,deadline:Date.now()+5000});
async function owned() {
  const mock = browserMock([{id:1,windowId:1,url:LAUNCHER}]);
  const controller = createTabController(mock.api,mock.fetcher);
  await controller.restore();
  await controller.execute({id:"html-open-one",command:"open",service_id:"one"});
  mock.setScriptingResults([{frameId:5,result:state("a")}]);
  return {mock,controller};
}

test("media command uses one owned frame/identity and ledger never repeats its effect", async () => {
  const {mock,controller} = await owned();
  assert.equal((await controller.mediaSnapshot()).media_id,"a".repeat(32));
  const item = request("html-seek-once");
  assert.equal((await controller.execute(item)).outcome,"completed");
  assert.equal((await controller.execute(item)).outcome,"completed");
  const effects = mock.calls.filter(call => call[0] === "script" && call[1].args?.[0] === "seek");
  assert.equal(effects.length,1);
  assert.deepEqual(effects[0][1].target.frameIds,[5]);
  assert.deepEqual(effects[0][1].args,["seek","a".repeat(32),30,item.deadline]);
});

test("unmanaged active tabs are neither inspected nor controlled", async () => {
  const {mock,controller} = await owned();
  await controller.mediaSnapshot();
  await mock.api.tabs.create({url:"https://unmanaged.example/",active:true});
  const before = mock.calls.filter(call => call[0] === "script").length;
  assert.equal(await controller.mediaSnapshot(),null);
  assert.equal((await controller.execute(request("html-unmanaged"))).reason,"no_media");
  assert.equal(mock.calls.filter(call => call[0] === "script").length,before);
});

test("changed media, ambiguous frames and expired commands fail without an action injection", async () => {
  const {mock,controller} = await owned();
  await controller.mediaSnapshot();
  mock.setScriptingResults([{frameId:5,result:state("b")}]);
  await controller.mediaSnapshot();
  assert.equal((await controller.execute(request("html-stale"))).reason,"no_media");
  const expired = {...request("html-expired","b"),deadline:Date.now()-1};
  assert.equal((await controller.execute(expired)).reason,"no_media");
  mock.setScriptingResults([{frameId:5,result:state("b")},{frameId:8,result:state("c")}]);
  assert.equal(await controller.mediaSnapshot(),null);
  assert.equal((await controller.execute(request("html-ambiguous","b"))).reason,"no_media");
  assert.equal(mock.calls.filter(call => call[0] === "script" && call[1].args?.[0] === "seek").length,0);
});

test("snapshot returning after active tab changes is discarded, not retargeted", async () => {
  const {mock,controller} = await owned();
  let complete;
  mock.api.scripting.executeScript = () => new Promise(resolve => { complete = resolve; });
  const pending = controller.mediaSnapshot();
  await new Promise(resolve => setImmediate(resolve));
  await mock.api.tabs.create({url:"https://unmanaged.example/",active:true});
  complete([{frameId:5,result:state("a")}]);
  assert.equal(await pending,null);
});

test("timed-out dispatched media remains uncertain even after late completion, never replays", async () => {
  const {mock,controller} = await owned();
  await controller.mediaSnapshot();
  let complete, effects = 0;
  mock.api.scripting.executeScript = () => { effects++; return new Promise(resolve => { complete = resolve; }); };
  const item = {...request("html-unknown"),deadline:Date.now()+80};
  assert.equal((await controller.execute(item)).outcome,"uncertain");
  assert.equal((await controller.execute(item)).outcome,"uncertain");
  complete([{frameId:5,result:state("a")}]);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal((await controller.execute(item)).outcome,"uncertain");
  assert.equal(effects,1);
  assert.equal(controller.getState().commands[item.id].state,"uncertain");
});

test("unsupported snapshot endpoint does not block legacy polling/ACK and report has no private metadata", async () => {
  const requests = [];
  const tabs = {restore:async()=>{},mediaSnapshot:async()=>state("a"),execute:async()=>({outcome:"completed"})};
  const wire = async (url,options) => {
    requests.push([url,options]);
    if (url.endsWith("/poll")) return {ok:true,json:async()=>[{id:"legacy-home",command:"home"}]};
    return {ok:!url.endsWith("/media")};
  };
  await createBridgeController(tabs,wire,{error(){}}).wake();
  assert.equal(requests.filter(([url]) => url.endsWith("/ack")).length,1);
  const reports = requests.filter(([url]) => url.endsWith("/media")).map(([,options])=>JSON.parse(options.body));
  assert.equal(reports.length,2); assert.ok(reports[1].sequence>reports[0].sequence);
  assert.deepEqual(reports[0].capabilities,["html_media_v1"]);
  assert.deepEqual(reports[0].media,state("a"));
});
