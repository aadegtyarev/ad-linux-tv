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
  let current="one",layer=null,observerCallback,timerCallback,records=[],serial=0;
  let removeAttributeThrows=Boolean(options.attributeRemoveThrows),removeThrows=Boolean(options.removeThrows);
  const base=()=>({display:"block",visibility:"visible",opacity:"1",clipPath:"none",scale:"none",rotate:"none",translate:"none",transform:"none",overflowX:"visible",overflowY:"visible",borderLeftWidth:"0px",borderRightWidth:"0px",borderTopWidth:"0px",borderBottomWidth:"0px",paddingLeft:"0px",paddingRight:"0px",paddingTop:"0px",paddingBottom:"0px",objectFit:"contain"});
  const site=new Map(),attribute=new Map(),video=new Target();
  Object.assign(video,{tagName:"VIDEO",ownerDocument:page,isConnected:true,currentSrc:"https://example.invalid/one",videoWidth:320,videoHeight:240,controls:false,mediaKeys:null,textTracks:[],parentElement:parent,getRootNode:()=>page});
  video.hasAttribute=name=>attribute.has(name);
  video.getAttribute=name=>attribute.has(name)?attribute.get(name):null;
  video.setAttribute=(name,value)=>{attribute.set(name,value);};
  video.removeAttribute=name=>{if(removeAttributeThrows)throw Error("attribute removal");attribute.delete(name);};
  const parentStyle=base(),videoStyle=base();
  const layerTransform=()=>{
    if(!layer?.isConnected)return null;
    const attr=layer.textContent.match(/video\[([^\]]+)\]/)?.[1];
    if(!attribute.has(attr))return null;
    const match=layer.textContent.match(/transform:scale\(([^,]+),([^\)]+)\)/);
    return match ? [Number(match[1]),Number(match[2])] : null;
  };
  const effective=()=>site.get("transform")?.important ? site.get("transform").matrix : layerTransform() || site.get("transform")?.matrix || [1,1];
  video.getBoundingClientRect=()=>{const [x,y]=effective();const w=320*Math.abs(x),h=240*Math.abs(y);return {left:160-w/2,right:160+w/2,top:120-h/2,bottom:120+h/2,width:w,height:h};};
  page.createElement=name=>{
    assert.equal(name,"style");
    return {textContent:"",isConnected:false,remove(){if(removeThrows)throw Error("remove");this.isConnected=false;}};
  };
  page.head={appendChild(node){layer=node;node.isConnected=true;if(options.appendThrows)throw Error("append");}};
  const styleOf=element=>{
    if(element===parent)return parentStyle;
    if(element!==video)return base();
    const s={...videoStyle}, [x,y]=effective();
    s.transform=(x===1 && y===1 && !layerTransform() && !site.has("transform")) ? "none" : `matrix(${x}, 0, 0, ${y}, 0, 0)`;
    if(layerTransform() && layer.textContent.includes("object-fit:fill") && !site.get("object-fit")?.important)s.objectFit="fill";
    else if(site.has("object-fit"))s.objectFit=site.get("object-fit").value;
    return s;
  };
  const matrixOf=value=>{
    if(value==="none")return {a:1,b:0,c:0,d:1,e:0,f:0};
    const n=value.match(/matrix\(([^)]+)\)/)[1].split(",").map(Number);
    return {a:n[0],b:n[1],c:n[2],d:n[3],e:n[4],f:n[5]};
  };
  const env={page,view,styleOf,matrixOf,afterFrame:options.afterFrame||(()=>Promise.resolve()),randomToken:()=>String(++serial).padStart(32,"0"),
    observe:(_video,callback)=>{if(options.observeThrows)throw Error("observe");observerCallback=callback;return {takeRecords:()=>records.splice(0),disconnect(){}};},
    setTimer:callback=>{timerCallback=callback;return 1;},clearTimer:()=>{}};
  const controller=createVideoGeometryController(env);
  return {page,view,parent,parentStyle,video,videoStyle,site,attribute,controller,
    isCurrent:(_v,id)=>current===id,setCurrent:id=>{current=id;},
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
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"unsupported");
  assert.equal(h.active(),true);assert.equal(h.controller.reset(h.video,"two",h.isCurrent).outcome,"restored");
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
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
  assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
});

test("open shadow player uses its own style layer and supports fullscreen hosts",async()=>{
  const h=makeHarness(),root={mode:"open",host:h.page.body};let appended=false;
  root.appendChild=node=>{appended=true;h.page.head.appendChild(node);};
  h.video.getRootNode=()=>root;h.parent.parentElement=null;h.parent.getRootNode=()=>root;
  h.page.fullscreenElement=h.page.body;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(appended,true);assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
});

test("an accessible closed shadow root can use its own style layer",async()=>{
  const h=makeHarness(),root={mode:"closed",host:h.page.body};let appended=false;
  root.appendChild=node=>{appended=true;h.page.head.appendChild(node);};
  h.video.getRootNode=()=>root;h.parent.parentElement=null;h.parent.getRootNode=()=>root;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(appended,true);assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
});

test("a normal fullscreen player with overflow hidden is accepted only when video fits",async()=>{
  const h=makeHarness();
  h.parentStyle.overflowX="hidden";h.parentStyle.overflowY="hidden";
  h.parent.getBoundingClientRect=()=>({left:0,top:0,right:320,bottom:240,width:320,height:240});
  h.page.fullscreenElement=h.parent;
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"applied");
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
  h.parent.getBoundingClientRect=()=>({left:20,top:0,right:300,bottom:240,width:280,height:240});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"unsupported");
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
    assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"unsupported");
    assert.equal(h.active(),false);assert.equal(h.attribute.size,0);
  }
  const h=makeHarness({removeThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"uncertain");
  assert.equal(h.attribute.size,0); // inert even if node removal failed
});

test("simultaneous failed removals remain tracked and can be retried",async()=>{
  const h=makeHarness({removeThrows:true,attributeRemoveThrows:true});
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"4:3",true)).outcome,"applied");
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"uncertain");
  assert.equal(h.active(),true);assert.equal(h.attribute.size,1);
  assert.equal((await h.controller.apply(h.video,"one",h.isCurrent,"16:9",true)).outcome,"uncertain");
  h.allowCleanup();assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
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
  assert.equal(h.controller.reset(h.video,"one",h.isCurrent).outcome,"restored");
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
