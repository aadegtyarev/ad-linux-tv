"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const reply=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body});
function deferred(){let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};}
function fixture(handler){
  let now=1000,serial=0,auth=0,revision=0;const timers=new Map(),calls=[],states=[],notices=[];
  class Element {
    constructor(){this.events={};this.disabled=false;this.open=false;this.attrs={};this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x)};}
    addEventListener(name,fn){this.events[name]=fn;}
    setAttribute(n,v){this.attrs[n]=v;if(n==="open")this.open=true;}
    removeAttribute(n){delete this.attrs[n];if(n==="open")this.open=false;}
    showModal(){this.open=true;}
    close(){this.open=false;}
    focus(){this.focused=true;}
    setPointerCapture(){}
    fire(name,args={}){return this.events[name]?.({preventDefault(){},...args});}
  }
  const elements=Object.fromEntries(["remote-power","power-dialog","power-confirm","power-cancel","power-note"].map(id=>[id,new Element()]));
  const document={hidden:false,events:{},querySelector:s=>elements[s.slice(1)],addEventListener(n,f){this.events[n]=f;}};
  const window={events:{},addEventListener(n,f){this.events[n]=f;}};
  const context={document,window,Date:class extends Date{static now(){return now;}},
    setTimeout:(fn,ms)=>{const id=++serial;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id)};
  vm.createContext(context);vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/power_controls.js","utf8"),context);
  let power;
  const options={request:async(method,path,body)=>{
    calls.push({method,path,body});if(handler)return handler(method,path,body);
    if(method==="GET")return reply({available:true,phase:"idle"});
    if(path==="/api/display-timer")return reply({asleep:!!body.sleep,phase:body.sleep?"asleep":"idle",error:null});
    return reply(body.action==="prepare"?{challenge:"a".repeat(43),expires_in:20}:{phase:"requested"},body.action==="prepare"?200:202);
  },auth:()=>{auth++;power.stop();},say:(...args)=>notices.push(args),beforeTimer:()=>++revision,
  timer:state=>{states.push(state);power.renderTimer(state);}};
  context.options=options;power=vm.runInContext("new RemotePowerControls(options)",context);power.start();
  function advance(ms){const end=now+ms;while(true){const next=[...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;now=next[1].at;timers.delete(next[0]);next[1].fn();}now=end;}
  const posts=()=>calls.filter(c=>c.method==="POST");
  return {power,elements,window,document,calls,posts,states,notices,advance,auth:()=>auth};
}

test("tap sends explicit sleep/wake and debounces duplicate activation",async()=>{
  const f=fixture();await flush();await f.power.tap();await f.power.tap();
  assert.equal(f.posts().length,1);assert.equal(f.posts()[0].body.sleep,true);
  f.advance(651);await f.power.tap();assert.equal(f.posts()[1].body.wake,true);
  assert.equal(f.power.busy,false);
});

test("hold prepares only; release/compat click never becomes short tap; confirm once",async()=>{
  const f=fixture();await flush();const button=f.elements["remote-power"];
  button.fire("pointerdown",{pointerId:1,clientX:0,clientY:0});f.advance(1201);await flush();
  assert.equal(f.posts().length,1);assert.equal(f.posts()[0].body.action,"prepare");
  assert.equal(f.elements["power-dialog"].open,true);assert.equal(f.elements["power-cancel"].focused,true);
  button.fire("pointerup",{pointerId:1});button.fire("click");await flush();assert.equal(f.posts().length,1);
  f.elements["power-confirm"].fire("click");await flush();f.elements["power-confirm"].fire("click");await flush();
  assert.equal(f.posts().length,2);assert.equal(f.posts()[1].body.action,"shutdown");assert.equal(f.power.phase,"requested");
});

test("motion/cancel removes hold and suppresses generated tap",async()=>{
  for(const cancel of ["pointercancel","pointermove"]){
    const f=fixture();await flush();const b=f.elements["remote-power"];
    b.fire("pointerdown",{pointerId:1,clientX:0,clientY:0});
    b.fire(cancel,{pointerId:1,clientX:20,clientY:0});f.advance(1201);
    b.fire("pointerup",{pointerId:1});b.fire("click");await flush();assert.equal(f.posts().length,0);
  }
});

test("dismiss fences late challenge; expired challenge cannot dispatch",async()=>{
  const gate=deferred();const f=fixture((m)=>m==="GET"?reply({available:true,phase:"idle"}):gate.promise);
  await flush();void f.power.open();f.power.dismiss();gate.resolve(reply({challenge:"a".repeat(43),expires_in:20}));await flush();
  assert.equal(f.elements["power-confirm"].disabled,true);assert.equal(f.elements["power-dialog"].open,false);
  const good=fixture();await flush();await good.power.open();good.advance(20_001);await good.power.shutdown();
  assert.equal(good.posts().length,1);assert.equal(good.elements["power-confirm"].disabled,true);
});

test("uncertain shutdown is not replayed",async()=>{
  const f=fixture((m,p,b)=>{
    if(m==="GET")return reply({available:true,phase:"idle"});
    if(b.action==="prepare")return reply({challenge:"a".repeat(43),expires_in:20});
    throw new Error("unknown delivery");
  });await flush();await f.power.open();await f.power.shutdown();await f.power.shutdown();await f.power.tap();
  assert.equal(f.posts().length,2);assert.equal(f.power.phase,"uncertain");
});

test("retirement fences late output result; blur does not strand short-action busy state",async()=>{
  for(const retire of [true,false]){
    const gate=deferred();const f=fixture(m=>m==="GET"?reply({available:true,phase:"idle"}):gate.promise);await flush();
    const pending=f.power.tap();if(retire){f.power.stop();f.power.start();}else f.window.events.blur();
    gate.resolve(reply({asleep:true,phase:"asleep",error:null}));await pending;
    assert.equal(f.states.length,retire?0:1);assert.equal(f.power.busy,false);
  }
});

test("keyboard/context confirmation and page visibility cancel never issue short action",async()=>{
  const f=fixture();await flush();const b=f.elements["remote-power"];
  b.fire("keydown",{key:"Enter",repeat:false});f.advance(1201);await flush();b.fire("keyup",{key:"Enter"});
  assert.equal(f.posts().length,1);assert.equal(f.posts()[0].body.action,"prepare");
  f.document.hidden=true;f.document.events.visibilitychange();assert.equal(f.elements["power-dialog"].open,false);
});
