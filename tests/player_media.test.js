"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {webcrypto} = require("node:crypto");
const {playerMedia} = require("../extension/player_media.js");
function setup(t, elements = []) {
  const previous = {document:global.document, crypto:global.crypto};
  global.document = {querySelectorAll:() => elements};
  Object.defineProperty(global, "crypto", {value:webcrypto, configurable:true});
  t.after(() => { global.document = previous.document; Object.defineProperty(global,"crypto", {value:previous.crypto, configurable:true}); });
  return elements;
}
function media(patch = {}) {
  return {tagName:"VIDEO", currentSrc:"https://example.invalid/synthetic", duration:900, currentTime:12,
    paused:false, ended:false, seekable:{length:1,start:() => 5,end:() => 890},
    play:async function() { this.paused = false; }, pause() { this.paused = true; }, ...patch};
}

test("bounded snapshot contains timing/correlation, never source URL or title", async t => {
  setup(t, [media()]);
  const state = await playerMedia();
  assert.match(state.media_id, /^[0-9a-f]{32}$/);
  assert.deepEqual(Object.keys(state).sort(), ["can_seek","duration","media_id","playing","position"]);
  assert.equal(state.position, 12); assert.equal(state.can_seek,true);
});

test("seek requires exact current element/source identity, deadline and actual seekable range", async t => {
  const element = media(); setup(t, [element]);
  const state = await playerMedia();
  const expiry = Date.now() + 5000;
  assert.equal(await playerMedia("seek", "b".repeat(32), 30, expiry), null);
  assert.equal(await playerMedia("seek", state.media_id, 1, expiry), null);
  assert.equal(await playerMedia("seek", state.media_id, 30, Date.now() - 1), null);
  assert.equal(await playerMedia("seek", state.media_id, 30, Date.now() + 10000), null);
  assert.equal(element.currentTime, 12);
  assert.equal((await playerMedia("seek", state.media_id, 30, expiry)).position,30);
  element.currentSrc = "https://example.invalid/new-synthetic";
  assert.equal(await playerMedia("seek", state.media_id, 40, expiry),null);
  assert.equal(element.currentTime,30);
});

test("explicit pause/play targets one element, keeps paused timing and never toggles", async t => {
  const element = media(); setup(t, [element]);
  const state = await playerMedia();
  assert.equal((await playerMedia("pause", state.media_id, null, Date.now()+5000)).playing,false);
  assert.equal((await playerMedia()).media_id,state.media_id);
  assert.equal((await playerMedia("play", state.media_id, null, Date.now()+5000)).playing,true);
  assert.equal(await playerMedia("toggle",state.media_id,null,Date.now()+5000),null);
});

test("ambiguous players, live/invalid timing and excessive DOM media fail closed", async t => {
  const elements = setup(t, [media(),media()]);
  assert.equal(await playerMedia(),null);
  elements.splice(0,2,media({duration:Infinity})); assert.equal(await playerMedia(),null);
  elements.splice(0,1,media({currentTime:NaN})); assert.equal(await playerMedia(),null);
  elements.splice(0,1,...Array.from({length:65},() => media())); assert.equal(await playerMedia(),null);
});

test("replacement element and missing seekable ranges never inherit previous seek authority", async t => {
  const elements = setup(t,[media()]);
  const state = await playerMedia();
  elements[0] = media({seekable:{length:0}});
  const replaced = await playerMedia();
  assert.notEqual(replaced.media_id,state.media_id); assert.equal(replaced.can_seek,false);
  assert.equal(await playerMedia("seek",state.media_id,40,Date.now()+5000),null);
  assert.equal(await playerMedia("seek",replaced.media_id,40,Date.now()+5000),null);
});
