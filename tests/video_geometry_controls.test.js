"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {VideoGeometryControls}=require("../src/ad_linux_tv/static/video_geometry_controls.js");

const id="a".repeat(32), commandId="AbCdEf0123456789";
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(request){
  const elements={mode:{value:"original"},mirror:{checked:false},apply:{},refresh:{},
    "tv-panel":{},status:{textContent:""}};
  const root={querySelector:selector=>elements[selector.match(/"([^"]+)"/)[1]],setAttribute(){}};
  const notices=[];let auth=0;
  const controls=new VideoGeometryControls(root,request,()=>{auth++;},(...args)=>notices.push(args));
  return {controls,elements,notices,auth:()=>auth};
}

test("TV panel opens only on explicit request; acceptance does not claim it appeared",async()=>{
  const requests=[];
  const h=harness(async(method,path,body)=>{
    requests.push([method,path,body]);
    return method==="GET" ? response(200,{available:false,media_id:null}) : response(202,{});
  });
  h.controls.activate();await settle();await h.controls.openTvPanel();
  assert.deepEqual(requests.at(-1),["POST","/api/tv-video-panel",{action:"open"}]);
  assert.deepEqual(h.notices,[["Запрос на открытие плашки на ТВ отправлен.",false]]);
});

test("TV panel failure and duplicate taps do not silently replay",async()=>{
  let count=0,finish;
  const h=harness(async(method)=>{
    if(method==="GET")return response(200,{available:false,media_id:null});
    count++;return new Promise(resolve=>{finish=resolve;});
  });
  h.controls.activate();await settle();
  const first=h.controls.openTvPanel();await settle();await h.controls.openTvPanel();
  assert.equal(count,1);finish(response(503,{}));await first;
  assert.deepEqual(h.notices,[["Не удалось открыть плашку на ТВ.",true]]);
  const old=h.controls.openTvPanel();await settle();h.controls.deactivate();
  finish(response(202,{}));await old;assert.equal(h.notices.length,1);
});

test("when no current video is found, choices remain visible but cannot apply to a future video",async()=>{
  const h=harness(async()=>response(200,{available:false,media_id:null}));
  h.controls.activate();await settle();
  assert.equal(h.elements.mode.disabled,false);assert.equal(h.elements.mirror.disabled,false);
  assert.equal(h.elements.apply.disabled,true);assert.equal(h.elements.refresh.disabled,false);
  assert.match(h.elements.status.textContent,/Видео не найдено/);
});

test("invalid or inconsistent media identifiers stay unavailable",async()=>{
  for(const state of [{available:true,media_id:[id]},{available:true,media_id:null},
    {available:false,media_id:id}]){
    const h=harness(async()=>response(200,state));h.controls.activate();await settle();
    assert.equal(h.elements.apply.disabled,true);
    assert.equal(h.elements.status.textContent,"Не удалось проверить видео.");
  }
});

test("only a completed matching bridge receipt reports success",async()=>{
  const requests=[];
  const h=harness(async(method,path,body)=>{
    requests.push([method,path,body]);
    if(method==="GET") return response(200,{available:true,media_id:id});
    if(body.action==="apply") return response(202,{id:commandId});
    return response(200,{id:commandId,outcome:"completed",reason:null});
  });
  h.controls.activate();await settle();
  h.elements.mode.value="4:3";h.elements.mirror.checked=true;
  await h.controls.apply();
  assert.deepEqual(requests.find(([, ,body])=>body?.action==="apply")[2],
    {action:"apply",media_id:id,mode:"4:3",mirror:true});
  assert.deepEqual(h.notices,[["Настройка отправлена плееру. Проверьте изображение.",false]]);
  assert.equal(h.elements.apply.disabled,false);
});

test("unsupported or uncertain receipts show an error without replaying",async()=>{
  for(const outcome of ["failed","uncertain"]){
    let writes=0;
    const h=harness(async(method,_path,body)=>{
      if(method==="GET")return response(200,{available:true,media_id:id});
      if(body.action==="apply"){writes++;return response(202,{id:commandId});}
      return response(200,{id:commandId,outcome,reason:"unsupported"});
    });
    h.controls.activate();await settle();await h.controls.apply();
    assert.equal(writes,1);assert.equal(h.notices.length,1);assert.equal(h.notices[0][1],true);
  }
});

test("changed target refuses application and late replies cannot revive a closed view",async()=>{
  let reads=0,writes=0;
  const h=harness(async(method)=>{
    if(method==="GET")return response(200,{available:true,media_id:++reads===1?id:"b".repeat(32)});
    writes++;return response(202,{id:commandId});
  });
  h.controls.activate();await settle();await h.controls.apply();
  assert.equal(writes,0);assert.equal(h.notices[0][1],true);
  let release;
  const h2=harness(()=>new Promise(resolve=>{release=resolve;}));
  h2.controls.activate();h2.controls.deactivate();release(response(200,{available:true,media_id:id}));
  await settle();assert.equal(h2.elements.apply.disabled,true);
});

test("a completed receipt for a replaced video is not reported as current success",async()=>{
  let reads=0;
  const h=harness(async(method,_path,body)=>{
    if(method==="GET")return response(200,{available:true,media_id:++reads<3?id:"b".repeat(32)});
    if(body.action==="apply")return response(202,{id:commandId});
    return response(200,{id:commandId,outcome:"completed",reason:null});
  });
  h.controls.activate();await settle();await h.controls.apply();
  assert.equal(h.notices.length,1);assert.equal(h.notices[0][1],true);
  assert.match(h.elements.status.textContent,/Видео сменилось/);
});

test("choosing a format without a current video never carries it to the next video",async()=>{
  let current=null,writes=0;
  const h=harness(async(method)=>{
    if(method!=="GET"){writes++;throw Error("must not apply automatically");}
    return response(200,{available:current!==null,media_id:current});
  });
  h.controls.activate();await settle();
  h.elements.mode.value="4:3";h.elements.mirror.checked=true;
  await h.controls.apply();assert.equal(writes,0);
  current=id;h.elements.refresh.onclick();await settle();
  assert.equal(h.elements.mode.value,"original");assert.equal(h.elements.mirror.checked,false);
  assert.equal(h.elements.apply.disabled,false);assert.equal(writes,0);
});

test("the same video retains the selected draft; a different one resets it",async()=>{
  let current=id;
  const h=harness(async()=>response(200,{available:true,media_id:current}));
  h.controls.activate();await settle();h.elements.mode.value="16:9";h.elements.mirror.checked=true;
  h.controls.deactivate();h.controls.activate();await settle();
  assert.equal(h.elements.mode.value,"16:9");assert.equal(h.elements.mirror.checked,true);
  current="b".repeat(32);h.controls.deactivate();h.controls.activate();await settle();
  assert.equal(h.elements.mode.value,"original");assert.equal(h.elements.mirror.checked,false);
});

test("duplicate taps cannot dispatch a second geometry request",async()=>{
  let writes=0,release;
  const h=harness(async(method,_path,body)=>{
    if(method==="GET")return response(200,{available:true,media_id:id});
    if(body.action==="apply"){writes++;return new Promise(resolve=>{release=resolve;});}
    return response(200,{id:commandId,outcome:"completed",reason:null});
  });
  h.controls.activate();await settle();
  const first=h.controls.apply();await settle();await h.controls.apply();
  assert.equal(writes,1);release(response(202,{id:commandId}));await first;
});

test("busy feedback is explicit only for the matching failed receipt and never retries",async()=>{
  for(const [receipt,specific] of [
    [{id:commandId,outcome:"failed",reason:"transition_busy"},true],
    [{id:"foreign-command-123",outcome:"failed",reason:"transition_busy"},false],
    [{id:commandId,outcome:"uncertain",reason:"transition_busy"},false],
    [{id:commandId,outcome:"completed",reason:"transition_busy"},false],
    [{id:commandId,outcome:"failed",reason:["transition_busy"]},false],
  ]) {
    let writes=0;
    const h=harness(async(method,_path,body)=>{
      if(method==="GET")return response(200,{available:true,media_id:id});
      if(body.action==="apply"){writes++;return response(202,{id:commandId});}
      return response(200,receipt);
    });
    h.controls.activate();await settle();await h.controls.apply();
    assert.equal(writes,1);assert.equal(h.notices.length,1);
    assert.equal(h.elements.status.textContent.includes("Переход видео ещё завершается"),specific);
    if(specific) assert.match(h.notices[0][0],/вручную.*Предыдущее изменение могло быть удалено/);
  }
});
