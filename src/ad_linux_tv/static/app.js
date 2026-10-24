"use strict";
const error = document.querySelector("#error");
const ui = createLauncherUI(send);

async function load() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("Server unavailable");
    const data = await response.json();
    ui.update(data.services, data.page_size);
    error.textContent = "";
    document.querySelector("#address").textContent = data.remote_address ||
      "No LAN listener is available; choose a LAN bind address.";
    const qr = document.querySelector("#qr");
    qr.src = data.remote_address ? "/api/qr" : "";
    qr.hidden = !data.remote_address;
  } catch (cause) {
    error.textContent = `Configuration/connection error: ${cause.message}`;
  }
}

async function checkBridge() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const status = await response.json();
    if (status.pending_commands) error.textContent = "Browser command awaiting Firefox acknowledgement.";
    else if (!status.extension_online) error.textContent = "Firefox bridge offline; check the extension.";
    else if (error.textContent.startsWith("Firefox bridge offline") ||
             error.textContent.startsWith("Browser command awaiting")) error.textContent = "";
  } catch (_) {
    error.textContent = "Server connection lost; restart ad-linux-tv.";
  }
}

async function send(command, service_id) {
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command, service_id}),
    });
    if (!response.ok) error.textContent = `Browser bridge unavailable (${response.status})`;
  } catch (_) {
    error.textContent = "Server connection lost; restart ad-linux-tv.";
  }
}

load();
checkBridge();
setInterval(() => {
  checkBridge();
  load();
}, 5000);
