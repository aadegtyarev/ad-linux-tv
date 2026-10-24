"use strict";
const configStatus = document.querySelector("#config-status");
const bridgeStatus = document.querySelector("#bridge-status");
const commandStatus = document.querySelector("#command-status");
const settings = document.querySelector("#settings");
const home = document.querySelector("#home");
const confirmation = document.querySelector("#confirm-kde");
const systemStatus = document.querySelector("#system-status");
const settingsActions = [document.querySelector("#settings-back"), document.querySelector("#open-kde")];
const confirmActions = [document.querySelector("#cancel-kde"), document.querySelector("#confirm-kde-yes")];

function openSettings() {
  home.hidden = true;
  settings.hidden = false;
  confirmation.hidden = true;
  systemStatus.textContent = "";
  settingsActions[0].focus();
}

function closeSettings() {
  settings.hidden = true;
  home.hidden = false;
  confirmation.hidden = true;
  document.querySelector('[data-settings="true"]')?.focus();
}

settingsActions[0].onclick = closeSettings;
settingsActions[1].onclick = () => {
  confirmation.hidden = false;
  confirmActions[0].focus();
};
confirmActions[0].onclick = () => {
  confirmation.hidden = true;
  settingsActions[0].focus();
};
confirmActions[1].onclick = async () => {
  confirmActions[1].disabled = true;
  systemStatus.textContent = "Открываем KDE…";
  try {
    const response = await fetch("/api/system/kde", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
    });
    if (!response.ok) throw new Error(`Ошибка переключения (${response.status}).`);
  } catch (error) {
    systemStatus.textContent = error.message;
  } finally {
    confirmActions[1].disabled = false;
  }
};

document.addEventListener("keydown", event => {
  if (settings.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    if (confirmation.hidden) closeSettings();
    else confirmActions[0].click();
    return;
  }
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const actions = confirmation.hidden ? settingsActions : confirmActions;
  const index = actions.indexOf(document.activeElement);
  actions[index === 0 ? 1 : 0].focus();
});

const ui = createLauncherUI(send, openSettings);
document.addEventListener("ad-linux-tv-select-for-bridge", () => {
  if (!settings.hidden) {
    const actions = confirmation.hidden ? settingsActions : confirmActions;
    const focused = actions.includes(document.activeElement) ? document.activeElement : actions[0];
    focused.click();
    document.documentElement.dataset.bridgeServiceId = "";
  } else document.documentElement.dataset.bridgeServiceId = ui.selectForBridge() || "";
});

async function load() {
  try {
    const response = await fetch("/api/services");
    if (!response.ok) throw new Error("сервер недоступен");
    const data = await response.json();
    ui.update(data.services, data.page_size);
    configStatus.textContent = "";
    document.querySelector("#address").textContent = data.remote_address ||
      "Адрес в локальной сети не найден.";
    const qr = document.querySelector("#qr");
    qr.src = data.remote_address ? "/api/qr" : "";
    qr.hidden = !data.remote_address;
  } catch (cause) {
    configStatus.textContent = `Ошибка конфигурации: ${cause.message}`;
  }
}

async function checkStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("статус недоступен");
    const status = await response.json();
    bridgeStatus.textContent = status.extension_online
      ? "Расширение Firefox подключено." : "Расширение Firefox не подключено.";
    const messages = [];
    if (status.pending_commands) messages.push("Команда ожидает ответа Firefox.");
    if (status.last_command_failure) {
      messages.push(`Последняя команда: ${status.last_command_failure.outcome} (${status.last_command_failure.reason}).`);
    }
    commandStatus.textContent = messages.join(" ");
  } catch (_) {
    bridgeStatus.textContent = "Соединение с сервером потеряно; перезапустите ТВ-режим.";
  }
}

async function send(command, service_id) {
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command, service_id}),
    });
    if (!response.ok) commandStatus.textContent = `Команда не выполнена (${response.status}).`;
    else void checkStatus();
  } catch (_) {
    commandStatus.textContent = "Связь с сервером потеряна; повторите команду.";
  }
}

load();
checkStatus();
setInterval(() => {
  checkStatus();
  load();
}, 5000);
