"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {TvShortcutControls} = require("../src/ad_linux_tv/static/tv_shortcut_controls.js");
const ok = (status, body) => ({status, ok:status >= 200 && status < 300, json:async()=>body});
const settle = () => new Promise(resolve=>setImmediate(resolve));
const id = "a".repeat(32);
function harness(request, {restartHint = true} = {}) {
  const elements = {};
  for (const name of ["ok", "volume_up", "volume_down", "video_panel", "magnifier", "fullscreen"])
    for (const suffix of ["key", "applied", "learn", "clear"]) elements[`${name}-${suffix}`] = {};
  for (const name of ["save", "cancel", "status"]) elements[name] = {};
  if (restartHint) elements.restart = {};
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
  assert.equal(h.elements.restart.hidden, false);
});

test("new controller remains compatible with an already-loaded older page", async()=>{
  const h=harness(async()=>ok(200,{tv_shortcuts:{},tv_shortcuts_restart_required:true}),{restartHint:false});
  await h.controls.activate();
  assert.match(h.elements.status.textContent,/перезапустите/);
  assert.equal(h.elements["ok-learn"].disabled,false);
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

test("navigation retains draft and CAS base while stopping a learner", async()=>{
  let release; const calls=[];
  const h=harness(async(method,path,body)=>{
    calls.push([method,path,body]);
    if(method==="GET") return ok(200,{tv_shortcuts:{ok:"XF86Launch1"},tv_shortcuts_restart_required:true});
    if(path==="/api/settings") return ok(200,{tv_shortcuts:body.value.assignments});
    if(body.action==="start") return new Promise(resolve=>{release=resolve;});
    return ok(200,{});
  });
  await h.controls.activate(); h.elements["ok-clear"].onclick();
  const learning=h.controls.learn("fullscreen"); await settle();
  h.controls.deactivate(); release(ok(202,{id})); await learning; await settle();
  assert.equal(calls.filter(([,path,body])=>path==="/api/tv-shortcut-learn" && body.action==="cancel").length,1);
  await h.controls.activate();
  assert.equal(h.elements["ok-key"].textContent,"Не назначено");
  assert.match(h.elements.status.textContent,/перезапуск/);
  await h.controls.save();
  assert.deepEqual(calls.at(-1)[2].value,{expected:{ok:"XF86Launch1"},assignments:{}});
});

test("pending save after navigation reconciles observed result without replay", async()=>{
  let state={ok:"XF86Launch1"}, finish; const writes=[];
  const h=harness(async(method,path,body)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:state,tv_shortcuts_restart_required:true});
    if(path==="/api/settings") { writes.push(body); return new Promise(resolve=>{finish=resolve;}); }
    return ok(200,{});
  });
  await h.controls.activate(); h.elements["ok-clear"].onclick();
  const pending=h.controls.save(); await settle();
  h.controls.deactivate(); await h.controls.activate();
  assert.equal(h.elements.save.disabled,true);
  assert.match(h.elements.status.textContent,/Проверяем результат/);
  state={}; finish(ok(200,{tv_shortcuts:state,tv_shortcuts_restart_required:true}));
  await pending; await settle();
  assert.equal(writes.length,1);
  assert.equal(h.elements["ok-key"].textContent,"Не назначено");
  assert.equal(h.controls.dirty,false);
  assert.match(h.elements.status.textContent,/совпадают с отправленными/);
  assert.match(h.elements.status.textContent,/перезапустите/);
});

test("pending save completed off-screen is reconciled without replay", async()=>{
  let state={ok:"XF86Launch1"}, finish; let writes=0;
  const h=harness(async(method,path)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:state});
    if(path==="/api/settings") { writes++; return new Promise(resolve=>{finish=resolve;}); }
    return ok(200,{});
  });
  await h.controls.activate(); h.elements["ok-clear"].onclick();
  const pending=h.controls.save(); await settle(); h.controls.deactivate();
  state={}; finish(ok(200,{tv_shortcuts:state})); await pending;
  await h.controls.activate();
  assert.equal(writes,1); assert.equal(h.controls.dirty,false);
  assert.match(h.elements.status.textContent,/совпадают с отправленными/);
  assert.doesNotMatch(h.elements.status.textContent,/другом устройстве/);
});

test("failed off-screen save retains the draft for explicit retry", async()=>{
  let finish,writes=0;
  const h=harness(async(method,path)=>{
    if(method==="GET") return ok(200,{tv_shortcuts:{ok:"XF86Launch1"}});
    if(path==="/api/settings") {writes++; return new Promise(resolve=>{finish=resolve;});}
    return ok(200,{});
  });
  await h.controls.activate(); h.elements["ok-clear"].onclick();
  const pending=h.controls.save(); await settle(); h.controls.deactivate();
  finish(ok(400,{})); await pending; await h.controls.activate();
  assert.equal(writes,1); assert.equal(h.controls.dirty,true);
  assert.equal(h.elements.save.disabled,false);
  assert.match(h.elements.status.textContent,/не подтверждено/);
});

test("disconnect reports discarded draft after reconnection", async()=>{
  const h=harness(async()=>ok(200,{tv_shortcuts:{ok:"XF86Launch1"}}));
  await h.controls.activate(); h.elements["ok-clear"].onclick(); h.controls.disconnect();
  await h.controls.activate();
  assert.match(h.elements.status.textContent,/черновик был сброшен/);
  assert.equal(h.elements["ok-key"].textContent,"XF86Launch1");
});

test("changed remote state after navigation fences stale draft", async()=>{
  let state={ok:"XF86Launch1"}, writes=0;
  const h=harness(async(method)=>{if(method==="GET") return ok(200,{tv_shortcuts:state}); writes++; return ok(200,{});});
  await h.controls.activate(); h.elements["ok-clear"].onclick(); h.controls.deactivate();
  state={fullscreen:"XF86Launch2"}; await h.controls.activate();
  assert.equal(h.elements.save.disabled,true); await h.controls.save(); assert.equal(writes,0);
  assert.match(h.elements.status.textContent,/другом устройстве/);
});
