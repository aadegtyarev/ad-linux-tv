"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {launcher, ready} = require("./helpers/launcher_mock.js");

test("launcher focus uses actual columns and carries arrows across pages", async () => {
  const ui = launcher();
  await ready();
  assert.equal(ui.elements["#tiles"].children.length, 12);
  assert.equal(ui.elements["#page"].textContent, "1 / 3");
  const firstTile = ui.elements["#tiles"].children[0];
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "4");
  assert.equal(ui.elements["#tiles"].children[0], firstTile);
  ui.elements["#next"].onclick();
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "12");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", isTrusted:true, preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "16");
  assert.equal(ui.elements["#page"].textContent, "2 / 3");
});

test("System remains pointer-clickable while arrows and bridge OK select tiles", async () => {
  const ui = launcher();
  await ready();
  const system = ui.elements["#system-button"];
  system.focus();
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowRight", preventDefault(){}});
  assert.equal(ui.doc.activeElement.dataset.serviceIndex, "1");
  system.focus();
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  assert.equal(ui.doc.documentElement.dataset.bridgeServiceId, "svc-1");
  assert.equal(ui.elements["#settings"].hidden, true);
  system.click();
  assert.equal(ui.elements["#settings"].hidden, false);
});

test("TV buttons show immediate touch feedback", async () => {
  const ui = launcher();
  await ready();
  const button = ui.elements["#system-button"];
  ui.doc.dispatchEvent({type:"pointerdown", pointerType:"touch", target:{closest:() => button}});
  assert.equal(button.classList.contains("tv-pressed"), true);
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

test("System opens via F8 and KDE requires a second confirmation", async () => {
  const ui = launcher();
  ui.services = [{id:"svc-0", name:"Service 0"}];
  await ready();
  assert.equal(ui.elements[".pagination"].hidden, true);
  assert.equal(ui.elements["#tiles"].children.length, 1);
  assert.equal(ui.elements["#system-button"].dataset.settings, "true");
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowRight", preventDefault(){}});
  assert.notEqual(ui.doc.activeElement.dataset.settings, "true");
  ui.doc.dispatchEvent({type:"keydown", key:"F8", preventDefault(){}});
  assert.equal(ui.elements["#settings"].hidden, false);
  for (let i = 0; i < 14 && ui.doc.activeElement !== ui.elements["#open-kde"]; i += 1)
    ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", preventDefault(){}});
  assert.equal(ui.doc.activeElement, ui.elements["#open-kde"]);
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

test("System timer presets send loopback request and remain reachable by arrows", async () => {
  const ui = launcher({hostname:"127.0.0.1"});
  await ready();
  ui.doc.dispatchEvent({type:"keydown", key:"F8", preventDefault(){}});
  const timerButton = ui.doc.querySelectorAll("#settings [data-timer]")[1];
  timerButton.click();
  await ready();
  const request = ui.calls.find(call => call.url === "/api/display-timer" && call.options?.method === "POST");
  assert.equal(JSON.parse(request.options.body).minutes, 15);
  assert.equal(ui.elements["#settings"].hidden, false);
});

test("System sound check stays in System and does not open KDE", async () => {
  const ui = launcher({hostname:"127.0.0.1"});
  ui.elements["#system-button"].click();
  await ready();
  ui.elements["#audio-test"].click();
  await ready();
  assert.equal(ui.elements["#confirm-kde"].hidden, true);
  assert.equal(ui.calls.filter(call => call.url === "/api/system/kde").length, 0);
  const sample = ui.calls.find(call => call.url === "/api/audio" &&
    JSON.parse(call.options?.body || "{}").test === true);
  assert.ok(sample);
});

test("System shows all three sound levels without changing them on refresh", async () => {
  const ui = launcher({hostname:"127.0.0.1"});
  ui.audio = {outputs:[{id:"hdmi",name:"HDMI"}],selected:"hdmi",volume:100,muted:false,browser_volume:75};
  ui.elements["#system-button"].click();
  await ready();
  const html = fs.readFileSync("src/ad_linux_tv/static/index.html", "utf8");
  assert.equal((html.match(/type="range"/g) || []).length, 4);
  assert.equal(ui.elements["#audio-volume"].value, 100);
  assert.equal(ui.elements["#tv-browser-volume"].value, 100);
  assert.equal(ui.calls.some(call => call.url === "/api/audio" &&
    JSON.parse(call.options?.body || "{}").browser_volume !== undefined), false);
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
  const open = launcher({hostname:"127.0.0.1", pinRequired:false});
  await ready();
  assert.equal(open.elements["#pairing-pin"].textContent, "PIN не нужен");
});
