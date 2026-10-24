"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {launcher, ready} = require("./helpers/launcher_mock.js");

test("launcher focus uses actual columns and carries arrows across pages", async () => {
  const ui = launcher();
  await ready();
  assert.equal(ui.elements["#tiles"].children.length, 12);
  assert.equal(ui.elements["#page"].textContent, "1 / 3");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "4");
  ui.elements["#next"].onclick();
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "12");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "16");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
});

test("service tile uses configured color and neutral tile stays neutral", async () => {
  const ui = launcher();
  ui.services = [{id:"colored", name:"Colored", color:"#FF6600"}, {id:"plain", name:"Plain"}];
  ui.refresh();
  await ready();
  assert.equal(ui.elements["#tiles"].children[0].properties["--tile-color"], "#FF6600");
  assert.equal(ui.elements["#tiles"].children[0].classList.contains("colored-tile"), true);
  assert.equal(ui.elements["#tiles"].children[1].classList.contains("colored-tile"), false);
});

test("periodic refresh preserves grid focus and skips unchanged DOM replacement", async () => {
  const ui = launcher();
  await ready();
  ui.elements["#tiles"].children[5].focus();
  const selected = ui.doc.activeElement;
  ui.refresh();
  await ready();
  assert.equal(ui.doc.activeElement, selected);
  ui.services = [ui.services[5], ...ui.services.filter((_, index) => index !== 5)];
  ui.refresh();
  await ready();
  assert.equal(ui.doc.activeElement.dataset.serviceId, "svc-5");
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "0");
});

test("services refresh does not clear offline or pending command status", async () => {
  const ui = launcher();
  await ready();
  ui.status = {extension_online:false, pending_commands:1,
    last_command_failure:{outcome:"uncertain", reason:"interrupted"}};
  ui.elements["#config-status"].textContent = "old configuration error";
  ui.refresh();
  await ready();
  assert.equal(ui.elements["#config-status"].textContent, "");
  assert.equal(ui.elements["#bridge-status"].textContent, "Расширение Firefox не подключено.");
  assert.equal(ui.elements["#command-status"].textContent,
    "Команда ожидает ответа Firefox. Последняя команда: uncertain (interrupted).");
});

test("physical tile click still posts Open and pagination stays local", async () => {
  const ui = launcher();
  await ready();
  ui.elements["#tiles"].children[3].click();
  await ready();
  const command = ui.calls.find(call => call.url === "/api/command");
  assert.equal(JSON.parse(command.options.body).service_id, "svc-3");
  ui.elements["#next"].focus();
  ui.elements["#next"].click();
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "12");
});

test("settings is reachable by remote OK and KDE requires a second confirmation", async () => {
  const ui = launcher();
  ui.services = [{id:"svc-0", name:"Service 0"}];
  await ready();
  assert.equal(ui.elements[".pagination"].hidden, true);
  assert.equal(ui.elements["#tiles"].children.length, 1);
  assert.equal(ui.elements["#system-button"].dataset.settings, "true");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowRight", preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.settings, "true");
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  assert.equal(ui.elements["#settings"].hidden, false);
  assert.equal(ui.doc.documentElement.dataset.bridgeServiceId, "");
  for (let i = 0; i < 5; i += 1) ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", preventDefault(){}});
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  assert.equal(ui.elements["#confirm-kde"].hidden, false);
  assert.equal(ui.calls.filter(call => call.url === "/api/system/kde").length, 0);
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowRight", preventDefault(){}});
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  await ready();
  assert.equal(ui.calls.filter(call => call.url === "/api/system/kde").length, 1);
});

test("System audio controls load state and submit selected volume", async () => {
  const ui = launcher({hostname:"127.0.0.1"});
  await ready();
  ui.elements["#system-button"].click();
  await ready();
  assert.equal(ui.elements["#audio-output"].value, "hdmi");
  assert.equal(ui.elements["#audio-volume-value"].textContent, "100%");
  ui.elements["#audio-volume"].value = "45";
  ui.elements["#audio-volume"].onchange();
  await ready();
  const request = ui.calls.find(call => call.url === "/api/audio" && call.options?.method === "POST");
  assert.equal(JSON.parse(request.options.body).volume, 45);
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", preventDefault(){}});
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", preventDefault(){}});
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowLeft", preventDefault(){}});
  await ready();
  const volumes = ui.calls.filter(call => call.url === "/api/audio" && call.options?.method === "POST")
    .map(call => JSON.parse(call.options.body).volume);
  assert.equal(volumes.at(-1), 95);
});

test("System exposes Firefox stream volume when playback is active", async () => {
  const ui = launcher({hostname:"127.0.0.1"});
  ui.audio = {outputs:[{id:"hdmi",name:"HDMI"}],selected:"hdmi",volume:100,muted:false,browser_volume:75};
  ui.elements["#system-button"].click();
  await ready();
  assert.equal(ui.elements["#browser-volume"].disabled, false);
  assert.equal(ui.elements["#browser-volume-value"].textContent, "75%");
  ui.elements["#browser-volume"].value = "60";
  ui.elements["#browser-volume"].onchange();
  await ready();
  assert.equal(ui.calls.some(call => call.url === "/api/audio" &&
    JSON.parse(call.options?.body || "{}").browser_volume === 60), true);
});

test("LAN address change updates both shown address and QR image", async () => {
  const ui = launcher();
  await ready();
  assert.match(ui.elements["#qr"].src, /192\.168\.1\.4/);
  ui.remoteAddress = "http://192.168.1.111:8765/remote";
  ui.refresh();
  await ready();
  assert.equal(ui.elements["#address"].textContent, ui.remoteAddress);
  assert.match(ui.elements["#qr"].src, /192\.168\.1\.111/);
});

test("pairing PIN is requested only by the local TV launcher", async () => {
  const lan = launcher();
  await ready();
  assert.equal(lan.calls.some(call => call.url === "/api/local-pin"), false);
  const local = launcher({hostname:"127.0.0.1"});
  await ready();
  assert.equal(local.elements["#pairing-pin"].textContent, "PIN: 1234");
  assert.equal(local.elements["#pairing-pin"].hidden, false);
  const call = local.calls.find(value => value.url === "/api/local-pin");
  assert.equal(call.options.headers["X-TV-Launcher"], "1");
});
