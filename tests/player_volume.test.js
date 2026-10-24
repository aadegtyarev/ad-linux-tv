"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {playerMediaVolume} = require("../extension/player_volume.js");

test("player volume uses playing HTML media and leaves paused media alone", () => {
  const paused = {paused:true, ended:false, muted:false, volume:0.9};
  const playing = {paused:false, ended:false, muted:false, volume:0.6};
  const previous = global.document;
  global.document = {querySelectorAll:() => [paused, playing]};
  try {
    assert.equal(playerMediaVolume("get", null), 60);
    assert.equal(playerMediaVolume("set", 35), 35);
    assert.equal(playing.volume, 0.35);
    assert.equal(paused.volume, 0.9);
    assert.equal(playerMediaVolume("set", 101), null);
    playing.paused = true;
    assert.equal(playerMediaVolume("get", null), null);
  } finally {
    global.document = previous;
  }
});
