"use strict";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login");
const loginPanel = document.querySelector("#login-panel");
const connecting = document.querySelector("#connecting");
const pinInput = document.querySelector("#pin");
const pinVisibility = document.querySelector("#pin-visibility");
const controls = document.querySelector("#controls");
const status = document.querySelector("#status");
const commandStatus = document.querySelector("#command-status");
let csrf = "";
let remoteSuspended = false;
const transport = new RemoteTransport(window.location);
// Binding is presentation context, not authentication or app-version detection.
// Keep links hidden by default if the existing binding parser rejects the page.
// Platform hints affect only the Android invitation, never binding or authority.
const apkPlatform = typeof navigator === "undefined" ? {} : navigator;
const apkUserAgent = typeof apkPlatform.userAgent === "string" ? apkPlatform.userAgent : "";
const apkIsIos = /iPhone|iPad|iPod/i.test(apkUserAgent) ||
  ((apkPlatform.platform === "MacIntel" || /Macintosh/i.test(apkUserAgent)) &&
    typeof apkPlatform.maxTouchPoints === "number" && apkPlatform.maxTouchPoints > 1);
document.querySelectorAll("[data-apk-browser]").forEach(element => {
  element.hidden = apkIsIos || !!transport.expectedDevice;
});
document.querySelectorAll("[data-apk-bound]").forEach(element => {
  element.hidden = apkIsIos || !transport.expectedDevice;
});
function bootstrapPath(path) {
  return transport.expectedDevice ? `${path}?device=${encodeURIComponent(transport.expectedDevice)}` : path;
}
function remoteFetch(path, options = {}) {
  if (remoteSuspended) return Promise.reject(new Error("remote suspended"));
  const method = options.method || "GET";
  const body = options.body === undefined ? null : JSON.parse(options.body);
  return transport.request(csrf, method, path, body);
}
const mediaControls = new PhoneMediaControls(
  (method, path, body) => remoteFetch(path, {
    method, ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  }), () => requireLogin(),
);
const phoneSettingsRoot = document.querySelector("#phone-settings-controls");
let pointerAccelerationLevel = 50;
const phoneSettingsPanel = phoneSettingsRoot ? new SettingsControls(phoneSettingsRoot,
  (method, action) => remoteFetch("/api/settings", {
    method, ...(action ? {body: JSON.stringify(action)} : {}),
  }), () => window.location.reload(), state => {
    pointerAccelerationLevel = state.pointer_acceleration ?? 50;
  }) : null;
if (phoneSettingsPanel) phoneSettingsPanel.bindMagnifierShortcut(document.querySelector("#pad-magnifier"));
let statusTimer = null;
let statusRequestId = 0;
let redirecting = false;
let lastPointerSettingsRefresh = 0;
const audioOutput = document.querySelector("#audio-output");
const audioVolume = document.querySelector("#audio-volume");
const audioStatus = document.querySelector("#audio-status");
let audioTimer = null;
let displayTimerPoll = null;
let displayAsleep = false;
let displayTimerRevision = 0;
let lastWakeHint = -Infinity;
let wakeHintPending = false;
const powerControls = new RemotePowerControls({
  request: (method,path,body) => remoteFetch(path,{method,...(body ? {body:JSON.stringify(body)} : {})}),
  auth: () => requireLogin(), say,
  beforeTimer: () => ++displayTimerRevision,
  timer: (state,revision) => { if (revision === displayTimerRevision) showPhoneTimer(state); },
});
let audioDragging = false;
let audioRevision = 0;
const advancedAudio = new AudioLevelsControls("phone", [
  ["output", "volume"], ["browser", "browser_volume"], ["player", "player_volume"],
], changeAudio, dragging => { audioDragging = dragging; });
let feedbackTimer = null;
let pressedButton = null;
function showButtonFeedback(button) {
  if (!button) return;
  if (pressedButton && pressedButton !== button) pressedButton.classList.remove("remote-pressed");
  pressedButton = button;
  button.classList.add("remote-pressed");
  const lamp = document.querySelector("#status");
  lamp.classList.add("remote-activity");
  if (feedbackTimer !== null) clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => {
    button.classList.remove("remote-pressed");
    pressedButton = null;
    lamp.classList.remove("remote-activity");
  }, 300);
}
document.addEventListener("pointerdown", event => {
  const button = event.target.closest("button");
  if (button) showButtonFeedback(button);
}, true);
document.addEventListener("click", event => {
  const button = event.target.closest("button");
  if (button) showButtonFeedback(button);
}, true);

pinVisibility.onclick = () => {
  const showing = pinInput.type === "password";
  pinInput.type = showing ? "text" : "password";
  pinVisibility.setAttribute("aria-pressed", String(showing));
  pinVisibility.setAttribute("aria-label", showing ? "Скрыть PIN" : "Показать PIN");
  pinInput.focus();
};

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
  audioOutput.disabled = false;
  audioVolume.value = state.volume;
  audioVolume.disabled = false;
  advancedAudio.render(state);
  document.querySelector("#audio-volume-value").textContent = `${state.volume}%`;
  const mute = document.querySelector("#audio-mute");
  mute.disabled = false;
  mute.textContent = state.muted ? "Выкл" : "Вкл";
  mute.setAttribute("aria-label", state.muted ? "Звук выключен. Включить" : "Звук включён. Выключить");
  mute.setAttribute("aria-pressed", String(state.muted));
  mute.dataset.muted = String(state.muted);
  audioStatus.textContent = "";
}

async function refreshAudio() {
  const revision = ++audioRevision;
  try {
    const response = await remoteFetch("/api/audio");
    if (response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("audio unavailable");
    const state = await response.json();
    if (revision === audioRevision) showAudio(state);
  } catch (_) {
    if (revision === audioRevision) {
      const mute = document.querySelector("#audio-mute");
      mute.disabled = true;
      mute.textContent = "?";
      mute.setAttribute("aria-label", "Состояние звука неизвестно");
      mute.removeAttribute("aria-pressed");
      audioOutput.disabled = true;
      audioVolume.disabled = true;
      advancedAudio.actions().forEach(control => { control.disabled = true; });
      audioStatus.textContent = "Звук недоступен. Проверьте подключение выхода и повторите.";
    }
  }
}

async function changeAudio(action) {
  const revision = ++audioRevision;
  try {
    const response = await remoteFetch("/api/audio", {
      method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(action),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("audio change failed");
    const state = await response.json();
    if (revision === audioRevision) showAudio(state);
  } catch (_) {
    if (revision !== audioRevision) return;
    await refreshAudio();
    audioStatus.textContent = "Не удалось изменить звук. Проверьте выход и повторите.";
  }
}

const phoneTimerStatus = document.querySelector("#phone-timer-status");
const timerBadge = document.querySelector("#remote-timer-badge");
const phoneTimerButtons = Array.from(document.querySelectorAll("[data-phone-timer]"));
function compactTime(seconds) {
  if (seconds <= 120) return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return `${Math.ceil(seconds / 60)} мин`;
}
function showPhoneTimer(state) {
  displayAsleep = state.asleep;
  powerControls.renderTimer(state);
  const counting = state.phase === "countdown" && state.remaining_seconds > 0;
  timerBadge.hidden = !counting;
  timerBadge.textContent = counting ? compactTime(state.remaining_seconds) : "";
  phoneTimerButtons.forEach(button => button.setAttribute("aria-pressed",
    String(Number(button.dataset.phoneTimer) === state.minutes && !state.asleep)));
  if (state.error === "pause_unavailable")
    phoneTimerStatus.textContent = "Не удалось поставить видео на паузу. Экран остался включённым.";
  else if (state.error === "audio_active")
    phoneTimerStatus.textContent = "Другой звук ещё играет. Экран остался включённым.";
  else if (state.error === "display_unavailable")
    phoneTimerStatus.textContent = "Не удалось изменить питание HDMI. Проверьте монитор.";
  else if (state.phase === "pausing")
    phoneTimerStatus.textContent = "Останавливаем воспроизведение перед выключением экрана…";
  else if (state.asleep) phoneTimerStatus.textContent = "Экран погашен. Коснитесь его или нажмите кнопку пульта.";
  else if (state.remaining_seconds > 0)
    phoneTimerStatus.textContent = `До отключения: ${Math.ceil(state.remaining_seconds / 60)} мин`;
  else phoneTimerStatus.textContent = "Выключен";
}

async function refreshDisplayTimer() {
  const revision = ++displayTimerRevision;
  try {
    const response = await remoteFetch("/api/display-timer");
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("timer unavailable");
    const state = await response.json();
    if (revision === displayTimerRevision) showPhoneTimer(state);
  } catch (_) {
    if (revision !== displayTimerRevision) return;
    phoneTimerStatus.textContent = "Нет связи с таймером. Проверьте Wi-Fi.";
    timerBadge.hidden = true;
  }
}

async function changeDisplayTimer(action) {
  const revision = ++displayTimerRevision;
  phoneTimerStatus.textContent = "Изменяем таймер…";
  try {
    const response = await remoteFetch("/api/display-timer", {
      method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf},
      body:JSON.stringify(action),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    const state = await response.json();
    if (revision === displayTimerRevision) showPhoneTimer(state);
  } catch (_) {
    if (revision !== displayTimerRevision) return;
    phoneTimerStatus.textContent = "Не удалось изменить таймер. Команда не повторялась.";
  }
}

for (const button of phoneTimerButtons)
  button.onclick = () => changeDisplayTimer({minutes:Number(button.dataset.phoneTimer)});
document.addEventListener("pointerdown", event => {
  if (event.target.closest("[data-no-wake]") || controls.hidden || remoteSuspended) return;
  // After idle/backgrounding the cached asleep flag may be stale. A fresh user
  // action can explicitly restore output power, throttled, never by polling.
  if (!wakeHintPending && (displayAsleep || Date.now()-lastWakeHint >= 5000)) {
    lastWakeHint = Date.now();
    wakeHintPending = true;
    void changeDisplayTimer({wake:true}).finally(() => { wakeHintPending = false; });
  }
}, true);

let messageTimer = null;
function say(text, error = false, notice = false) {
  message.textContent = text;
  message.dataset.error = String(error);
  message.dataset.notice = String(notice);
  message.hidden = !text;
  const loginError = document.querySelector("#login-error");
  loginError.textContent = error && !loginPanel.hidden ? text : "";
  if (!text) return;
  status.textContent = error ? "Ошибка" : "Отправлено";
  status.dataset.feedback = error ? "error" : "success";
  status.title = text;
  status.setAttribute("aria-label", text);
  if (messageTimer !== null) clearTimeout(messageTimer);
  messageTimer = setTimeout(() => {
    delete status.dataset.feedback;
    message.hidden = true;
    void refreshStatus();
  }, error || notice ? 6000 : 1300);
}

function requireLogin() {
  if (remoteSuspended) return;
  touchpadControls.reset();
  mediaControls.stop();
  powerControls.stop();
  displayTimerRevision += 1;
  csrf = "";
  transport.close();
  if (statusTimer !== null) clearInterval(statusTimer);
  statusTimer = null;
  if (audioTimer !== null) clearInterval(audioTimer);
  audioTimer = null;
  if (displayTimerPoll !== null) clearInterval(displayTimerPoll);
  displayTimerPoll = null;
  controls.hidden = true;
  connecting.hidden = false;
  loginPanel.hidden = true;
  void restoreLogin(true);
}

function privateRemoteUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" || url.port !== "8765" || url.pathname !== "/remote" ||
        url.search || url.hash || url.username || url.password) return null;
    const octets = url.hostname.split(".");
    if (octets.length !== 4 || octets.some(part => !/^\d{1,3}$/.test(part) || Number(part) > 255)) return null;
    const [a, b] = octets.map(Number);
    if (!(a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168))) return null;
    return url.href;
  } catch (_) { return null; }
}

async function refreshStatus() {
  const requestId = ++statusRequestId;
  try {
    const response = await remoteFetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const value = await response.json();
    if (requestId !== statusRequestId) return;
    const nextAddress = privateRemoteUrl(value.preferred_remote_address);
    if (!transport.expectedDevice && !remoteSuspended && !redirecting && nextAddress && window.location?.href &&
        nextAddress !== new URL(window.location.href).href) {
      redirecting = true;
      window.location.replace(nextAddress);
      return;
    }
    const messages = [value.extension_online ? "Firefox подключён." : "Firefox не подключён. Подождите или перезапустите ТВ-режим."];
    if (value.pending_commands) messages.push("Команда выполняется…");
    if (value.last_command_failure) messages.push("Последняя команда не выполнена. Нажмите ещё раз.");
    status.dataset.online = String(value.extension_online);
    if (!status.dataset.feedback) {
      status.textContent = !value.extension_online ? "Firefox" :
        value.last_command_failure ? "Ошибка" : value.pending_commands ? "Ждём" : "";
      status.setAttribute("aria-label", messages.join(" "));
      status.title = messages.join(" ");
    }
    const visible = [];
    if (value.pending_commands) visible.push("Команда выполняется…");
    if (value.last_command_failure) visible.push("Последняя команда не выполнена. Повторите действие.");
    if (value.view_pending) visible.push("Для настроенного вида сайта требуется новая версия Firefox bridge. Применится при следующем открытии сервиса после обновления расширения.");
    commandStatus.textContent = visible.join(" ");
    commandStatus.hidden = visible.length === 0;
    if (phoneSettingsPanel && !remoteFace.hidden && touchpadControls.isIdle() &&
        Date.now() - lastPointerSettingsRefresh >= 5000) {
      lastPointerSettingsRefresh = Date.now();
      void phoneSettingsPanel.refresh();
    }
  } catch (_) {
    if (requestId !== statusRequestId) return;
    status.dataset.online = "false";
    if (!status.dataset.feedback) {
      status.textContent = "Нет связи";
      status.setAttribute("aria-label", "Нет связи с медиацентром. Проверьте Wi-Fi.");
    }
    commandStatus.hidden = true;
  }
}

async function post(path, body, success) {
  try {
    const response = await remoteFetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(body),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (response.status === 503 && (body.key?.startsWith("browser-") || ["up", "down", "left", "right", "ok", "system", "video-fullscreen"].includes(body.key))) return say("Firefox на телевизоре сейчас не активен. Откройте ТВ-режим и повторите.", true);
    if (response.status === 503) return say("Управление сейчас недоступно. Подождите несколько секунд и повторите.", true);
    if (!response.ok) return say(`Не удалось выполнить действие (${response.status}). Повторите попытку.`, true);
    say(success);
    void refreshStatus();
    return true;
  } catch (_) {
    say("Нет связи с медиацентром. Проверьте Wi‑Fi и повторите попытку.", true);
  }
  return false;
}

async function activateRemote(token, restored = false) {
  if (remoteSuspended) return;
  csrf = token;
  connecting.hidden = true;
  loginPanel.hidden = true;
  controls.hidden = false;
  showPage("remote");
  if (!restored) say("Телефон подключён.");
  void refreshAudio();
  mediaControls.start();
  powerControls.start();
  void refreshDisplayTimer();
  void refreshStatus();
  if (statusTimer !== null) clearInterval(statusTimer);
  if (audioTimer !== null) clearInterval(audioTimer);
  statusTimer = setInterval(refreshStatus, 1000);
  audioTimer = setInterval(() => { if (!audioDragging) void refreshAudio(); }, 5000);
  displayTimerPoll = setInterval(() => { void refreshDisplayTimer(); void powerControls.refresh(); }, 5000);
}
async function restoreLogin(expired = false) {
  if (remoteSuspended) return;
  let sessionAvailable = false;
  try {
    const response = await fetch(bootstrapPath("/api/session"), {cache:"no-store"});
    if (response.ok) {
      const data = await response.json();
      if (typeof data.csrf === "string" && data.csrf) {
        sessionAvailable = true;
        await activateRemote(data.csrf, true);
        return;
      }
    }
  } catch (_) { /* Keep PIN entry available when the server cannot be reached. */ }
  if (sessionAvailable) {
    connecting.textContent = "Нет связи с медиацентром. Подключаем снова…";
    connecting.hidden = false;
    loginPanel.hidden = true;
    setTimeout(() => { if (!csrf || controls.hidden) void restoreLogin(expired); }, 1500);
    return;
  }
  connecting.hidden = true;
  loginPanel.hidden = false;
  if (expired) say("Сеанс пульта истёк. Введите PIN ещё раз.", true);
}
void restoreLogin();

loginForm.onsubmit = async event => {
  event.preventDefault();
  if (remoteSuspended) return;
  const pin = pinInput.value;
  try {
    const response = await fetch(bootstrapPath("/api/login"), {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({pin}),
    });
    if (!response.ok) {
      say(response.status === 429 ? "Слишком много попыток. Подождите и попробуйте снова." : "Неверный PIN. Попробуйте ещё раз.", true);
      return;
    }
    const data = await response.json();
    pinInput.value = "";
    pinInput.type = "password";
    pinVisibility.setAttribute("aria-pressed", "false");
    pinVisibility.setAttribute("aria-label", "Показать PIN");
    await activateRemote(data.csrf);
  } catch (_) {
    say("Нет связи с медиацентром. Проверьте Wi-Fi и повторите попытку.", true);
  }
};

document.querySelector("#audio-refresh").onclick = refreshAudio;
document.querySelector("#audio-test").onclick = async () => {
  const notice = document.querySelector("#audio-status");
  notice.textContent = "Проверяем звук…";
  try {
    const response = await remoteFetch("/api/audio", {
      method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify({test: true}),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("audio test failed");
    notice.textContent = "Сигнал отправлен. Если его не слышно, проверьте выход и громкость.";
  } catch (_) {
    notice.textContent = "Нет звука. Проверьте выход, громкость и отключение звука.";
  }
};
audioOutput.onchange = () => changeAudio({output: audioOutput.value});
for (const slider of [audioVolume]) {
  slider.addEventListener("pointerdown", () => { audioDragging = true; });
  slider.addEventListener("pointerup", () => { audioDragging = false; });
  slider.addEventListener("pointercancel", () => { audioDragging = false; });
}
audioVolume.oninput = () => {
  document.querySelector("#audio-volume-value").textContent = `${audioVolume.value}%`;
};
audioVolume.onchange = () => changeAudio({volume: Number(audioVolume.value)});
document.querySelector("#audio-mute").onclick = () =>
  changeAudio({muted: document.querySelector("#audio-mute").dataset.muted !== "true"});

document.querySelector("#history-back").onclick = () =>
  post("/api/input", {key:"browser-back"}, "Открываем предыдущую страницу…");
const remoteFace = document.querySelector("#remote-face");
const keyboardPage = document.querySelector("#remote-keyboard-page");
const timerPage = document.querySelector("#remote-timer-page");
const menuPage = document.querySelector("#remote-menu-page");
const sharePage = document.querySelector("#remote-share-page");
const settingsPage = document.querySelector("#remote-settings-page");
function showPage(page) {
  if (page !== "remote") powerControls.dismiss();
  remoteFace.hidden = page !== "remote";
  if (page !== "remote") setTextEditor(false);
  timerPage.hidden = page !== "timer";
  menuPage.hidden = page !== "menu";
  sharePage.hidden = page !== "share";
  settingsPage.hidden = page !== "settings";
  window.scrollTo(0, 0);
  if (page === "remote") void phoneSettingsPanel?.refresh();
}
function setTextEditor(open) {
  keyboardPage.hidden = !open;
  document.querySelector("#show-keyboard").setAttribute("aria-expanded", String(open));
  const input = document.querySelector("#remote-text");
  if (open) input.focus(); else input.blur();
}
document.querySelector("#show-keyboard").onclick = () => setTextEditor(keyboardPage.hidden);
if (document.querySelector("#close-text")) document.querySelector("#close-text").onclick = () => setTextEditor(false);
document.querySelector("#show-timer").onclick = () => {
  showPage("timer");
  void refreshDisplayTimer();
};
document.querySelector("#show-menu").onclick = () => {
  showPage("menu");
  void refreshAudio();
};
document.querySelector("#show-settings").onclick = () => {
  showPage("settings");
  void phoneSettingsPanel?.refresh();
  void refreshAudio();
};
document.querySelector("#back-to-menu").onclick = () => showPage("menu");
document.querySelector("#show-share").onclick = async () => {
  showPage("share");
  const qr = document.querySelector("#share-qr");
  const link = document.querySelector("#share-url");
  const note = document.querySelector("#share-status");
  qr.hidden = true;
  link.hidden = true;
  note.textContent = "Готовим QR-код…";
  try {
    const response = await remoteFetch("/api/services");
    if (!response.ok) throw new Error("address unavailable");
    const {remote_address: address} = await response.json();
    if (!address || !address.startsWith("http://")) throw new Error("address unavailable");
    link.href = address;
    link.textContent = address;
    link.hidden = false;
    qr.onload = () => { note.textContent = ""; };
    qr.onerror = () => { qr.hidden = true; note.textContent = "QR-код недоступен. Откройте адрес ниже."; };
    qr.src = `/api/qr?refresh=${Date.now()}`;
    qr.hidden = false;
  } catch (_) {
    note.textContent = "Адрес пульта недоступен. Проверьте Wi-Fi и откройте этот экран снова.";
  }
};
async function waitForHome() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 400));
    try {
      const response = await remoteFetch("/api/status");
      if (!response.ok) break;
      const state = await response.json();
      if (state.extension_online && state.pending_commands === 0) return true;
    } catch (_) { break; }
  }
  return false;
}
document.querySelectorAll(".return-remote").forEach(button => {
  button.onclick = () => showPage("remote");
});
const touchpadControls = createPhoneTouchpad(
  post,
  action => remoteFetch("/api/pointer", {method:"POST", body:JSON.stringify(action)}),
  () => pointerAccelerationLevel,
  () => requireLogin(),
  message => say(message, true),
);
function sendKey(key) { return touchpadControls.sendKey(key); }

// Public fixed lifecycle hook for the native shell, no general JS/native bridge.
function reconcileMediaOnReturn() {
  if (csrf && !remoteSuspended) mediaControls.reconcile();
}
window.addEventListener("focus", reconcileMediaOnReturn);
window.addEventListener("pageshow", reconcileMediaOnReturn);
document.addEventListener("visibilitychange", () => { if (!document.hidden) reconcileMediaOnReturn(); });
window.adLinuxTvRemoteLifecycle = Object.freeze({resume:reconcileMediaOnReturn, suspend() {
  if (remoteSuspended) return;
  remoteSuspended = true;
  csrf = "";
  touchpadControls.stop();
  mediaControls.stop();
  powerControls.stop();
  displayTimerRevision += 1;
  transport.close();
  for (const timer of [statusTimer, audioTimer, displayTimerPoll])
    if (timer !== null) clearInterval(timer);
  statusTimer = audioTimer = displayTimerPoll = null;
}});
document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => post("/api/command", {command: button.dataset.c}, "");
});
document.querySelector('[data-c="home"]').onclick = async () => {
  if (!await post("/api/command", {command:"home"}, "Открываем плитки…")) return;
  if (!await waitForHome()) return say("Плитки не открылись. Проверьте Firefox.", true);
  await post("/api/input", {key:"escape"}, "Плитки открыты.");
};
let textSending = false;
document.querySelector("#text-form").onsubmit = async event => {
  event.preventDefault();
  const input = document.querySelector("#remote-text");
  if (!input.value || textSending) return;
  const value = input.value;
  textSending = true;
  try {
    if (await post("/api/input", {text:value}, "Текст введён.") && input.value === value) {
      input.value = "";
      setTextEditor(false);
    }
  } finally { textSending = false; }
};
document.querySelector("#key-backspace").onclick = () =>
  post("/api/input", {key: "backspace"}, "Символ удалён.");
document.querySelector("#key-enter").onclick = () =>
  post("/api/input", {key: "enter"}, "Enter отправлен.");
document.querySelector("#key-address").onclick = () =>
  post("/api/input", {key: "address"}, "Адресная строка выбрана.");
