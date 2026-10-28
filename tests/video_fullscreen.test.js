"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {createTabController} = require("../extension/tabs.js");
const {LAUNCHER} = require("../extension/tab_storage.js");
const {browserMock} = require("./helpers/browser_mock.js");

async function owned(frames) {
  const mock = browserMock([{id:1,windowId:1,url:LAUNCHER}]);
  const controller = createTabController(mock.api,mock.fetcher);
  await controller.restore();
  await controller.execute({id:"fullscreen-open",command:"open",service_id:"one"});
  mock.setScriptingResults(options => {
    const action = options.args?.[0];
    if (action === "probe") return frames;
    if (action === "enter") return [{frameId:options.target.frameIds[0], result:true}];
    if (action === "exit") return [{frameId:0, result:true}];
    return [];
  });
  return {mock,controller};
}
const actions = mock => mock.calls.filter(call => call[0] === "script" && call[1].args)
  .map(call => [call[1].args[0], call[1].target.frameIds || "all"]);

test("button fullscreens the best-scoring video frame only on request", async () => {
  const {mock,controller} = await owned([
    {frameId:0,result:{fullscreen:false,score:0}},
    {frameId:7,result:{fullscreen:false,score:5000}},
    {frameId:9,result:{fullscreen:false,score:300}},
  ]);
  assert.equal((await controller.execute({id:"fullscreen-one",command:"fullscreen"})).outcome,"completed");
  assert.deepEqual(actions(mock).filter(([action]) => action !== "status"),
    [["probe","all"],["enter",[7]]]);
});

test("the same button leaves fullscreen when any frame is fullscreen", async () => {
  const {mock,controller} = await owned([
    {frameId:0,result:{fullscreen:true,score:0}},
    {frameId:7,result:{fullscreen:true,score:5000}},
  ]);
  assert.equal((await controller.execute({id:"fullscreen-two",command:"fullscreen"})).outcome,"completed");
  assert.deepEqual(actions(mock).filter(([action]) => action !== "status"),
    [["probe","all"],["exit",[0]]]);
});

test("no visible video is reported without entering fullscreen", async () => {
  const {mock,controller} = await owned([{frameId:0,result:{fullscreen:false,score:0}}]);
  assert.equal((await controller.execute({id:"fullscreen-three",command:"fullscreen"})).reason,"no_media");
  assert.equal(actions(mock).some(([action]) => action === "enter"),false);
});

function page(paused = false) {
  const requested = [];
  const box = (left, top, width, height) => () => ({left, top, width, height});
  const body = {getBoundingClientRect:box(0,0,1920,3000)};
  const column = {getBoundingClientRect:box(0,60,1920,1400), parentElement:body};
  const player = {getBoundingClientRect:box(40,80,1280,720), parentElement:column,
    requestFullscreen:async () => requested.push("player")};
  const video = {tagName:"VIDEO", getBoundingClientRect:box(40,80,1280,720), parentElement:player, paused,
    ended:false, requestFullscreen:async () => requested.push("video")};
  const preview = {tagName:"VIDEO", getBoundingClientRect:box(0,900,1600,900), parentElement:body, paused:true,
    ended:false, requestFullscreen:async () => requested.push("preview")};
  const document = {body, documentElement:{}, fullscreenElement:null,
    querySelectorAll:() => [preview, video], exitFullscreen:async () => requested.push("exit")};
  const context = {document, getComputedStyle:() => ({visibility:"visible"}), module:{exports:{}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("extension/player_media.js","utf8"), context);
  return {fullscreen:context.module.exports.videoFullscreen, requested, document};
}

test("page function fullscreens the playing video's player box and exits on demand", async () => {
  const view = page(false);
  const probe = await view.fullscreen("probe");
  assert.equal(probe.fullscreen,false);
  assert.equal(probe.score,1280 * 720 * 4);
  assert.equal(await view.fullscreen("enter"),true);
  assert.deepEqual(view.requested,["player"]);
  assert.equal(await view.fullscreen("exit"),false);
  view.document.fullscreenElement = {};
  assert.equal(await view.fullscreen("exit"),true);
  assert.deepEqual(view.requested,["player","exit"]);
  assert.equal(await view.fullscreen("seek"),null);
});

test("page function finds a video inside a shadow root and fullscreens its host player", async () => {
  const requested = [];
  const box = (left, top, width, height) => () => ({left, top, width, height});
  const body = {getBoundingClientRect:box(0,0,1920,3000)};
  const column = {getBoundingClientRect:box(0,60,1920,1400), parentElement:body};
  const host = {tagName:"VK-VIDEO-PLAYER", getBoundingClientRect:box(84,64,1447,796),
    parentElement:column, requestFullscreen:async () => requested.push("host")};
  const wrapper = {tagName:"DIV", getBoundingClientRect:box(84,64,1447,796), parentElement:null,
    getRootNode:() => ({host}), requestFullscreen:async () => requested.push("wrapper")};
  const video = {tagName:"VIDEO", getBoundingClientRect:box(84,64,1447,796), parentElement:wrapper,
    paused:false, ended:false, requestFullscreen:async () => requested.push("video")};
  host.shadowRoot = {querySelectorAll:() => [wrapper, video]};
  const document = {body, documentElement:{}, fullscreenElement:null, querySelectorAll:() => [host]};
  const context = {document, getComputedStyle:() => ({visibility:"visible"}), module:{exports:{}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("extension/player_media.js","utf8"), context);
  const fullscreen = context.module.exports.videoFullscreen;
  assert.equal((await fullscreen("probe")).score,1447 * 796 * 4);
  assert.equal(await fullscreen("enter"),true);
  assert.deepEqual(requested,["host"]);
});
