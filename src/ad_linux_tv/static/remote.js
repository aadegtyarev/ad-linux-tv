"use strict";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login");
const controls = document.querySelector("#controls");
let csrf = "";

function requireLogin() {
  csrf = "";
  controls.hidden = true;
  loginForm.hidden = false;
  message.textContent = "Session expired; log in again.";
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
  } catch (_) {
    message.textContent = "Connection lost; check the TV server and retry.";
  }
};

document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => post(button.dataset.c);
});
document.querySelector("#open").onclick = () =>
  post("open", document.querySelector("#services").value);
