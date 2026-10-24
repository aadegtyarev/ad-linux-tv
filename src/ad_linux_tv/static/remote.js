"use strict";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login");
const loginPanel = document.querySelector("#login-panel");
const controls = document.querySelector("#controls");
const status = document.querySelector("#status");
let csrf = "";
let statusTimer = null;

function say(text, error = false) {
  message.textContent = text;
  message.dataset.error = String(error);
}

function requireLogin() {
  csrf = "";
  if (statusTimer !== null) clearInterval(statusTimer);
  statusTimer = null;
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
    void refreshStatus();
    statusTimer = setInterval(refreshStatus, 1000);
  } catch (_) {
    say("Нет связи с Beelink. Проверьте Wi‑Fi и повторите попытку.", true);
  }
};

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
