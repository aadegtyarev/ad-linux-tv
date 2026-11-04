"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createTabController} = require("../extension/tabs.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");

const snapshot = {media_id:"a".repeat(32),playing:true,position:12,duration:900,can_seek:true};
const token="b".repeat(32);
const command = (id, overrides={}) => ({id,command:"video_geometry",service_id:null,
  media_id:snapshot.media_id,mode:"4:3",mirror:true,deadline:Date.now()+5000,...overrides});
async function setup() {
  const mock=browserMock([{id:1,windowId:1,url:LAUNCHER}]);
  const controller=createTabController(mock.api,mock.fetcher);
  await controller.restore();
  await controller.execute({id:"geometry-open",command:"open",service_id:"one"});
  mock.setScriptingResults([{frameId:5,result:snapshot}]);
  assert.equal((await controller.mediaSnapshot()).media_id,snapshot.media_id);
  return {mock,controller};
}

test("geometry is confined to the current owned frame and is never replayed",async()=>{
  const {mock,controller}=await setup();
  mock.setScriptingResults(options=>options.files ? [{frameId:5}] :
    options.func?.name==="playerMedia" ? [{frameId:5,result:snapshot}] :
    [{frameId:5,result:{outcome:"applied",token}}]);
  const item=command("geometry-success");
  assert.equal((await controller.execute(item)).outcome,"completed");
  assert.equal((await controller.execute(item)).outcome,"completed");
  const calls=mock.calls.filter(call=>call[0]==="script" && (call[1].files || call[1].func?.name==="invokeVideoGeometry"));
  assert.equal(calls.length,2);
  assert.deepEqual(calls[0][1].target.frameIds,[5]);
  assert.deepEqual(calls[0][1].files,["video_geometry.js"]);
  assert.deepEqual(calls[1][1].args,[snapshot.media_id,"4:3",true,item.deadline]);
  assert.ok(controller.capabilities().includes("video_geometry_v1"));
});

test("unsupported and malformed requests never become successful receipts",async()=>{
  const {mock,controller}=await setup();
  mock.setScriptingResults(options=>options.files ? [{frameId:5}] :
    options.func?.name==="playerMedia" ? [{frameId:5,result:snapshot}] :
    [{frameId:5,result:{outcome:"unsupported"}}]);
  assert.equal((await controller.execute(command("geometry-unsupported"))).reason,"unsupported");
  const before=mock.calls.filter(call=>call[0]==="script").length;
  assert.equal((await controller.execute(command("geometry-invalid",{mode:"url(https://example.invalid/)"}))).outcome,"failed");
  assert.equal((await controller.execute(command("geometry-expired",{deadline:Date.now()-1}))).reason,"no_media");
  assert.equal(mock.calls.filter(call=>call[0]==="script").length,before);
});

test("changing the active tab or media identity prevents injection",async()=>{
  const {mock,controller}=await setup();
  await mock.api.tabs.create({url:"https://unmanaged.example/",active:true});
  const before=mock.calls.filter(call=>call[0]==="script").length;
  assert.equal((await controller.execute(command("geometry-unmanaged"))).reason,"no_media");
  assert.equal(mock.calls.filter(call=>call[0]==="script").length,before);
});

test("new ambiguity before dispatch blocks the geometry injection",async()=>{
  const {mock,controller}=await setup();
  mock.setScriptingResults(options=>options.func?.name==="playerMedia" ?
    [{frameId:5,result:snapshot},{frameId:8,result:{ambiguous:true}}] :
    (()=>{throw Error("ambiguous player must not be changed");})());
  assert.equal((await controller.execute(command("geometry-ambiguous"))).reason,"no_media");
});

test("media changed after application cancels only that owned layer",async()=>{
  const {mock,controller}=await setup();let scans=0,cancelled=0;
  mock.setScriptingResults(options=>{
    if(options.func?.name==="playerMedia")return ++scans===1 ? [{frameId:5,result:snapshot}] : [];
    if(options.files)return [{frameId:5}];
    if(options.func?.name==="invokeVideoGeometry")return [{frameId:5,result:{outcome:"applied",token}}];
    if(options.func?.name==="cancelVideoGeometry"){
      cancelled++;assert.deepEqual(options.args,[snapshot.media_id,token]);
      return [{frameId:5,result:{outcome:"restored"}}];
    }
    throw Error("unexpected script");
  });
  assert.equal((await controller.execute(command("geometry-changed-after"))).reason,"no_media");
  assert.equal(cancelled,1);
});

test("later cross-frame ambiguity removes the previous geometry layer",async()=>{
  const {mock,controller}=await setup();let ambiguous=false,cancelled=0;
  mock.setScriptingResults(options=>{
    if(options.files)return [{frameId:5}];
    if(options.func?.name==="playerMedia")return ambiguous ?
      [{frameId:5,result:snapshot},{frameId:8,result:{ambiguous:true}}] : [{frameId:5,result:snapshot}];
    if(options.func?.name==="invokeVideoGeometry")return [{frameId:5,result:{outcome:"applied",token}}];
    if(options.func?.name==="cancelVideoGeometry"){
      cancelled++;assert.deepEqual(options.args,[snapshot.media_id,token]);
      return [{frameId:5,result:{outcome:"restored"}}];
    }
    throw Error("unexpected script");
  });
  assert.equal((await controller.execute(command("geometry-before-ambiguity"))).outcome,"completed");
  ambiguous=true;assert.equal(await controller.mediaSnapshot(),null);assert.equal(cancelled,1);
});

test("failed retirement is retried on the next report",async()=>{
  const {mock,controller}=await setup();let ambiguous=false,cancelled=0;
  mock.setScriptingResults(options=>{
    if(options.files)return [{frameId:5}];
    if(options.func?.name==="playerMedia")return ambiguous ?
      [{frameId:5,result:snapshot},{frameId:8,result:{ambiguous:true}}] : [{frameId:5,result:snapshot}];
    if(options.func?.name==="invokeVideoGeometry")return [{frameId:5,result:{outcome:"applied",token}}];
    if(options.func?.name==="cancelVideoGeometry")return [{frameId:5,result:{outcome:++cancelled===1?"uncertain":"restored"}}];
    throw Error("unexpected script");
  });
  assert.equal((await controller.execute(command("geometry-before-retry"))).outcome,"completed");
  const getTab=mock.api.tabs.get;mock.api.tabs.get=async()=>{throw Error("transient tab lookup failure");};
  ambiguous=true;assert.equal(await controller.mediaSnapshot(),null);
  mock.api.tabs.get=getTab;ambiguous=false;
  assert.equal((await controller.mediaSnapshot()).media_id,snapshot.media_id);
  assert.equal(cancelled,2);
});

test("a slow retirement cannot publish an older media snapshot",async()=>{
  const {mock,controller}=await setup();let current=snapshot,release;
  const second={...snapshot,media_id:"c".repeat(32)},third={...snapshot,media_id:"d".repeat(32)};
  mock.setScriptingResults(options=>{
    if(options.files)return [{frameId:5}];
    if(options.func?.name==="playerMedia")return [{frameId:5,result:current}];
    if(options.func?.name==="invokeVideoGeometry")return [{frameId:5,result:{outcome:"applied",token}}];
    if(options.func?.name==="cancelVideoGeometry")return new Promise(resolve=>{release=resolve;});
    throw Error("unexpected script");
  });
  assert.equal((await controller.execute(command("geometry-before-overlap"))).outcome,"completed");
  current=second;const older=controller.mediaSnapshot();
  await new Promise(resolve=>setImmediate(resolve));assert.equal(typeof release,"function");
  current=third;assert.equal((await controller.mediaSnapshot()).media_id,third.media_id);
  release([{frameId:5,result:{outcome:"restored"}}]);assert.equal(await older,null);
  const next=command("geometry-after-overlap",{media_id:third.media_id});
  assert.equal((await controller.execute(next)).outcome,"completed");
});

test("a timed-out injection is uncertain and is not dispatched after the deadline",async()=>{
  const {mock,controller}=await setup();let finish;let count=0;
  mock.setScriptingResults(options=>{
    if(options.func?.name==="playerMedia")return [{frameId:5,result:snapshot}];
    if(options.files){count++;return new Promise(resolve=>{finish=resolve;});}
    throw Error("expired request must not execute geometry");
  });
  const item=command("geometry-timeout",{deadline:Date.now()+40});
  assert.equal((await controller.execute(item)).outcome,"uncertain");
  assert.equal((await controller.execute(item)).outcome,"uncertain");
  finish([{frameId:5}]);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(count,1);
  assert.equal((await controller.execute(item)).outcome,"uncertain");
});
