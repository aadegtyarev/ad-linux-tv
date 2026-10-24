"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const layout = require("../src/ad_linux_tv/static/layout.js");

test("pagination covers all items and handles empty lists", () => {
  const entries = Array.from({length: 13}, (_, index) => index);
  assert.equal(layout.pageCount(entries.length, 12), 2);
  assert.deepEqual(layout.pageItems(entries, 1, 12), [12]);
  assert.equal(layout.pageCount(0, 12), 1);
  assert.deepEqual(layout.pageItems([], 0, 12), []);
});

test("directional focus wraps and handles a short final row", () => {
  assert.equal(layout.moveFocus(0, "left", 5, 3), 4);
  assert.equal(layout.moveFocus(4, "down", 5, 3), 1);
  assert.equal(layout.moveFocus(1, "up", 5, 3), 4);
  assert.throws(() => layout.moveFocus(0, "diagonal", 5, 3), RangeError);
});
