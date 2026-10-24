"use strict";
const message = document.querySelector("#message");
const controls = document.querySelector("#controls");
let csrf = "";

async function post(command, service_id) {
  const response = await fetch("/api/command", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: JSON.stringify({command, service_id}),
  });
  if (!response.ok) message.textContent = `Command failed (${response.status})`;
}

document.querySelector("#login").onsubmit = async event => {
  event.preventDefault();
  const pin = event.target.querySelector("input").value;
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
  event.target.hidden = true;
  controls.hidden = false;
  const data = await (await fetch("/api/services")).json();
  for (const service of data.services) {
    const option = document.createElement("option");
    option.value = service.id;
    option.textContent = service.name;
    document.querySelector("#services").append(option);
  }
};

document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => post(button.dataset.c);
});
document.querySelector("#open").onclick = () =>
  post("open", document.querySelector("#services").value);
