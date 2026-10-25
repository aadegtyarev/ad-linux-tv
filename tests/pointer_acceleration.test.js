"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const context = vm.createContext({});
vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/pointer_acceleration.js", "utf8"), context);
const make = level => vm.runInContext(`new PointerAcceleration(${level})`, context);

test("zero acceleration preserves the previous constant mapping", () => {
  const motion = make(0);
  assert.equal(motion.move(10, 2, 10).dx, 30);
  assert.equal(motion.move(10, 2, 20).dy, 6);
});

test("fast sustained movement gains distance but a pause and reversal reset it", () => {
  const motion = make(50);
  assert.equal(motion.move(10, 0, 10).dx, 30);
  const fast = motion.move(15, 0, 20).dx;
  assert.ok(fast > 45 && fast <= 90);
  assert.equal(motion.move(10, 0, 200).dx, 30);
  motion.move(15, 0, 210);
  assert.equal(motion.move(-10, 0, 220).dx, -30);
});
