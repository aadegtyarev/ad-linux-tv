"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {VideoGeometryControls}=require("../src/ad_linux_tv/static/video_geometry_controls.js");

const id="a".repeat(32), commandId="AbCdEf0123456789";
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(request){
  const elements={mode:{value:"original"},mirror:{checked:false},apply:{},status:{textContent:""}};
  const root={querySelector:selector=>elements[selector.match(/"([^"]+)"/)[1]],setAttribute(){}};
  const notices=[];let auth=0;
  const controls=new VideoGeometryControls(root,request,()=>{auth++;},(...args)=>notices.push(args));
  return {controls,elements,notices,auth:()=>auth};
}

test("an old bridge or no video keeps controls unavailable",async()=>{
  const h=harness(async()=>response(200,{available:false,media_id:null}));
  h.controls.activate();await settle();
  assert.equal(h.elements.apply.disabled,true);
  assert.match(h.elements.status.textContent,/Нет доступного видео/);
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
  assert.deepEqual(h.notices,[["Настройка видео применена.",false]]);
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
  assert.match(h.elements.status.textContent,/не подтверждён/);
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
