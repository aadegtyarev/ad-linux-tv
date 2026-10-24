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
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowDown", preventDefault(){}});
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  assert.equal(ui.elements["#confirm-kde"].hidden, false);
  assert.equal(ui.calls.filter(call => call.url === "/api/system/kde").length, 0);
  ui.doc.dispatchEvent({type:"keydown", key:"ArrowRight", preventDefault(){}});
  ui.doc.dispatchEvent({type:"ad-linux-tv-select-for-bridge"});
  await ready();
  assert.equal(ui.calls.filter(call => call.url === "/api/system/kde").length, 1);
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
