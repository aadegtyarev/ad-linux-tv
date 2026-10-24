"use strict";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login");
const loginPanel = document.querySelector("#login-panel");
const controls = document.querySelector("#controls");
const status = document.querySelector("#status");
let csrf = "";
let statusTimer = null;
let browserService = null;
const audioOutput = document.querySelector("#audio-output");
const audioVolume = document.querySelector("#audio-volume");
const browserVolume = document.querySelector("#browser-volume");
const audioStatus = document.querySelector("#audio-status");
let audioTimer = null;
let audioDragging = false;

function showAudio(state) {
  const names = state.outputs.map(output => output.id).join("\n");
  if (audioOutput.dataset.outputs !== names) {
    audioOutput.replaceChildren();
    for (const output of state.outputs) {
      const option = document.createElement("option");
      option.value = output.id;
      option.textContent = output.name;
      audioOutput.append(option);
    }
    audioOutput.dataset.outputs = names;
  }
  audioOutput.value = state.selected;
  audioVolume.value = state.volume;
  document.querySelector("#audio-volume-value").textContent = `${state.volume}%`;
  const browserActive = state.browser_volume != null;
  browserVolume.disabled = !browserActive;
  if (browserActive) browserVolume.value = state.browser_volume;
  document.querySelector("#browser-volume-value").textContent = browserActive ? `${state.browser_volume}%` : "—";
  document.querySelector("#browser-volume-hint").hidden = browserActive;
  document.querySelector("#audio-mute").textContent = state.muted ? "Включить звук" : "Выключить звук";
  document.querySelector("#audio-mute").dataset.muted = String(state.muted);
  audioStatus.textContent = "";
}

async function refreshAudio() {
  try {
    const response = await fetch("/api/audio");
    if (response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("audio unavailable");
    showAudio(await response.json());
  } catch (_) {
    audioStatus.textContent = "Звук недоступен. Проверьте подключение выхода и повторите.";
  }
}

async function changeAudio(action) {
  try {
    const response = await fetch("/api/audio", {
      method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(action),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("audio change failed");
    showAudio(await response.json());
  } catch (_) {
    await refreshAudio();
    audioStatus.textContent = "Не удалось изменить звук. Проверьте выход и повторите.";
  }
}

function say(text, error = false) {
  message.textContent = text;
  message.dataset.error = String(error);
}

function requireLogin() {
  csrf = "";
  if (statusTimer !== null) clearInterval(statusTimer);
  statusTimer = null;
  if (audioTimer !== null) clearInterval(audioTimer);
  audioTimer = null;
  controls.hidden = true;
  loginPanel.hidden = false;
  say("Сеанс пульта истёк. Введите PIN ещё раз.", true);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const value = await response.json();
    const messages = [value.extension_online ? "Firefox подключён." : "Firefox не подключён. Подождите или перезапустите ТВ-режим."];
    if (value.pending_commands) messages.push("Команда выполняется…");
    if (value.last_command_failure) messages.push("Последняя команда не выполнена. Нажмите ещё раз.");
    status.textContent = messages.join(" ");
    status.dataset.online = String(value.extension_online);
  } catch (_) {
    status.textContent = "Нет связи с Beelink. Проверьте сеть и повторите попытку.";
    status.dataset.online = "false";
  }
}

async function post(path, body, success) {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(body),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (response.status === 503) return say("Управление сейчас недоступно. Подождите несколько секунд и повторите.", true);
    if (!response.ok) return say(`Не удалось выполнить действие (${response.status}). Повторите попытку.`, true);
    say(success);
    void refreshStatus();
    return true;
  } catch (_) {
    say("Нет связи с Beelink. Проверьте Wi‑Fi и повторите попытку.", true);
  }
  return false;
}

loginForm.onsubmit = async event => {
  event.preventDefault();
  const pin = document.querySelector("#pin").value;
  try {
    const response = await fetch("/api/login", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({pin}),
    });
    if (!response.ok) {
      say(response.status === 429 ? "Слишком много попыток. Подождите и попробуйте снова." : "Неверный PIN. Попробуйте ещё раз.", true);
      return;
    }
    csrf = (await response.json()).csrf;
    document.querySelector("#pin").value = "";
    const responseServices = await fetch("/api/services");
    if (!responseServices.ok) throw new Error("service list unavailable");
    const data = await responseServices.json();
    browserService = data.services.find(service => service.id === "browser")?.id || null;
    const select = document.querySelector("#services");
    select.replaceChildren();
    for (const service of data.services) {
      const option = document.createElement("option");
      option.value = service.id;
      option.textContent = service.name;
      select.append(option);
    }
    loginPanel.hidden = true;
    controls.hidden = false;
    say("Телефон подключён.");
    void refreshAudio();
    void refreshStatus();
    statusTimer = setInterval(refreshStatus, 1000);
    audioTimer = setInterval(() => { if (!audioDragging) void refreshAudio(); }, 5000);
  } catch (_) {
    say("Нет связи с Beelink. Проверьте Wi‑Fi и повторите попытку.", true);
  }
};

document.querySelector("#audio-refresh").onclick = refreshAudio;
audioOutput.onchange = () => changeAudio({output: audioOutput.value});
for (const slider of [audioVolume, browserVolume]) {
  slider.addEventListener("pointerdown", () => { audioDragging = true; });
  slider.addEventListener("pointerup", () => { audioDragging = false; });
  slider.addEventListener("pointercancel", () => { audioDragging = false; });
}
audioVolume.oninput = () => {
  document.querySelector("#audio-volume-value").textContent = `${audioVolume.value}%`;
};
audioVolume.onchange = () => changeAudio({volume: Number(audioVolume.value)});
browserVolume.oninput = () => {
  document.querySelector("#browser-volume-value").textContent = `${browserVolume.value}%`;
};
browserVolume.onchange = () => changeAudio({browser_volume: Number(browserVolume.value)});
document.querySelector("#audio-mute").onclick = () =>
  changeAudio({muted: document.querySelector("#audio-mute").dataset.muted !== "true"});

document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => post("/api/command", {command: button.dataset.c}, "Команда отправлена.");
});
document.querySelector("#open").onclick = () =>
  post("/api/command", {command: "open", service_id: document.querySelector("#services").value}, "Открываем сервис…");
document.querySelector("#text-form").onsubmit = async event => {
  event.preventDefault();
  const input = document.querySelector("#remote-text");
  if (!input.value) return;
  if (await post("/api/input", {text: input.value}, "Текст введён.")) input.value = "";
};
document.querySelector("#url-form").onsubmit = async event => {
  event.preventDefault();
  const input = document.querySelector("#remote-url");
  const raw = input.value.trim();
  if (!raw) return;
  const address = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const parsed = new URL(address);
    if (!/^https?:$/.test(parsed.protocol) || !parsed.hostname || address.length > 512) throw new Error("invalid URL");
  } catch (_) {
    return say("Введите адрес сайта, например example.com.", true);
  }
  if (!browserService) return say("Плитка «Браузер» не настроена на Beelink.", true);
  if (!await post("/api/command", {command: "open", service_id: browserService}, "Открываем Браузер…")) return;
  let ready = false;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 400));
    try {
      const response = await fetch("/api/status");
      if (!response.ok) throw new Error("status unavailable");
      const state = await response.json();
      if (state.extension_online && state.pending_commands === 0) { ready = true; break; }
    } catch (_) { break; }
  }
  if (!ready) return say("Браузер не открылся. Проверьте соединение с Firefox и повторите.", true);
  await new Promise(resolve => setTimeout(resolve, 500));
  if (!await post("/api/input", {key: "address"}, "Адресная строка выбрана.")) return;
  if (!await post("/api/input", {text: address}, "Адрес введён.")) return;
  if (await post("/api/input", {key: "enter"}, "Открываем сайт…")) input.value = "";
};
document.querySelector("#key-backspace").onclick = () =>
  post("/api/input", {key: "backspace"}, "Символ удалён.");
document.querySelector("#key-enter").onclick = () =>
  post("/api/input", {key: "enter"}, "Enter отправлен.");
document.querySelector("#key-tab").onclick = () =>
  post("/api/input", {key: "tab"}, "Выбрано следующее поле.");
document.querySelector("#key-shift-tab").onclick = () =>
  post("/api/input", {key: "shift-tab"}, "Выбрано предыдущее поле.");
document.querySelector("#key-address").onclick = () =>
  post("/api/input", {key: "address"}, "Адресная строка выбрана.");
