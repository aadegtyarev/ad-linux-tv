"use strict";
const configStatus = document.querySelector("#config-status");
const bridgeStatus = document.querySelector("#bridge-status");
const commandStatus = document.querySelector("#command-status");
const settings = document.querySelector("#settings");
const home = document.querySelector("#home");
const confirmation = document.querySelector("#confirm-kde");
const systemStatus = document.querySelector("#system-status");
const audioOutput = document.querySelector("#audio-output");
const audioVolume = document.querySelector("#audio-volume");
const audioStatus = document.querySelector("#audio-status");
const audioMute = document.querySelector("#audio-mute");
const advancedAudio = new AudioLevelsControls("tv", [
  ["browser", "browser_volume"], ["player", "player_volume"],
], changeAudio);
const timerButtons = Array.from(document.querySelectorAll("#settings [data-timer]"));
const tvTimerStatus = document.querySelector("#tv-timer-status");
const tvSettingsRoot = document.querySelector("#tv-settings-controls");
const tvSettingsPanel = tvSettingsRoot ? new SettingsControls(tvSettingsRoot,
  (method, action) => fetch("/api/settings", {
    method, headers: {"Content-Type": "application/json"},
    ...(action ? {body: JSON.stringify(action)} : {}),
  }), () => void loadPairingPin(), state => {
    // The desktop switch exists only on computers with a KDE display manager.
    document.querySelector("#kde-actions").hidden = state.kde_available === false;
  }) : null;
const rangeActions = [audioVolume, ...advancedAudio.sliders(),
  tvSettingsPanel?.field("pointer-acceleration"), tvSettingsPanel?.field("magnifier-scale"),
  tvSettingsPanel?.field("view-zoom")].filter(Boolean);
for (const slider of rangeActions) slider.addEventListener("click", () => slider.focus());
const settingsActions = [document.querySelector("#settings-back"), audioOutput, audioVolume,
  audioMute, document.querySelector("#audio-refresh"),
  document.querySelector("#audio-test"), ...advancedAudio.actions(), ...timerButtons,
  ...(tvSettingsPanel?.actions() || []), document.querySelector("#open-kde")];
const confirmActions = [document.querySelector("#cancel-kde"), document.querySelector("#confirm-kde-yes")];
let currentRemoteAddress = "";
let pressedTvButton = null;
let pressedTvTimer = null;
function flashTvButton(button) {
  if (!button) return;
  if (pressedTvButton && pressedTvButton !== button) pressedTvButton.classList.remove("tv-pressed");
  pressedTvButton = button;
  button.classList.add("tv-pressed");
  if (pressedTvTimer !== null) clearTimeout(pressedTvTimer);
  pressedTvTimer = setTimeout(() => {
    button.classList.remove("tv-pressed");
    pressedTvButton = null;
  }, 360);
}
for (const eventName of ["pointerdown", "click"]) {
  document.addEventListener(eventName, event => {
    flashTvButton(event.target?.closest?.("button"));
  }, true);
}



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
  advancedAudio.render(state);
  document.querySelector("#audio-volume-value").textContent = `${state.volume}%`;
  audioMute.dataset.muted = String(state.muted);
  audioMute.textContent = state.muted ? "Включить звук" : "Выключить звук";
  audioStatus.textContent = "";
}

async function refreshAudio() {
  try {
    const response = await fetch("/api/audio");
    if (!response.ok) throw new Error("audio unavailable");
    showAudio(await response.json());
  } catch (_) {
    audioStatus.textContent = "Звук недоступен. Проверьте подключение выхода и повторите.";
  }
}

async function changeAudio(action) {
  try {
    const response = await fetch("/api/audio", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(action),
    });
    if (!response.ok) throw new Error("audio change failed");
    showAudio(await response.json());
  } catch (_) {
    audioStatus.textContent = "Не удалось изменить звук. Проверьте выход и повторите.";
  }
}

document.querySelector("#audio-refresh").onclick = refreshAudio;
document.querySelector("#audio-test").onclick = async () => {
  audioStatus.textContent = "Проверяем звук…";
  try {
    const response = await fetch("/api/audio", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({test: true}),
    });
    if (!response.ok) throw new Error("audio test failed");
    audioStatus.textContent = "Сигнал отправлен. Если не слышно, проверьте выход и громкость.";
  } catch (_) {
    audioStatus.textContent = "Нет звука. Проверьте выход, громкость и отключение звука.";
  }
};
audioOutput.onchange = () => changeAudio({output: audioOutput.value});
audioVolume.oninput = () => {
  document.querySelector("#audio-volume-value").textContent = `${audioVolume.value}%`;
};
audioVolume.onchange = () => changeAudio({volume: Number(audioVolume.value)});
audioMute.onclick = () => changeAudio({muted: audioMute.dataset.muted !== "true"});

function showDisplayTimer(state) {
  timerButtons.forEach(button => button.setAttribute("aria-pressed",
    String(Number(button.dataset.timer) === state.minutes && !state.asleep)));
  if (state.error === "pause_unavailable")
    tvTimerStatus.textContent = "Не удалось остановить воспроизведение. Экран оставлен включённым.";
  else if (state.error === "audio_active")
    tvTimerStatus.textContent = "Другой звук ещё играет. Экран оставлен включённым.";
  else if (state.error === "display_unavailable")
    tvTimerStatus.textContent = "Не удалось погасить или включить HDMI. Проверьте монитор.";
  else if (state.phase === "pausing")
    tvTimerStatus.textContent = "Останавливаем воспроизведение перед выключением экрана…";
  else if (state.asleep) tvTimerStatus.textContent = "Экран погашен. Коснитесь его или используйте пульт.";
  else if (state.remaining_seconds > 0)
    tvTimerStatus.textContent = `До отключения: ${Math.ceil(state.remaining_seconds / 60)} мин`;
  else tvTimerStatus.textContent = "Выключен";
}

async function refreshDisplayTimer() {
  try {
    const response = await fetch("/api/display-timer", {cache:"no-store"});
    if (!response.ok) throw new Error("timer unavailable");
    showDisplayTimer(await response.json());
  } catch (_) {
    tvTimerStatus.textContent = "Таймер недоступен. Проверьте ТВ-сервер.";
  }
}

for (const button of timerButtons) button.onclick = async () => {
  tvTimerStatus.textContent = "Устанавливаем таймер…";
  try {
    const response = await fetch("/api/display-timer", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({minutes:Number(button.dataset.timer)}),
    });
    showDisplayTimer(await response.json());
  } catch (_) {
    tvTimerStatus.textContent = "Не удалось изменить таймер. Повторите.";
  }
};

async function loadPairingPin() {
  if (globalThis.location?.hostname !== "127.0.0.1") return;
  const display = document.querySelector("#pairing-pin");
  try {
    const response = await fetch("/api/local-pin", {
      headers: {"X-TV-Launcher": "1"}, cache: "no-store",
    });
    if (!response.ok) throw new Error("PIN unavailable");
    const data = await response.json();
    if (data.pin_required === false) {
      display.textContent = "PIN не нужен";
      display.hidden = false;
      return;
    }
    if (typeof data.pin !== "string" || !data.pin || data.pin.length > 128) throw new Error("Invalid PIN");
    display.textContent = `PIN: ${data.pin}`;
  } catch (_) {
    display.textContent = "PIN недоступен. Проверьте настройку ТВ.";
  }
  display.hidden = false;
}

function openSettings() {
  home.hidden = true;
  settings.hidden = false;
  confirmation.hidden = true;
  systemStatus.textContent = "";
  settingsActions[0].focus();
  void refreshAudio();
  void refreshDisplayTimer();
  void tvSettingsPanel?.refresh();
}

function closeSettings() {
  settings.hidden = true;
  home.hidden = false;
  confirmation.hidden = true;
  const selected = Array.from(document.querySelector("#tiles").children)
    .find(button => button.tabIndex === 0);
  selected?.focus();
}

settingsActions[0].onclick = closeSettings;
document.querySelector("#open-kde").onclick = () => {
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
  if (event.key === "F8") {
    event.preventDefault();
    if (settings.hidden) openSettings();
    return;
  }
  if (settings.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    if (confirmation.hidden) closeSettings();
    else confirmActions[0].click();
    return;
  }
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const actions = confirmation.hidden
    ? settingsActions.filter(action => !action.disabled && !action.closest?.("[hidden]") &&
        (action.tagName === "SUMMARY" || !action.closest?.("details:not([open])")))
    : confirmActions;
  const index = actions.indexOf(document.activeElement);
  if (confirmation.hidden && (event.key === "ArrowRight" || event.key === "ArrowLeft") &&
      rangeActions.includes(document.activeElement)) {
    const slider = document.activeElement;
    if (slider.disabled) return;
    const step = Number(slider.step) || 5;
    slider.value = Math.min(Number(slider.max) || 100, Math.max(Number(slider.min) || 0,
      Number(slider.value) + (event.key === "ArrowRight" ? step : -step)));
    slider.oninput?.();
    slider.onchange?.();
  } else if (confirmation.hidden && (event.key === "ArrowLeft" || event.key === "ArrowRight") && document.activeElement === audioOutput && audioOutput.options.length) {
    const change = event.key === "ArrowRight" ? 1 : -1;
    audioOutput.selectedIndex = (audioOutput.selectedIndex + change + audioOutput.options.length) % audioOutput.options.length;
    audioOutput.onchange();
  } else if (confirmation.hidden && (event.key === "ArrowLeft" || event.key === "ArrowRight") && document.activeElement?.tagName === "SELECT") {
    const select = document.activeElement;
    const change = event.key === "ArrowRight" ? 1 : -1;
    select.selectedIndex = (select.selectedIndex + change + select.options.length) % select.options.length;
    select.onchange?.();
  } else {
    const change = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1;
    let target = (index + change + actions.length) % actions.length;
    while (actions[target].disabled) target = (target + change + actions.length) % actions.length;
    actions[target].focus();
  }
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
    const nextAddress = data.remote_address || "";
    document.querySelector("#address").textContent = nextAddress ||
      "Адрес в локальной сети не найден.";
    const qr = document.querySelector("#qr");
    if (nextAddress !== currentRemoteAddress) {
      qr.src = nextAddress ? `/api/qr?address=${encodeURIComponent(nextAddress)}` : "";
      currentRemoteAddress = nextAddress;
    }
    qr.hidden = !nextAddress;
  } catch (cause) {
    configStatus.textContent = `Ошибка конфигурации: ${cause.message}`;
    currentRemoteAddress = "";
    document.querySelector("#qr").hidden = true;
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
loadPairingPin();
checkStatus();
setInterval(() => {
  checkStatus();
  load();
  if (!settings.hidden) refreshDisplayTimer();
}, 5000);
