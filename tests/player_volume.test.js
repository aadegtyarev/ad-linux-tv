"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {playerMediaVolume, pinMediaVolume} = require("../extension/player_volume.js");

test("player volume uses playing HTML media and leaves paused media alone", () => {
  const paused = {paused:true, ended:false, muted:false, volume:0.9};
  const playing = {paused:false, ended:false, muted:false, volume:0.6,
    pause() { this.paused = true; }};
  const previous = global.document;
  global.document = {querySelectorAll:() => [paused, playing]};
  try {
    assert.equal(playerMediaVolume("get", null), 60);
    assert.equal(playerMediaVolume("set", 35), 35);
    assert.equal(playing.volume, 0.35);
    assert.equal(paused.volume, 0.9);
    assert.equal(playerMediaVolume("set", 101), null);
    assert.equal(playerMediaVolume("pause", null), 35);
    assert.equal(playing.paused, true);
    assert.equal(playerMediaVolume("get", null), null);
  } finally {
    global.document = previous;
  }
});

test("managed page volume pin follows playback and later site volume changes", () => {
  const playing = {localName:"video",paused:false,ended:false,volume:0.4};
  const paused = {localName:"audio",paused:true,ended:false,volume:0.2};
  const listeners = {};
  const previous = global.document;
  global.document = {
    querySelectorAll:() => [playing, paused],
    addEventListener:(name, callback) => { listeners[name] ||= []; listeners[name].push(callback); },
  };
  try {
    pinMediaVolume();
    assert.equal(playing.volume, 1);
    assert.equal(paused.volume, 0.2);
    paused.paused = false;
    listeners.play[0]({target:paused});
    assert.equal(paused.volume, 1);
    playing.volume = 0.5;
    listeners.volumechange[0]({target:playing});
    assert.equal(playing.volume, 1);
    pinMediaVolume();
    assert.equal(listeners.play.length, 1);
  } finally {
    global.document = previous;
  }
});
