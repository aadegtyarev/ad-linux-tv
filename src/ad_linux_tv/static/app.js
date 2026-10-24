"use strict";
let services = [], size = 12, page = 0, focus = 0;
const tiles = document.querySelector("#tiles"), error = document.querySelector("#error");
async function load() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("Server unavailable");
    const data = await response.json(); services = data.services; size = data.page_size; render();
    document.querySelector("#address").textContent = `${location.hostname}:${location.port}/remote`;
    const qr = document.querySelector("#qr"); qr.src = "/api/qr"; qr.hidden = false;
  } catch (e) { error.textContent = `Configuration/connection error: ${e.message}`; }
}
function render() {
  const subset = services.slice(page * size, (page + 1) * size); tiles.replaceChildren();
  subset.forEach((s, i) => { const b = document.createElement("button"); b.textContent = s.name; b.onclick = () => send("open", s.id); b.tabIndex = i === focus ? 0 : -1; tiles.append(b); });
  document.querySelector("#page").textContent = `${page + 1} / ${Math.max(1, Math.ceil(services.length / size))}`;
}
async function send(command, service_id) { await fetch("/api/command", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command,service_id})}); }
document.addEventListener("keydown", e => { const cols = Math.max(1, Math.floor(innerWidth / 260)); if (e.key === "ArrowRight") focus++; else if (e.key === "ArrowLeft") focus--; else if (e.key === "ArrowDown") focus += cols; else if (e.key === "ArrowUp") focus -= cols; else if (e.key === "Enter") { e.preventDefault(); tiles.children[focus]?.click(); return; } else return; e.preventDefault(); const max = Math.min(size, services.length - page * size); focus = (focus + max) % max; tiles.children[focus]?.focus(); });
document.querySelector("#next").onclick = () => { page = (page + 1) % Math.ceil(services.length / size); focus = 0; render(); };
document.querySelector("#prev").onclick = () => { page = (page + Math.ceil(services.length / size) - 1) % Math.ceil(services.length / size); focus = 0; render(); };
load();
