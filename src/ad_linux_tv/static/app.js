"use strict";
let services = [];
let size = 12;
let page = 0;
let focus = 0;
const tiles = document.querySelector("#tiles");
const error = document.querySelector("#error");

async function load() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("Server unavailable");
    const data = await response.json();
    services = data.services;
    size = data.page_size;
    error.textContent = "";
    render();
    document.querySelector("#address").textContent = data.remote_address ||
      "No reachable LAN address; check bind/network configuration.";
    const qr = document.querySelector("#qr");
    qr.src = "/api/qr";
    qr.hidden = false;
  } catch (cause) {
    error.textContent = `Configuration/connection error: ${cause.message}`;
  }
}

function render() {
  const subset = MediaLayout.pageItems(services, page, size);
  tiles.replaceChildren();
  subset.forEach((service, index) => {
    const button = document.createElement("button");
    button.textContent = service.name;
    button.onclick = () => send("open", service.id);
    button.tabIndex = index === focus ? 0 : -1;
    tiles.append(button);
  });
  document.querySelector("#page").textContent =
    `${page + 1} / ${MediaLayout.pageCount(services.length, size)}`;
}

async function checkBridge() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!status.extension_online) error.textContent = "Firefox bridge offline; check the extension.";
    else if (error.textContent.startsWith("Firefox bridge offline")) error.textContent = "";
  } catch (_) {
    error.textContent = "Server connection lost; restart ad-linux-tv.";
  }
}

async function send(command, service_id) {
  const response = await fetch("/api/command", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({command, service_id}),
  });
  if (!response.ok) error.textContent = `Browser bridge unavailable (${response.status})`;
}

document.addEventListener("keydown", event => {
  const columns = Math.max(1, Math.floor(innerWidth / 260));
  const direction = {
    ArrowRight: "right", ArrowLeft: "left", ArrowDown: "down", ArrowUp: "up",
  }[event.key];
  if (event.key === "Enter") {
    event.preventDefault();
    tiles.children[focus]?.click();
    return;
  }
  if (!direction || !services.length) return;
  event.preventDefault();
  const count = MediaLayout.pageItems(services, page, size).length;
  focus = MediaLayout.moveFocus(focus, direction, count, columns);
  tiles.children[focus]?.focus();
});

document.querySelector("#next").onclick = () => {
  page = (page + 1) % MediaLayout.pageCount(services.length, size);
  focus = 0;
  render();
};
document.querySelector("#prev").onclick = () => {
  page = (page + MediaLayout.pageCount(services.length, size) - 1) %
    MediaLayout.pageCount(services.length, size);
  focus = 0;
  render();
};
load();
checkBridge();
setInterval(() => {
  checkBridge();
  if (!services.length) load();
}, 5000);
