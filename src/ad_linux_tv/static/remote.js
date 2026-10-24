"use strict";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login");
const controls = document.querySelector("#controls");
const status = document.querySelector("#status");
let csrf = "";
let statusTimer = null;

function requireLogin() {
  csrf = "";
  if (statusTimer !== null) clearInterval(statusTimer);
  statusTimer = null;
  controls.hidden = true;
  loginForm.hidden = false;
  message.textContent = "Session expired; log in again.";
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const value = await response.json();
    const messages = [value.extension_online ? "Firefox bridge online." : "Firefox bridge offline."];
    if (value.pending_commands) messages.push("Command awaiting Firefox acknowledgement.");
    if (value.last_command_failure) {
      messages.push(`Last command ${value.last_command_failure.outcome} (${value.last_command_failure.reason}).`);
    }
    status.textContent = messages.join(" ");
  } catch (_) {
    status.textContent = "TV server unavailable.";
  }
}

async function post(command, service_id) {
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify({command, service_id}),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) message.textContent = `Command failed (${response.status})`;
    else message.textContent = "Command accepted.";
  } catch (_) {
    message.textContent = "Connection lost; check the TV server and retry.";
  }
}

loginForm.onsubmit = async event => {
  event.preventDefault();
  const pin = event.target.querySelector("input").value;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pin}),
    });
    if (!response.ok) {
      message.textContent = "Login failed or temporarily locked";
      return;
    }
    csrf = (await response.json()).csrf;
    const responseServices = await fetch("/api/services");
    if (!responseServices.ok) throw new Error("service list unavailable");
    const data = await responseServices.json();
    const select = document.querySelector("#services");
    select.replaceChildren();
    for (const service of data.services) {
      const option = document.createElement("option");
      option.value = service.id;
      option.textContent = service.name;
      select.append(option);
    }
    loginForm.hidden = true;
    controls.hidden = false;
    message.textContent = "";
    void refreshStatus();
    statusTimer = setInterval(refreshStatus, 1000);
  } catch (_) {
    message.textContent = "Connection lost; check the TV server and retry.";
  }
};

document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => post(button.dataset.c);
});
document.querySelector("#open").onclick = () =>
  post("open", document.querySelector("#services").value);
