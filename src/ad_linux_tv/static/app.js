"use strict";
const configStatus = document.querySelector("#config-status");
const bridgeStatus = document.querySelector("#bridge-status");
const commandStatus = document.querySelector("#command-status");
const ui = createLauncherUI(send);
document.addEventListener("ad-linux-tv-select-for-bridge", () => {
  document.documentElement.dataset.bridgeServiceId = ui.selectForBridge() || "";
});

async function load() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("Server unavailable");
    const data = await response.json();
    ui.update(data.services, data.page_size);
    configStatus.textContent = "";
    document.querySelector("#address").textContent = data.remote_address ||
      "No LAN listener is available; choose a LAN bind address.";
    const qr = document.querySelector("#qr");
    qr.src = data.remote_address ? "/api/qr" : "";
    qr.hidden = !data.remote_address;
  } catch (cause) {
    configStatus.textContent = `Configuration error: ${cause.message}`;
  }
}

async function checkStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const status = await response.json();
    bridgeStatus.textContent = status.extension_online
      ? "Firefox bridge online." : "Firefox bridge offline; check the extension.";
    const messages = [];
    if (status.pending_commands) messages.push("Browser command awaiting Firefox acknowledgement.");
    if (status.last_command_failure) {
      messages.push(`Last browser command ${status.last_command_failure.outcome} (${status.last_command_failure.reason}).`);
    }
    commandStatus.textContent = messages.join(" ");
  } catch (_) {
    bridgeStatus.textContent = "Server connection lost; restart ad-linux-tv.";
  }
}

async function send(command, service_id) {
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command, service_id}),
    });
    if (!response.ok) commandStatus.textContent = `Command failed (${response.status}).`;
    else void checkStatus();
  } catch (_) {
    commandStatus.textContent = "Server connection lost; retry the command.";
  }
}

load();
checkStatus();
setInterval(() => {
  checkStatus();
  load();
}, 5000);
