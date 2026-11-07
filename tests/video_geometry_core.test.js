"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {videoGeometryScale,createVideoGeometryController,createVideoGeometryEnvironment,createVideoGeometryCommand}=require("../extension/video_geometry.js");

class Target {
  constructor(){this.events=new Map();}
  addEventListener(name,fn){if(!this.events.has(name))this.events.set(name,new Set());this.events.get(name).add(fn);}
  removeEventListener(name,fn){this.events.get(name)?.delete(fn);}
  fire(name){for(const fn of this.events.get(name)||[])fn();}
}
function makeHarness(options={}) {
  const page=new Target(),view=new Target();
  view.innerWidth=1366;view.innerHeight=768;
  page.hidden=false;page.fullscreenElement=null;
  page.body={parentElement:null};page.documentElement={parentElement:null};
  const parent={parentElement:page.body};
  page.body.parentElement=page.documentElement;
  let current="one",layer=null,observerCallback,timerCallback,records=[],serial=0,transition="none";
  let removeAttributeThrows=Boolean(options.attributeRemoveThrows),removeThrows=Boolean(options.removeThrows);
  const base=()=>({display:"block",visibility:"visible",opacity:"1",clipPath:"none",scale:"none",rotate:"none",translate:"none",transform:"none",overflowX:"visible",overflowY:"visible",borderLeftWidth:"0px",borderRightWidth:"0px",borderTopWidth:"0px",borderBottomWidth:"0px",paddingLeft:"0px",paddingRight:"0px",paddingTop:"0px",paddingBottom:"0px",objectFit:"contain"});
  const site=new Map(),attribute=new Map(),video=new Target();
  Object.assign(video,{tagName:"VIDEO",ownerDocument:page,isConnected:true,currentSrc:"https://example.invalid/one",videoWidth:320,videoHeight:240,controls:false,mediaKeys:null,textTracks:[],parentElement:parent,getRootNode:()=>page});
  video.hasAttribute=name=>attribute.has(name);
  video.getAttribute=name=>attribute.has(name)?attribute.get(name):null;
  video.setAttribute=(name,value)=>{attribute.set(name,value);};
  video.removeAttribute=name=>{if(removeAttributeThrows)throw Error("attribute removal");attribute.delete(name);};
  const parentStyle=base(),bodyStyle=base(),videoStyle=base();
  const layerTransform=()=>{
    if(!layer?.isConnected)return null;
    const attr=layer.textContent.match(/video\[([^\]]+)\]/)?.[1];
    if(!attribute.has(attr))return null;
    const match=layer.textContent.match(/transform:scale\(([^,]+),([^\)]+)\)/);
    return match ? [Number(match[1]),Number(match[2])] : null;
  };
  const effective=()=>site.get("transform")?.important ? site.get("transform").matrix : layerTransform() || site.get("transform")?.matrix || [1,1];
  video.getBoundingClientRect=()=>{const [x,y]=effective();const b=options.box || {left:0,top:0,width:320,height:240};
    const w=b.width*Math.abs(x),h=b.height*Math.abs(y),cx=b.left+b.width/2,cy=b.top+b.height/2;
    return {left:cx-w/2,right:cx+w/2,top:cy-h/2,bottom:cy+h/2,width:w,height:h};};
  page.createElement=name=>{
    assert.equal(name,"style");
    return {textContent:"",isConnected:false,remove(){if(removeThrows)throw Error("remove");this.isConnected=false;}};
  };
  page.head={appendChild(node){layer=node;node.isConnected=true;if(options.appendThrows)throw Error("append");}};
  const styleOf=element=>{
    if(element===parent)return parentStyle;
    if(element===page.body)return bodyStyle;
    if(element!==video)return base();
    const s={...videoStyle}, [x,y]=effective();
    s.transform=(x===1 && y===1 && !layerTransform() && !site.has("transform")) ? "none" : `matrix(${x}, ${options.shear?.b || 0}, ${options.shear?.c || 0}, ${y}, 0, 0)`;
    if(layerTransform() && layer.textContent.includes("object-fit:fill") && !site.get("object-fit")?.important)s.objectFit="fill";
    else if(site.has("object-fit"))s.objectFit=site.get("object-fit").value;
    return s;
  };
  const matrixOf=value=>{
    if(value==="none")return {a:1,b:0,c:0,d:1,e:0,f:0};
    const n=value.match(/matrix\(([^)]+)\)/)[1].split(",").map(Number);
    return {a:n[0],b:n[1],c:n[2],d:n[3],e:n[4],f:n[5]};
  };
  const env={page,view,styleOf,matrixOf,transformTransitions:element=>element===video ? transition : "none",afterFrame:options.afterFrame||(()=>Promise.resolve()),randomToken:()=>String(++serial).padStart(32,"0"),
    observe:(_video,callback)=>{if(options.observeThrows)throw Error("observe");observerCallback=callback;return {takeRecords:()=>records.splice(0),disconnect(){}};},
    setTimer:callback=>{timerCallback=callback;return 1;},clearTimer:()=>{}};
  const controller=createVideoGeometryController(env);
  return {page,view,parent,parentStyle,bodyStyle,video,videoStyle,site,attribute,controller,
    isCurrent:(_v,id)=>current===id,setCurrent:id=>{current=id;},setTransition:value=>{transition=value;},effective,
    active:()=>Boolean(layer?.isConnected),
    notify:record=>observerCallback(record),queue:record=>records.push(record),
    tick:()=>timerCallback(),
    allowCleanup:()=>{removeThrows=false;removeAttributeThrows=false;}};
}

test("injected command uses the current opaque media identity and bounded fields",async()=>{
  const id="a".repeat(32), video={currentSrc:"https://example.invalid/one",duration:100};
  const record={id,fingerprint:`${video.currentSrc}\n${video.duration}`};
  const page={__adLinuxTvTiming:{items:new WeakMap([[video,record]]),last:video}};
  let calls=0, stillCurrent;
  const factory=()=>({apply:async(target,identity,current,mode,mirror)=>{
    calls++;stillCurrent=current;assert.equal(target,video);assert.equal(identity,id);assert.equal(current(video,id),true);
    assert.equal(mode,"4:3");assert.equal(mirror,true);return {outcome:"applied"};
  }});
  const command=createVideoGeometryCommand(page,{},factory),deadline=Date.now()+5000;
  assert.equal((await command(id,"4:3",true,deadline)).outcome,"applied");
  assert.equal((await command("b".repeat(32),"4:3",true,deadline)).outcome,"unsupported");
  assert.equal((await command(id,"arbitrary-css",true,deadline)).outcome,"unsupported");
  assert.equal((await command(id,"4:3",1,deadline)).outcome,"unsupported");
  assert.equal((await command(id,"4:3",true,Date.now()-1)).outcome,"unsupported");
  page.__adLinuxTvTiming.last=null;
  assert.equal(stillCurrent(video,id),false);
  assert.equal((await command(id,"4:3",true,deadline)).outcome,"unsupported");
  assert.equal(calls,1);
});

test("expired asynchronous application is reset, not reported as successful",async()=>{
  const id="a".repeat(32), video={currentSrc:"https://example.invalid/one",duration:100};
  const page={__adLinuxTvTiming:{items:new WeakMap([[video,{id,fingerprint:`${video.currentSrc}\n${video.duration}`}]]),last:video}};
  let finish, reset=0;
  const factory=()=>({apply:()=>new Promise(resolve=>{finish=resolve;}),
    cancel:(identity,token)=>{reset++;assert.equal(identity,id);assert.equal(token,"c".repeat(32));}});
  const now=Date.now;let clock=1000;Date.now=()=>clock;
  try {
    const command=createVideoGeometryCommand(page,{},factory),pending=command(id,"4:3",true,2000);
    clock=2001;finish({outcome:"applied",token:"c".repeat(32)});
    assert.equal((await pending).outcome,"uncertain");assert.equal(reset,1);
  } finally {Date.now=now;}
});

test("native observation is limited to the video and relevant attributes",()=>{
  let observed;
  class Observer {constructor(callback){this.callback=callback;} observe(target,options){observed={target,options};}}
  const video={}, env=createVideoGeometryEnvironment({}, {MutationObserver:Observer});
  env.observe(video,()=>{},"data-ad-tv-geometry-example");
  assert.deepEqual(observed,{target:video,options:{attributes:true,
    attributeFilter:["style","class","src","data-ad-tv-geometry-example"]}});
});

test("native environment bounds fallback document scans to once per second",()=>{
  let delay,callback,cleared;
  const view={setInterval:(fn,ms)=>{callback=fn;delay=ms;return 17;},clearInterval:id=>{cleared=id;}};
  const env=createVideoGeometryEnvironment({},view);
  const tick=()=>{};
  assert.equal(env.setTimer(tick),17);
  assert.equal(callback,tick);
  assert.equal(delay,1000);
  env.clearTimer(17);
  assert.equal(cleared,17);
});

test("ratios are bounded and horizontal mirror is independent",()=>{
  assert.deepEqual(videoGeometryScale(320,240,16/9,true),{x:-1,y:0.75});
  assert.deepEqual(videoGeometryScale(320,240,4/3,false),{x:1,y:1});
  assert.throws(()=>videoGeometryScale(0,1,1,false));
});

test("temporary layer never changes newer or identical site inline styles",async()=>{
  const h=makeHarness();
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(h.site.size,0);
  const newer={matrix:[-1,.75],important:true};h.site.set("transform",newer);
  h.notify({attributeName:"style"});
  assert.equal(h.active(),false);assert.equal(h.site.get("transform"),newer);
  assert.equal(h.attribute.size,0);
});

test("stale target and stale reset cannot destroy a newer active session",async()=>{
  const h=makeHarness();h.setCurrent("two");
  assert.equal((await h.controller.apply(h.video,"two",h.isCurrent,"4:3",false)).outcome,"applied");
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false)).outcome,"unsupported");
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"unsupported");
  assert.equal(h.active(),true);assert.equal((await h.controller.reset(h.video,"two",h.isCurrent)).outcome,"restored");
  assert.equal(h.active(),false);
});

for(const change of [
  h=>{h.video.controls=true;},h=>{h.video.textTracks=[{mode:"showing"}];},
  h=>{h.video.mediaKeys={};},h=>{h.page.hidden=true;},
  h=>{h.page.fullscreenElement=h.video;},h=>{h.video.currentSrc="https://example.invalid/two";},
  h=>{h.setCurrent("two");},h=>{h.video.isConnected=false;},
]) test("late eligibility or identity loss removes only the owned layer",async()=>{
  const h=makeHarness();assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false)).outcome,"applied");
  const site={matrix:[.8,1],important:true};h.site.set("transform",site);change(h);h.tick();
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);assert.equal(h.site.get("transform"),site);
});

test("fullscreen container is eligible but fullscreen video and changed fullscreen are not",async()=>{
  const h=makeHarness();h.page.fullscreenElement=h.video;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",false)).outcome,"unsupported");
  h.page.fullscreenElement=h.parent;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",false)).outcome,"applied");
  h.page.fullscreenElement=null;h.page.fire("fullscreenchange");assert.equal(h.active(),false);
});

test("clipping, padding, transform and inaccessible roots fail closed",async()=>{
  for(const change of [h=>h.parentStyle.overflowX="hidden",h=>h.parentStyle.clipPath="inset(1px)",
    h=>h.videoStyle.paddingTop="2px",h=>h.parentStyle.clip="rect(0px, 200px, 200px, 0px)",
    h=>h.videoStyle.clip="rect(0px, 200px, 200px, 0px)",h=>h.parentStyle.transform="matrix(2,0,0,2,0,0)",
    h=>h.video.getRootNode=()=>({}),h=>h.videoStyle.scale="2",h=>h.parentStyle.maskImage="url(#mask)",
    h=>h.parentStyle.borderTopLeftRadius="5px"]){
    const h=makeHarness();change(h);
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"unsupported");
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  }
});

test("an accessible embedded frame can change only its selected video",async()=>{
  const h=makeHarness();h.view.top={};
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("open shadow player uses its own style layer and supports fullscreen hosts",async()=>{
  const h=makeHarness(),root={mode:"open",host:h.page.body};let appended=false;
  root.appendChild=node=>{appended=true;h.page.head.appendChild(node);};
  h.video.getRootNode=()=>root;h.parent.parentElement=null;h.parent.getRootNode=()=>root;
  h.page.fullscreenElement=h.page.body;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(appended,true);assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
});

test("an accessible closed shadow root can use its own style layer",async()=>{
  const h=makeHarness(),root={mode:"closed",host:h.page.body};let appended=false;
  root.appendChild=node=>{appended=true;h.page.head.appendChild(node);};
  h.video.getRootNode=()=>root;h.parent.parentElement=null;h.parent.getRootNode=()=>root;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(appended,true);assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
});

test("a fullscreen player fits a video inside overflow hidden",async()=>{
  const h=makeHarness();
  h.parentStyle.overflowX="hidden";h.parentStyle.overflowY="hidden";
  h.parent.getBoundingClientRect=()=>({left:0,top:0,right:320,bottom:240,width:320,height:240});
  h.page.fullscreenElement=h.parent;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  h.parent.getBoundingClientRect=()=>({left:20,top:0,right:300,bottom:240,width:280,height:240});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
});

test("author inline important conflict is detected and player style is not overwritten",async()=>{
  const h=makeHarness();const site={matrix:[.5,1],important:true};h.site.set("transform",site);
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"unsupported");
  assert.equal(h.active(),false);assert.equal(h.site.get("transform"),site);
});

test("a late cancellation cannot remove a newer geometry layer",async()=>{
  const h=makeHarness();
  const first=await h.controller.apply(h.video,"one",h.isCurrent,"4:3",false);
  const second=await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  assert.equal(h.controller.cancel("one",first.token).outcome,"unchanged");
  assert.equal(h.active(),true);
  assert.equal(h.controller.cancel("one",second.token).outcome,"restored");
  assert.equal(h.active(),false);
});

test("setup and teardown exceptions are reported, while remaining cleanup still runs",async()=>{
  for(const option of [{appendThrows:true},{observeThrows:true}]){
    const h=makeHarness(option);
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true),
      {outcome:"unsupported",reason:"geometry_post_write_exception"});
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  }
  const h=makeHarness({removeThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"uncertain");
  assert.equal(h.attribute.size,0); // inert even if node removal failed
});

test("simultaneous failed removals remain tracked and can be retried",async()=>{
  const h=makeHarness({removeThrows:true,attributeRemoveThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"uncertain");
  assert.equal(h.active(),true);assert.equal(h.attribute.size,1);
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"uncertain");
  h.allowCleanup();assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("failed invalidation retries cleanup after the target becomes ineligible",async()=>{
  const h=makeHarness({removeThrows:true,attributeRemoveThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  h.video.isConnected=false;h.tick();
  assert.equal(h.active(),true);assert.equal(h.attribute.size,1);
  h.allowCleanup();h.tick();
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("pending identical marker writes are not removed during cleanup",async()=>{
  const h=makeHarness();assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  const marker=[...h.attribute.keys()][0];h.queue({attributeName:marker});
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.has(marker),true);
});

test("loadstart on reused video retires the layer and preserves new site styles",async()=>{
  const h=makeHarness();assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",false)).outcome,"applied");
  const site={matrix:[.9,1],important:true};h.site.set("transform",site);h.video.currentSrc="https://example.invalid/two";h.video.fire("loadstart");
  assert.equal(h.active(),false);assert.equal(h.site.get("transform"),site);
});

test("the temporary geometry ends when the current playback finishes",async()=>{
  const h=makeHarness();
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  h.video.fire("ended");
  assert.equal(h.active(),false);
  assert.equal(h.attribute.size,0);
});

test("no success before frame verification and source change while waiting fails closed",async()=>{
  let resolve;const h=makeHarness({afterFrame:()=>new Promise(done=>{resolve=done;})});
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);h.video.currentSrc="https://example.invalid/two";resolve();
  assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
});

test("a newer request fences the result of an older in-flight request",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(done=>frames.push(done))});
  const old=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
  const newer=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);
  frames[0]();assert.equal((await old).outcome,"unsupported");assert.equal(h.active(),true);
  frames[1]();assert.equal((await newer).outcome,"applied");
});


test("identity matrices are accepted, translations and 3D matrices rejected",async()=>{
  for (const [transform,expected] of [["matrix(1, 0, 0, 1, 0, 0)","applied"],
    ["matrix(1, 0, 0, 1, 1, 0)","unsupported"],
    ["matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)","unsupported"]]) {
    const h=makeHarness();h.parentStyle.transform=transform;
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,expected);
  }
});

test("preparation waits for a transition and checks identity again before writing",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.setTransition("running");
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  assert.equal(h.active(),false);
  h.video.currentSrc="https://example.invalid/changed";frames.shift()();
  assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
});

test("reset during preparation invalidates pending work without a layer",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.setTransition("running");const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  const reset=h.controller.reset(h.video,"one",h.isCurrent);
  h.setTransition("none");frames.shift()();
  assert.equal((await reset).outcome,"unchanged");
  assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
});

test("finite busy preparation reports its reason and never writes",async()=>{
  const now=Date.now;let clock=1000;Date.now=()=>clock;
  try {
    const h=makeHarness({afterFrame:()=>{clock=1701;return Promise.resolve();}});
    h.setTransition("running");
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true,3000),
      {outcome:"unsupported",reason:"transition_busy"});
    assert.equal(h.active(),false);
  } finally {Date.now=now;}
});

test("replacement removes only its own layer and a stale completion cannot remove a newer layer",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  const first=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);frames.shift()();
  assert.equal((await first).outcome,"applied");
  h.setTransition("running");const replacement=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  h.setTransition("none");const newer=h.controller.apply(h.video,"one",h.isCurrent,"4:3",false);
  frames.shift()();assert.equal((await replacement).outcome,"unsupported");assert.equal(h.active(),true);
  frames.shift()();assert.equal((await newer).outcome,"applied");assert.equal(h.active(),true);
});

test("post-apply transition must end before success",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.active(),true);h.setTransition("none");frames.shift()();
  assert.equal((await pending).outcome,"applied");
});

test("transient clipping during a transform transition waits for strict final geometry",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.parentStyle.overflowX="hidden";
  h.parent.getBoundingClientRect=()=>({left:100,right:420,top:0,bottom:240});
  const rect=h.video.getBoundingClientRect;let overshoot=false;
  h.video.getBoundingClientRect=()=>{const box=rect();return {...box,left:box.left+100-(overshoot?5:0),right:box.right+100+(overshoot?5:0)};};
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
  overshoot=true;h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.active(),true);assert.equal(frames.length,1);
  overshoot=false;h.setTransition("none");frames.shift()();
  assert.equal((await pending).outcome,"applied");
});

test("preparation waits through clipping only while the transition is running",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.parentStyle.overflowX="hidden";
  h.parent.getBoundingClientRect=()=>({left:100,right:420,top:0,bottom:240});
  const rect=h.video.getBoundingClientRect;let overshoot=true;
  h.video.getBoundingClientRect=()=>{const box=rect();return {...box,left:box.left+100-(overshoot?5:0),right:box.right+100+(overshoot?5:0)};};
  h.setTransition("running");
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
  assert.equal(h.active(),false);assert.equal(frames.length,1);
  overshoot=false;h.setTransition("none");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
  frames.shift()();assert.equal((await pending).outcome,"applied");
});

test("clipping while waiting never bypasses final geometry or safety guards",async()=>{
  for (const kind of ["final","source","unsafe","ancestor","viewport","ownership"]) {
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    h.parentStyle.overflowX="hidden";
    h.parent.getBoundingClientRect=()=>({left:100,right:420,top:0,bottom:240});
    const rect=h.video.getBoundingClientRect;let overshoot=false;
    h.video.getBoundingClientRect=()=>{const box=rect();return {...box,left:box.left+100-(overshoot?5:0),right:box.right+100+(overshoot?5:0)};};
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
    overshoot=true;h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
    assert.equal(h.active(),true);
    if(kind==="final") h.setTransition("none");
    if(kind==="source") h.video.currentSrc="https://example.invalid/changed";
    if(kind==="unsafe") h.setTransition("unsafe");
    if(kind==="ancestor") h.parentStyle.opacity="0";
    if(kind==="viewport") {h.view.innerWidth=10;h.setTransition("none");}
    if(kind==="ownership") h.attribute.clear();
    frames.shift()();const result=await pending;
    assert.equal(result.outcome,"unsupported",kind);
    if(kind==="final") assert.equal(result.reason,"geometry_clipping");
    assert.equal(h.active(),false,kind);assert.equal(h.attribute.size,0,kind);
  }
});

function clippingTransitionHarness() {
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.parentStyle.overflowX="hidden";h.bodyStyle.overflowX="hidden";
  h.parent.getBoundingClientRect=()=>({left:100,right:420,top:0,bottom:240});
  h.page.body.getBoundingClientRect=()=>({left:100,right:420,top:0,bottom:240});
  const rect=h.video.getBoundingClientRect;let overshoot=false;
  h.video.getBoundingClientRect=()=>{const box=rect();return {...box,left:box.left+100-(overshoot?5:0),right:box.right+100+(overshoot?5:0)};};
  return {h,frames,overshoot:value=>{overshoot=value;}};
}

test("temporary clipping checks every ancestor and strict final clipping",async()=>{
  for (const kind of ["settled","upper-style","upper-final-clipping"]) {
    const fixture=clippingTransitionHarness(),{h,frames}=fixture;
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
    fixture.overshoot(true);h.setTransition("running");
    if(kind==="upper-style") h.bodyStyle.opacity="0";
    frames.shift()();await new Promise(resolve=>setImmediate(resolve));
    if(kind==="upper-style") {
      assert.deepEqual(await pending,{outcome:"unsupported",reason:"geometry_ancestor_style"});
      assert.equal(h.active(),false);assert.equal(h.attribute.size,0);continue;
    }
    assert.equal(h.active(),true);
    fixture.overshoot(false);h.setTransition("none");
    if(kind==="upper-final-clipping") h.page.body.getBoundingClientRect=()=>({left:101,right:419,top:0,bottom:240});
    frames.shift()();const result=await pending;
    if(kind==="settled") assert.equal(result.outcome,"applied");
    else {
      assert.deepEqual(result,{outcome:"unsupported",reason:"geometry_clipping"});
      assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
    }
  }
});

test("clipped running confirmation times out and cleans the owned layer",async()=>{
  const now=Date.now;let clock=1000;Date.now=()=>clock;
  try {
    const fixture=clippingTransitionHarness(),{h,frames}=fixture;
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false,3000);
    fixture.overshoot(true);h.setTransition("running");frames.shift()();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(h.active(),true);clock=1700;frames.shift()();
    assert.deepEqual(await pending,{outcome:"unsupported",reason:"geometry_post_write_current"});
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  } finally {Date.now=now;}
});

test("mutation and playback races during clipped transition clean the owned layer",async()=>{
  for (const kind of ["mutation","loadstart","emptied","ended"]) {
    const fixture=clippingTransitionHarness(),{h,frames}=fixture;
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
    fixture.overshoot(true);h.setTransition("running");frames.shift()();
    await new Promise(resolve=>setImmediate(resolve));assert.equal(h.active(),true);
    if(kind==="mutation") h.notify({attributeName:"class"});else h.video.fire(kind);
    assert.equal(h.active(),false);frames.shift()();
    assert.deepEqual(await pending,{outcome:"unsupported",reason:kind==="mutation" ? "geometry_close_mutation" : "geometry_close_playback"});
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  }
});

test("animation inspection rejects paused, infinite and non-transition transforms",()=>{
  class Transition {}
  const view={CSSTransition:Transition}, env=createVideoGeometryEnvironment({},view),element={};
  const effect={target:element,getKeyframes:()=>[{transform:"none"},{transform:"scale(1)"}],
    getComputedTiming:()=>({endTime:200,activeDuration:200})};
  const animation=Object.assign(new Transition(),{effect,transitionProperty:"transform",playState:"running",playbackRate:1});
  element.getAnimations=()=>[animation];
  assert.equal(env.transformTransitions(element),"running");
  animation.playState="paused";assert.equal(env.transformTransitions(element),"unsafe");
  animation.playState="running";effect.getComputedTiming=()=>({endTime:Infinity,activeDuration:Infinity});
  assert.equal(env.transformTransitions(element),"unsafe");
  effect.getComputedTiming=()=>({endTime:200,activeDuration:200});
  element.getAnimations=()=>[{...animation}];assert.equal(env.transformTransitions(element),"unsafe");
});


test("late frame after confirmation timeout cannot restore a layer",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  const pending=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true,Date.now()+15);
  assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
  frames.shift()();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("stale identity cannot cancel pending preparation",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.setTransition("running");const pending=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);
  assert.equal((await h.controller.reset(h.video,"wrong",h.isCurrent)).outcome,"unsupported");
  h.setTransition("none");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
  frames.shift()();assert.equal((await pending).outcome,"applied");
});

test("settled nonidentity transform after waiting is rejected",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.setTransition("running");const pending=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);
  h.site.set("transform",{matrix:[.8,1]});h.setTransition("none");frames.shift()();
  assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
});

test("post-apply inspection waits only for a transition to the expected matrix",()=>{
  class Transition {}
  class Matrix {constructor(value){
    const n=value.match(/matrix\(([^)]+)\)/)[1].split(",").map(Number);
    [this.a,this.b,this.c,this.d,this.e,this.f]=n;this.is2D=true;
  }}
  const element={},env=createVideoGeometryEnvironment({}, {CSSTransition:Transition,DOMMatrixReadOnly:Matrix});
  let end="matrix(-1,0,0,0.75,0,0)";
  const effect={target:element,getKeyframes:()=>[{transform:"none"},{transform:end}],
    getComputedTiming:()=>({endTime:200,activeDuration:200})};
  const animation=Object.assign(new Transition(),{effect,transitionProperty:"transform",playState:"running",playbackRate:1});
  element.getAnimations=()=>[animation];
  assert.equal(env.transformTransitions(element,{x:-1,y:.75}),"running");
  end="matrix(-0.9991,0.0009,-0.0009,0.7509,0,0)";
  assert.equal(env.transformTransitions(element,{x:-1,y:.75}),"running");
  end="matrix(1,0,0,1,10,0)";
  assert.equal(env.transformTransitions(element,{x:-1,y:.75}),"unsafe");
});

test("original and reset report cleanup without waiting for site presentation",async()=>{
  for (const method of ["original","reset"]) {
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    const first=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);frames.shift()();
    assert.equal((await first).outcome,"applied");
    h.setTransition("unsafe");h.site.set("transform",{matrix:[.8,1]});
    const restoring=method === "reset" ? h.controller.reset(h.video,"one",h.isCurrent) :
      h.controller.apply(h.video,"one",h.isCurrent,"original",false);
    assert.equal((await restoring).outcome,"restored");
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);assert.equal(frames.length,0);
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"original",false)).outcome,"unchanged");
  }
});

test("reset cleanup failure stays uncertain even when site presentation is unavailable",async()=>{
  const h=makeHarness({removeThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  h.setTransition("unsafe");h.site.set("transform",{matrix:[.8,1]});
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"uncertain");
  assert.equal(h.active(),true);h.allowCleanup();
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  assert.equal(h.active(),false);
});

test("reset cancels an older pending wait and cannot remove a newer active layer",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  h.setTransition("running");
  const old=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"unchanged");
  h.setTransition("none");const newer=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);
  frames.shift()();assert.equal((await old).outcome,"unsupported");assert.equal(h.active(),true);
  frames.shift()();assert.equal((await newer).outcome,"applied");assert.equal(h.active(),true);
});

function otherVideo(h) {
  const video=new Target(),attributes=new Map();
  Object.assign(video,{tagName:"VIDEO",ownerDocument:h.page,isConnected:true,
    currentSrc:"https://example.invalid/other",videoWidth:320,videoHeight:240,controls:false,
    mediaKeys:null,textTracks:[],parentElement:h.parent,getRootNode:()=>h.page,
    getBoundingClientRect:()=>({left:0,top:0,right:320,bottom:240,width:320,height:240})});
  video.hasAttribute=name=>attributes.has(name);
  video.getAttribute=name=>attributes.has(name)?attributes.get(name):null;
  video.setAttribute=(name,value)=>attributes.set(name,value);
  video.removeAttribute=name=>attributes.delete(name);
  return video;
}

test("a verified new video cleans up a no-longer-current owned layer",async()=>{
  const h=makeHarness(),other=otherVideo(h);
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  h.setCurrent("two");
  assert.equal((await h.controller.apply(other,"two",h.isCurrent,"original",false)).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("failed cleanup of a no-longer-current video is uncertain and remains tracked",async()=>{
  const h=makeHarness({removeThrows:true,attributeRemoveThrows:true}),other=otherVideo(h);
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  h.setCurrent("two");
  assert.equal((await h.controller.apply(other,"two",h.isCurrent,"original",false)).outcome,"uncertain");
  assert.equal(h.active(),true);h.allowCleanup();
  assert.equal((await h.controller.apply(other,"two",h.isCurrent,"original",false)).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("late confirmation from retired video cannot remove a subsequently installed layer",async()=>{
  const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
  const other=otherVideo(h);
  const old=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
  h.setCurrent("two");
  assert.equal((await h.controller.apply(other,"two",h.isCurrent,"original",false)).outcome,"restored");
  h.setCurrent("one");
  const newer=h.controller.apply(h.video,"one",h.isCurrent,"4:3",true);
  frames.shift()();assert.equal((await old).outcome,"unsupported");assert.equal(h.active(),true);
  frames.shift()();assert.equal((await newer).outcome,"applied");assert.equal(h.active(),true);
});

for (const event of ["loadstart","emptied","ended"]) {
  test(`same-source ${event} invalidates preparation and removes temporary listeners`,async()=>{
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    h.setTransition("running");
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
    h.video.fire(event);h.setTransition("none");frames.shift()();
    assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
    for (const name of ["loadstart","emptied","ended"]) assert.equal(h.video.events.get(name)?.size || 0,0);
  });
  test(`same-source ${event} invalidates confirmation and cleans the owned layer`,async()=>{
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"16:9",true);
    h.video.fire(event);frames.shift()();
    assert.equal((await pending).outcome,"unsupported");assert.equal(h.active(),false);
    for (const name of ["loadstart","emptied","ended"]) assert.equal(h.video.events.get(name)?.size || 0,0);
  });
}

test("geometry failure categories come from the actual checks without page data",async()=>{
  const cases=[
    [h=>{h.video.controls=true;},"geometry_eligibility"],
    [h=>{h.view.innerWidth=10;},"geometry_viewport"],
    [h=>{h.parentStyle.transform="matrix(2, 0, 0, 1, 0, 0)";},"geometry_ancestor_style"],
    [h=>{h.parentStyle.overflowX="hidden";h.parent.getBoundingClientRect=()=>({left:161,right:319,top:0,bottom:240});},"geometry_clipping"],
    [h=>{h.setTransition("unsafe");},"geometry_transition"],
    [h=>{h.videoStyle.transform="ignored";h.site.set("transform",{matrix:[0.5,1]});},"geometry_video_transform"],
    [h=>{h.site.set("object-fit",{value:"contain",important:true});},"geometry_presentation_matrix"],
  ];
  for(const [mutate,reason] of cases){
    const h=makeHarness();mutate(h);
    const result=await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false);
    assert.deepEqual(result,{outcome:"unsupported",reason});
    assert.equal(h.active(),false);
  }
});

test("post-write guard and presentation bounds and ratio have distinct fixed reasons",async()=>{
  for(const [kind,reason] of [["guard","geometry_post_write_current"],["bounds","geometry_presentation_bounds"],["ratio","geometry_presentation_ratio"]]){
    let h,frames=0;
    h=makeHarness({afterFrame:()=>{frames++;if(kind==="guard")h.video.controls=true;return Promise.resolve();}});
    const rect=h.video.getBoundingClientRect;
    h.video.getBoundingClientRect=()=>{
      const box=rect();
      if(frames && kind==="bounds") return {...box,left:box.left+5,right:box.right+5};
      if(frames && kind==="ratio") return {...box,width:box.width-10};
      return box;
    };
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false),{outcome:"unsupported",reason});
    assert.equal(h.active(),false);
  }
});

test("post-write checks identify closed session, ownership, and actual layout failure",async()=>{
  for(const [kind,reason] of [["closed","geometry_close_mutation"],
    ["marker","geometry_post_write_ownership"],["layer","geometry_post_write_ownership"],
    ["viewport","geometry_viewport"],
    ["style","geometry_ancestor_style"],["clipping","geometry_clipping"]]){
    let h,layer;
    h=makeHarness({afterFrame:()=>{
      if(kind==="closed") h.notify({attributeName:"class"});
      if(kind==="marker") h.attribute.clear();
      if(kind==="layer") layer.remove();
      if(kind==="viewport") h.view.innerWidth=10;
      if(kind==="style") h.parentStyle.opacity="0";
      if(kind==="clipping") {
        h.parentStyle.overflowX="hidden";
        h.parent.getBoundingClientRect=()=>({left:1,right:319,top:0,bottom:240});
      }
      return Promise.resolve();
    }});
    const append=h.page.head.appendChild;
    h.page.head.appendChild=node=>{layer=node;append(node);};
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false),
      {outcome:"unsupported",reason});
    assert.equal(h.active(),false);
  }
});

test("post-write timeout is categorized and cleanup failure remains uncertain",async()=>{
  const timeout=makeHarness({afterFrame:()=>new Promise(()=>{})});
  assert.deepEqual(await timeout.controller.apply(timeout.video,"one",timeout.isCurrent,"16:9",false,Date.now()+20),
    {outcome:"unsupported",reason:"geometry_post_write_current"});
  let h;
  h=makeHarness({removeThrows:true,afterFrame:()=>{h.attribute.clear();return Promise.resolve();}});
  assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false),{outcome:"uncertain"});
  h.allowCleanup();h.tick();
});

test("running confirmation at its limit reports current, not an arbitrary error",async()=>{
  const original=Date.now;let clock=1000,h;
  Date.now=()=>clock;
  try {
    h=makeHarness({afterFrame:()=>{clock=1700;h.setTransition("running");return Promise.resolve();}});
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false,3000),
      {outcome:"unsupported",reason:"geometry_post_write_current"});
    assert.equal(h.active(),false);
  } finally {Date.now=original;}
});

test("post-write exceptions do not expose text or mask uncertain cleanup",async()=>{
  const h=makeHarness({appendThrows:true,removeThrows:true});
  assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false),{outcome:"uncertain"});
  h.allowCleanup();h.tick();
});

test("close callbacks report only their fixed per-session cause",async()=>{
  for (const [kind,reason] of [["mutation","geometry_close_mutation"],
    ["playback","geometry_close_playback"],["check","geometry_close_check"]]) {
    let h;
    h=makeHarness({afterFrame:()=>{
      if(kind==="mutation") h.notify({attributeName:"sensitive page value"});
      if(kind==="playback") h.video.fire("loadstart");
      if(kind==="check") {h.page.hidden=true;h.page.fire("visibilitychange");}
      return Promise.resolve();
    }});
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"16:9",false),
      {outcome:"unsupported",reason});
    assert.equal(h.active(),false);
  }
});

test("viewport and clipping overshoot waits in preparation and confirmation until settled",async()=>{
  for (const phase of ["preparation","confirmation"]) {
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    h.parentStyle.overflowX="hidden";h.parent.getBoundingClientRect=()=>({left:0,right:320,top:0,bottom:240});
    const rect=h.video.getBoundingClientRect;let overshoot=phase==="preparation";
    h.video.getBoundingClientRect=()=>{const box=rect();return overshoot ? {...box,left:-5,right:box.right+5} : box;};
    if(overshoot) h.setTransition("running");
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    if(phase==="confirmation") {overshoot=true;h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));}
    assert.equal(frames.length,1);overshoot=false;h.setTransition("none");frames.shift()();
    if(phase==="preparation") {await new Promise(resolve=>setImmediate(resolve));frames.shift()();}
    assert.equal((await pending).outcome,"applied");
  }
});

test("running viewport overflow retains invalid box and safety rejection",async()=>{
  for (const phase of ["preparation","confirmation"]) for (const kind of ["nan","infinity","zero","style","unsafe"]) {
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    const rect=h.video.getBoundingClientRect;let bad=false;
    h.video.getBoundingClientRect=()=>{const box=rect();if(!bad)return box;
      return {...box,left:kind==="nan" ? NaN : -5,right:kind==="infinity" ? Infinity : box.right,width:kind==="zero" ? 0 : box.width};};
    const mutate=()=>{bad=true;h.setTransition(kind==="unsafe" ? "unsafe" : "running");if(kind==="style")h.parentStyle.opacity="0";};
    if(phase==="preparation")mutate();
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    if(phase==="confirmation"){mutate();frames.shift()();}
    const reason=kind==="style" ? "geometry_ancestor_style" : kind==="unsafe" && phase==="preparation" ? "geometry_transition" : "geometry_viewport";
    assert.deepEqual(await pending,{outcome:"unsupported",reason},`${phase} ${kind}`);
    assert.equal(h.active(),false);
  }
});

test("viewport overflow remains strict when settled, including viewport shrink",async()=>{
  for (const phase of ["final","shrink"]) {
    const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    const rect=h.video.getBoundingClientRect;let overflow=false;
    h.video.getBoundingClientRect=()=>{const box=rect();return overflow ? {...box,left:-5} : box;};
    const pending=h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    {overflow=true;h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
      if(phase==="shrink") {overflow=false;h.view.innerWidth=10;}
      h.setTransition("none");frames.shift()();}
    assert.deepEqual(await pending,{outcome:"unsupported",reason:"geometry_viewport"});assert.equal(h.active(),false);
  }
});

test("viewport overflow preparation timeout rechecks and never writes",async()=>{
  const now=Date.now;let clock=1000;Date.now=()=>clock;
  try {
    const h=makeHarness({afterFrame:()=>{clock=1701;return Promise.resolve();}});
    const rect=h.video.getBoundingClientRect;h.video.getBoundingClientRect=()=>({...rect(),left:-5});h.setTransition("running");
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"original",true,3000),{outcome:"unsupported",reason:"transition_busy"});
    assert.equal(h.active(),false);
  } finally {Date.now=now;}
});

test("viewport overflow confirmation fences media, ownership, and timeout",async()=>{
  for (const kind of ["source","ownership","timeout"]) {
    const now=Date.now;let clock=1000;Date.now=()=>clock;
    try {
      const frames=[];const h=makeHarness({afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
      const rect=h.video.getBoundingClientRect;let overflow=false;
      h.video.getBoundingClientRect=()=>{const box=rect();return overflow ? {...box,left:-5} : box;};
      const pending=h.controller.apply(h.video,"one",h.isCurrent,"original",true,3000);
      overflow=true;h.setTransition("running");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
      if(kind==="source")h.video.currentSrc="https://example.invalid/changed";
      if(kind==="ownership")h.attribute.clear();
      if(kind==="timeout")clock=1700;
      frames.shift()();const result=await pending;
      assert.equal(result.outcome,"unsupported",kind);assert.equal(h.active(),false,kind);assert.equal(h.attribute.size,0,kind);
    } finally {Date.now=now;}
  }
});

test("centered fit handles each viewport edge and preserves independent mirror and aspect",async()=>{
  for (const [edge,box] of Object.entries({left:{left:-40,top:50,width:200,height:200},right:{left:240,top:50,width:200,height:200},top:{left:100,top:-40,width:200,height:200},bottom:{left:100,top:140,width:200,height:200}})) {
    for (const mode of ["original","4:3","16:9"]) for (const mirror of [false,true]) {
      if(mode==="original" && !mirror)continue;
      const h=makeHarness({box});h.view.innerWidth=400;h.view.innerHeight=300;
      assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,mode,mirror)).outcome,"applied",`${edge} ${mode} ${mirror}`);
      const rect=h.video.getBoundingClientRect(),[x,y]=h.effective();
      assert.ok(rect.left>=0 && rect.right<=400 && rect.top>=0 && rect.bottom<=300,edge);
      assert.ok(Math.abs((rect.left+rect.right)/2-(box.left+box.width/2))<1e-9);
      assert.ok(Math.abs((rect.top+rect.bottom)/2-(box.top+box.height/2))<1e-9);
      assert.equal(x<0,mirror);assert.ok(y>0);
      if(mode!=="original")assert.ok(Math.abs(rect.width/rect.height-(mode==="4:3" ? 4/3 : 16/9))<1e-9);
      assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");assert.equal(h.active(),false);
    }
  }
});

test("fit intersects multiple clipping ancestors and leaves fitting target scale unchanged",async()=>{
  const h=makeHarness({box:{left:0,top:0,width:400,height:300}});h.view.innerWidth=400;h.view.innerHeight=300;
  h.parentStyle.overflowX="hidden";h.bodyStyle.overflowY="hidden";
  h.parent.getBoundingClientRect=()=>({left:50,right:350,top:0,bottom:300});
  h.page.body.getBoundingClientRect=()=>({left:0,right:400,top:75,bottom:225});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"original",true)).outcome,"applied");
  assert.ok(Math.abs(h.effective()[0]+0.5)<1e-10 && Math.abs(h.effective()[1]-0.5)<1e-10);
  assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
  const target=makeHarness({box:{left:0,top:-50,width:400,height:400}});target.view.innerWidth=400;target.view.innerHeight=300;
  assert.equal((await target.controller.apply(target.video,"one",target.isCurrent,"16:9",false)).outcome,"applied");
  assert.deepEqual(target.effective(),[1,0.5625]);
});

test("centered fit rejects impossible centers, invalid bounds and invalid neutral boxes",async()=>{
  for (const [box,reason] of [
    [{left:-400,top:0,width:200,height:100},"geometry_viewport"],
    [{left:-100,top:0,width:200,height:100},"geometry_viewport"],
    [{left:0,top:0,width:0,height:100},"geometry_viewport"],
    [{left:0,top:0,width:Infinity,height:100},"geometry_viewport"],
    [{left:NaN,top:0,width:200,height:100},"geometry_viewport"]]) {
    const h=makeHarness({box});h.view.innerWidth=400;h.view.innerHeight=300;
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"original",true),{outcome:"unsupported",reason});assert.equal(h.active(),false);
  }
  for (const rect of [{left:201,right:300,top:0,bottom:300},{left:0,right:NaN,top:0,bottom:300},{left:0,right:0,top:0,bottom:300}]) {
    const h=makeHarness({box:{left:0,top:0,width:400,height:300}});h.view.innerWidth=400;h.view.innerHeight=300;
    h.parentStyle.overflowX="hidden";h.parent.getBoundingClientRect=()=>rect;
    assert.deepEqual(await h.controller.apply(h.video,"one",h.isCurrent,"original",true),{outcome:"unsupported",reason:"geometry_clipping"});assert.equal(h.active(),false);
  }
});

test("centered fit handles large, small and fractional finite boxes",async()=>{
  for(const box of [{left:-500000,top:0,width:1000400,height:300},{left:199.875,top:149.875,width:0.25,height:0.25},{left:-0.25,top:49.75,width:400.5,height:200.5}]) {
    const h=makeHarness({box});h.view.innerWidth=400;h.view.innerHeight=300;
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"original",true)).outcome,"applied");
    const r=h.video.getBoundingClientRect();assert.ok(r.left>=0 && r.right<=400 && r.top>=0 && r.bottom<=300);
  }
});

test("fitted sessions retain transition, change and cleanup fences",async()=>{
  for(const kind of ["settled","viewport","clip","source","ownership"]) {
    const frames=[];const h=makeHarness({box:{left:-40,top:50,width:200,height:200},afterFrame:()=>new Promise(resolve=>frames.push(resolve))});
    h.view.innerWidth=400;h.view.innerHeight=300;h.parentStyle.overflowX="hidden";
    let clip={left:0,right:400,top:0,bottom:300};h.parent.getBoundingClientRect=()=>clip;
    h.setTransition("running");const pending=h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    h.setTransition("none");frames.shift()();await new Promise(resolve=>setImmediate(resolve));
    if(kind==="viewport")h.view.innerWidth=20;
    if(kind==="clip")clip={left:100,right:400,top:0,bottom:300};
    if(kind==="source")h.video.currentSrc="https://example.invalid/changed";
    if(kind==="ownership")h.attribute.clear();
    frames.shift()();const result=await pending;
    assert.equal(result.outcome,kind==="settled" ? "applied" : "unsupported",kind);
    if(kind!=="settled") {assert.equal(h.active(),false);assert.equal(h.attribute.size,0);}
  }
});

test("fitted active session closes when clipping or viewport changes",async()=>{
  for(const kind of ["clip","viewport"]) {
    const h=makeHarness({box:{left:-40,top:50,width:200,height:200}});h.view.innerWidth=400;h.view.innerHeight=300;
    h.parentStyle.overflowX="hidden";let clip={left:0,right:400,top:0,bottom:300};h.parent.getBoundingClientRect=()=>clip;
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"original",true)).outcome,"applied");
    if(kind==="clip")clip={left:50,right:400,top:0,bottom:300};else h.view.innerWidth=20;
    h.tick();assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  }
});

test("tiny fitted mirror presentation requires the correct signed scale",async()=>{
  for (const kind of ["correct","opposite","relative-error","zero"]) {
    let h;
    h=makeHarness({box:{left:-999800,top:-499850,width:2000000,height:1000000},afterFrame:()=>{
      if(kind!=="correct") {
        const [x,y]=h.effective();
        h.site.set("transform",{matrix:[kind==="opposite" ? -x : kind==="zero" ? 0 : x*0.5,y],important:true});
      }
      return Promise.resolve();
    }});
    h.view.innerWidth=400;h.view.innerHeight=300;
    const result=await h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    if(kind==="correct") {
      assert.equal(result.outcome,"applied");assert.ok(h.effective()[0]<0 && Math.abs(h.effective()[0])<0.001);
      assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
    } else {
      assert.equal(result.outcome,"unsupported",kind);assert.equal(h.active(),false,kind);assert.equal(h.attribute.size,0,kind);
      if(kind!=="zero")assert.equal(result.reason,"geometry_presentation_matrix",kind);
    }
  }
});

test("tiny transition endpoint requires signed scale and bounded relative error",()=>{
  class Transition {}
  class Matrix {constructor(value){
    const n=value.match(/matrix\(([^)]+)\)/)[1].split(",").map(Number);
    [this.a,this.b,this.c,this.d,this.e,this.f]=n;this.is2D=true;
  }}
  const element={},env=createVideoGeometryEnvironment({}, {CSSTransition:Transition,DOMMatrixReadOnly:Matrix});
  let end="matrix(-0.0001,0,0,0.0002,0,0)";
  const effect={target:element,getKeyframes:()=>[{transform:"none"},{transform:end}],
    getComputedTiming:()=>({endTime:200,activeDuration:200})};
  element.getAnimations=()=>[Object.assign(new Transition(),{effect,transitionProperty:"transform",playState:"running",playbackRate:1})];
  const expected={x:-0.0001,y:0.0002};
  assert.equal(env.transformTransitions(element,expected),"running");
  for(const matrix of ["matrix(0.0001,0,0,0.0002,0,0)","matrix(-0.00015,0,0,0.0002,0,0)",
    "matrix(-0.0001,0,0,-0.0002,0,0)","matrix(-0.0001,NaN,0,0.0002,0,0)"]) {
    end=matrix;assert.equal(env.transformTransitions(element,expected),"unsafe",matrix);
  }
  for(const matrix of ["matrix(-0.0001,0.00005,0,0.0002,0,0)","matrix(-0.0001,0,0.00005,0.0002,0,0)"]) {
    end=matrix;assert.equal(env.transformTransitions(element,expected),"unsafe",matrix);
  }
  end="matrix(-0.0001005,0.0000005,-0.000001,0.000201,0,0)";
  assert.equal(env.transformTransitions(element,expected),"running");
  end="matrix(-0.0001,0.0000005,0.0009,0.75,0,0)";
  assert.equal(env.transformTransitions(element,{x:-0.0001,y:0.75}),"running");
});

test("presentation bounds shear relative to fitted axes and permits ordinary rounding",async()=>{
  for (const kind of ["tiny-b","tiny-c","tiny-rounding","ordinary-rounding"]) {
    const tiny=kind!=="ordinary-rounding";
    const options={box:tiny ? {left:-999800,top:-499850,width:2000000,height:1000000} : undefined};
    options.afterFrame=()=>{options.shear=kind==="tiny-b" ? {b:0.00005} : kind==="tiny-c" ? {c:0.00005} :
      kind==="tiny-rounding" ? {b:0.0000005,c:-0.0000005} : {b:0.0009,c:-0.0009};return Promise.resolve();};
    const h=makeHarness(options);h.view.innerWidth=400;h.view.innerHeight=300;
    const result=await h.controller.apply(h.video,"one",h.isCurrent,"original",true);
    if(kind==="tiny-b" || kind==="tiny-c") {
      assert.deepEqual(result,{outcome:"unsupported",reason:"geometry_presentation_matrix"},kind);
      assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
    } else {
      assert.equal(result.outcome,"applied",kind);
      assert.equal((await h.controller.reset(h.video,"one",h.isCurrent)).outcome,"restored");
    }
  }
});
