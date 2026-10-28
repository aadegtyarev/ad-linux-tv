"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {createPhoneTouchpad} = require("../src/ad_linux_tv/static/touchpad_controls.js");
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture(t, post = async () => {}, request = async () => ({ok:true, status:200})) {
  const old = {document:global.document, acceleration:global.PointerAcceleration};
  const elements = new Map();
  global.document = {querySelector(id) {
    if (!elements.has(id)) elements.set(id, {
      events:{}, style:{}, classList:{add(){}, remove(){}}, setAttribute(){},
      addEventListener(name, callback) { this.events[name] = callback; },
      setPointerCapture(){}, getBoundingClientRect() { return {left:0, top:0}; },
    });
    return elements.get(id);
  }};
  global.PointerAcceleration = class { move(dx,dy) { return {dx,dy}; } };
  t.after(() => { global.document = old.document; global.PointerAcceleration = old.acceleration; });
  const errors = [], auth = [];
  const controller = createPhoneTouchpad(post, request, () => 50, () => auth.push(true), text => errors.push(text));
  t.after(() => controller.stop());
  const pad = elements.get("#remote-touchpad");
  const event = (x = 20) => ({pointerId:1, clientX:x, clientY:20, timeStamp:0,
    preventDefault(){}, target:{closest(){ return null; }}});
  return {controller, pad, event, auth, errors};
}

test("two fingers coalesce diagonal scrolling without a click", async t => {
  const sent=[];
  const {controller,pad,event}=fixture(t,undefined,async body=>{sent.push(body);return {ok:true,status:200};});
  const e=(id,x,y)=>({...event(x),pointerId:id,clientY:y});
  pad.events.pointerdown(e(1,20,20));pad.events.pointerdown(e(2,40,20));
  pad.events.pointermove(e(1,32,26));
  pad.events.pointerup(e(1,32,26));pad.events.pointerup(e(2,40,20));
  await new Promise(resolve=>setTimeout(resolve,60));
  assert.deepEqual(sent,[{scroll:-6,scroll_x:-12}]);
  controller.reset();sent.length=0;
  pad.events.pointerdown(e(1,20,20));pad.events.pointerdown(e(2,40,20));
  pad.events.pointermove(e(1,32,20));controller.reset();
  await new Promise(resolve=>setTimeout(resolve,60));assert.deepEqual(sent,[]);
});

test("stop drops queued keys and rejects future gesture work without replay", async t => {
  let complete;
  const sent = [];
  const {controller} = fixture(t, (_path, body) => {
    sent.push(body.key); return new Promise(resolve => { complete = resolve; });
  });
  const first = controller.sendKey("up");
  const second = controller.sendKey("down");
  await flush();
  controller.stop(); complete();
  await Promise.all([first, second]);
  await controller.sendKey("right");
  assert.deepEqual(sent, ["up"]);
});

test("reauth reset fences old navigation but fresh explicit input does not wait for it", async t => {
  let complete;
  const sent = [];
  const {controller} = fixture(t, (_path, body) => {
    sent.push(body.key);
    return body.key === "up" ? new Promise(resolve => { complete = resolve; }) : Promise.resolve();
  });
  const first = controller.sendKey("up"), second = controller.sendKey("down");
  await flush(); controller.reset();
  await controller.sendKey("right"); complete();
  await Promise.all([first, second]);
  assert.deepEqual(sent, ["up", "right"]);
});

test("reset discards a click waiting for the pointer drain microtask", async t => {
  const sent = [];
  const {controller, pad, event} = fixture(t, undefined, async body => {
    sent.push(body); return {ok:true,status:200};
  });
  pad.events.pointerdown(event()); pad.events.pointerup(event());
  controller.reset(); await flush();
  assert.deepEqual(sent, []);
});

test("late auth error from retired gesture cannot change current UI or restart transport", async t => {
  let complete;
  const {controller, pad, event, auth, errors} = fixture(t, undefined,
    () => new Promise(resolve => { complete = resolve; }));
  pad.events.pointerdown(event()); pad.events.pointermove(event(40));
  await new Promise(resolve => setTimeout(resolve, 35));
  assert.equal(typeof complete, "function");
  controller.stop(); complete({status:403,ok:false}); await flush();
  assert.deepEqual(auth, []); assert.deepEqual(errors, []);
});
