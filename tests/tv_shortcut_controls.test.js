"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {TvShortcutControls} = require("../src/ad_linux_tv/static/tv_shortcut_controls.js");
const ok = (status, body) => ({status, ok:status >= 200 && status < 300, json:async()=>body});
const settle = () => new Promise(resolve=>setImmediate(resolve));
const id = "a".repeat(32);
function harness(request) {
  const elements = {};
  for (const name of ["ok", "volume_up", "volume_down", "video_panel", "magnifier", "fullscreen"])
    for (const suffix of ["key", "applied", "learn", "clear"]) elements[`${name}-${suffix}`] = {};
  for (const name of ["save", "cancel", "status"]) elements[name] = {};
  const root = {querySelector:s=>elements[s.match(/"([^"]+)"/)[1]]};
  let saved = 0, auth = 0;
  const controls = new TvShortcutControls(root, request, ()=>auth++, ()=>saved++, async()=>{});
  return {controls, elements, saved:()=>saved, auth:()=>auth};
}

test("learning is a draft only until explicitly saved", async()=>{
  const calls=[];
  const h=harness(async(method,path,body)=>{
    calls.push([method,path,body]);
    if(method==="GET") return ok(200,{tv_shortcuts:{},tv_shortcuts_restart_required:false});
    if(path==="/api/settings") return ok(200,{tv_shortcuts:body.value.assignments,tv_shortcuts_restart_required:true});
    if(body.action==="start") return ok(202,{id});
    if(body.action==="result") return ok(200,{state:"ready",key:"XF86Launch1"});
    return ok(200,{});
  });
  await h.controls.activate(); await h.controls.learn("video_panel");
  assert.equal(h.elements["video_panel-key"].textContent,"XF86Launch1");
  assert.equal(calls.filter(([,path])=>path==="/api/settings").length,1);
  await h.controls.save();
  assert.deepEqual(calls.at(-1),["POST","/api/settings",{setting:"tv_shortcuts",value:{expected:{},assignments:{video_panel:"XF86Launch1"}}}]);
  assert.equal(h.saved(),1); assert.match(h.elements.status.textContent,/перезапустите/);
});

test("all six distinct choices remain drafts until one explicit save", async()=>{
  const actions=["ok","volume_up","volume_down","video_panel","magnifier","fullscreen"];
  let key="",writes=0;
  const h=harness(async(method,path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:{}});
    if(path==="/api/settings"){writes++;return ok(200,{tv_shortcuts:body.value.assignments,tv_shortcuts_restart_required:true});}
    if(body.action==="start") return ok(202,{id});
    return ok(200,{state:"ready",key});
  });
  await h.controls.activate();
  for(let i=0;i<actions.length;i++){key=`XF86Launch${i+1}`;await h.controls.learn(actions[i]);}
  assert.equal(writes,0);await h.controls.save();assert.equal(writes,1);
  for(let i=0;i<actions.length;i++)assert.equal(h.elements[`${actions[i]}-key`].textContent,`XF86Launch${i+1}`);
});

test("clearing one of six choices retains the other five until explicitly saved", async()=>{
  const saved={ok:"XF86Launch1",volume_up:"XF86Launch2",volume_down:"XF86Launch3",video_panel:"XF86Launch4",magnifier:"XF86Launch5",fullscreen:"XF86Launch6"};
  let write=null;
  const h=harness(async(method,_path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:saved,tv_shortcuts_applied:saved});
    write=body; return ok(200,{tv_shortcuts:body.value.assignments,tv_shortcuts_applied:saved,tv_shortcuts_restart_required:true});
  });
  await h.controls.activate();h.elements["volume_up-clear"].onclick();
  assert.equal(write,null);assert.equal(h.elements["volume_up-key"].textContent,"Не назначено");
  assert.equal(h.elements["volume_up-applied"].textContent,"Сейчас: XF86Launch2");
  await h.controls.save();
  assert.deepEqual(write.value.expected,saved);
  assert.equal(Object.keys(write.value.assignments).length,5);
  assert.equal(write.value.assignments.volume_up,undefined);
  assert.equal(write.value.assignments.ok,"XF86Launch1");
});

test("a saved replacement still displays the key applied before restart", async()=>{
  const old={video_panel:"XF86Launch1"};
  const h=harness(async(method,path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:old,tv_shortcuts_applied:old});
    if(path==="/api/settings") return ok(200,{tv_shortcuts:body.value.assignments,tv_shortcuts_applied:old,tv_shortcuts_restart_required:true});
    if(body.action==="start") return ok(202,{id});
    return ok(200,{state:"ready",key:"XF86Launch2"});
  });
  await h.controls.activate(); await h.controls.learn("video_panel"); await h.controls.save();
  assert.equal(h.elements["video_panel-key"].textContent,"XF86Launch2");
  assert.equal(h.elements["video_panel-applied"].textContent,"Сейчас: XF86Launch1");
  assert.match(h.elements.status.textContent,/перезапустите/);
});

test("duplicate choice and unsupported key do not overwrite drafts or save", async()=>{
  let candidate="XF86Launch1", writes=0;
  const h=harness(async(method,path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:{video_panel:"XF86Launch1"}});
    if(path==="/api/settings"){writes++;return ok(200,{});}
    if(body.action==="start") return ok(202,{id});
    if(body.action==="result") return ok(200,{state:"ready",key:candidate});
    return ok(200,{});
  });
  await h.controls.activate(); await h.controls.learn("magnifier");
  assert.match(h.elements.status.textContent,/уже выбрана/);
  assert.equal(h.elements["magnifier-key"].textContent,"Не назначено");
  candidate="Return"; await h.controls.learn("magnifier");
  assert.match(h.elements.status.textContent,/недоступна/); assert.equal(writes,0);
});

test("an extra OK key cannot be reused for volume or a video action", async()=>{
  const h=harness(async(method,_path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:{ok:"XF86Launch1"}});
    if(body.action==="start") return ok(202,{id});
    return ok(200,{state:"ready",key:"XF86Launch1"});
  });
  await h.controls.activate();
  await h.controls.learn("volume_up");
  assert.match(h.elements.status.textContent,/уже выбрана/);
  await h.controls.learn("video_panel");
  assert.match(h.elements.status.textContent,/уже выбрана/);
  assert.equal(h.elements["volume_up-key"].textContent,"Не назначено");
  assert.equal(h.elements["video_panel-key"].textContent,"Не назначено");
});

test("a stale draft keeps its original compare-and-swap base", async()=>{
  let external={}, attempted=null;
  const h=harness(async(method,path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:external});
    if(path==="/api/settings"){attempted=body;return ok(400,{});}
    if(body.action==="start") return ok(202,{id});
    return ok(200,{state:"ready",key:"XF86Launch1"});
  });
  await h.controls.activate(); await h.controls.learn("video_panel");
  external={fullscreen:"XF86Launch2"};
  await h.controls.save();
  assert.deepEqual(attempted.value,{expected:{},assignments:{video_panel:"XF86Launch1"}});
  assert.match(h.elements.status.textContent,/другом устройстве/);
  assert.equal(h.elements["video_panel-key"].textContent,"XF86Launch1");
});

test("cancellation on the TV is reported without assigning a key", async()=>{
  const h=harness(async(method,_path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:{}});
    if(body.action==="start") return ok(202,{id});
    return ok(200,{state:"cancelled"});
  });
  await h.controls.activate(); await h.controls.learn("video_panel");
  assert.equal(h.elements["video_panel-key"].textContent,"Не назначено");
  assert.match(h.elements.status.textContent,/отменён на ТВ/);
});

test("cancel before late admission retires the new operation without saving", async()=>{
  let finish; const calls=[];
  const h=harness(async(method,path,body)=>{
    calls.push([method,path,body]);
    if(method==="GET") return ok(200,{tv_shortcuts:{}});
    if(body.action==="start") return new Promise(resolve=>{finish=resolve;});
    return ok(200,{});
  });
  await h.controls.activate(); const pending=h.controls.learn("fullscreen"); await settle();
  h.controls.cancel(); finish(ok(202,{id})); await pending; await settle();
  assert.deepEqual(calls.at(-1),["POST","/api/tv-shortcut-learn",{action:"cancel",id}]);
  assert.equal(h.elements["fullscreen-key"].textContent,"Не назначено");
});

test("lost socket never reconnects just to cancel a stale learner", async()=>{
  let finish; const calls=[];
  const h=harness(async(method,path,body)=>{
    calls.push([method,path,body]);
    if(method==="GET") return ok(200,{tv_shortcuts:{}});
    if(body.action==="start") return new Promise(resolve=>{finish=resolve;});
    return ok(200,{});
  });
  await h.controls.activate(); const pending=h.controls.learn("fullscreen"); await settle();
  h.controls.disconnect(); finish(ok(202,{id})); await pending; await settle();
  assert.equal(calls.filter(([,path,body])=>path==="/api/tv-shortcut-learn" && body.action==="cancel").length,0);
});

test("reconciliation after a disconnect reloads state without replaying learning", async()=>{
  const calls=[];
  const h=harness(async(method,path,body)=>{
    calls.push([method,path,body]);
    return ok(200,{tv_shortcuts:{}});
  });
  await h.controls.activate();
  h.controls.disconnect();
  assert.equal(h.elements["video_panel-learn"].disabled,true);
  await h.controls.activate();
  assert.equal(h.elements["video_panel-learn"].disabled,false);
  assert.deepEqual(calls.map(([method,path])=>[method,path]),[["GET","/api/settings"],["GET","/api/settings"]]);
});

test("unavailable or older server cannot enable learning", async()=>{
  const h=harness(async()=>ok(200,{})); await h.controls.activate();
  assert.equal(h.elements["video_panel-learn"].disabled,true);
  assert.match(h.elements.status.textContent,/недоступно/);
});
