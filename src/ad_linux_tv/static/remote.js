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
let statusTimer = null;
let browserService = null;
const audioOutput = document.querySelector("#audio-output");
const audioVolume = document.querySelector("#audio-volume");
const audioStatus = document.querySelector("#audio-status");
let audioTimer = null;
let displayTimerPoll = null;
let displayAsleep = false;
let audioDragging = false;
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
  audioVolume.value = state.volume;
  document.querySelector("#audio-volume-value").textContent = `${state.volume}%`;
  document.querySelector("#audio-mute").textContent = state.muted ? "♩" : "♬";
  document.querySelector("#audio-mute").setAttribute("aria-label", state.muted ? "Включить звук" : "Выключить звук");
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

const phoneTimerStatus = document.querySelector("#phone-timer-status");
const phoneTimerButtons = Array.from(document.querySelectorAll("[data-phone-timer]"));
function showPhoneTimer(state) {
  displayAsleep = state.asleep;
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
  try {
    const response = await fetch("/api/display-timer", {cache:"no-store"});
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("timer unavailable");
    showPhoneTimer(await response.json());
  } catch (_) {
    phoneTimerStatus.textContent = "Нет связи с таймером. Проверьте Wi-Fi.";
  }
}

async function changeDisplayTimer(action) {
  phoneTimerStatus.textContent = "Изменяем таймер…";
  try {
    const response = await fetch("/api/display-timer", {
      method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf},
      body:JSON.stringify(action),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    showPhoneTimer(await response.json());
  } catch (_) {
    phoneTimerStatus.textContent = "Не удалось изменить таймер. Повторите.";
  }
}

for (const button of phoneTimerButtons)
  button.onclick = () => changeDisplayTimer({minutes:Number(button.dataset.phoneTimer)});
document.addEventListener("pointerdown", () => {
  if (displayAsleep && !controls.hidden) {
    displayAsleep = false;
    void changeDisplayTimer({wake:true});
  }
}, true);

let messageTimer = null;
function say(text, error = false) {
  message.textContent = text;
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
  }, error ? 5000 : 1300);
}

function requireLogin() {
  csrf = "";
  if (statusTimer !== null) clearInterval(statusTimer);
  statusTimer = null;
  if (audioTimer !== null) clearInterval(audioTimer);
  audioTimer = null;
  if (displayTimerPoll !== null) clearInterval(displayTimerPoll);
  displayTimerPoll = null;
  controls.hidden = true;
  connecting.hidden = true;
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
    commandStatus.textContent = visible.join(" ");
    commandStatus.hidden = visible.length === 0;
  } catch (_) {
    status.dataset.online = "false";
    if (!status.dataset.feedback) {
      status.textContent = "Нет связи";
      status.setAttribute("aria-label", "Нет связи с Beelink. Проверьте Wi-Fi.");
    }
    commandStatus.hidden = true;
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
    if (response.status === 503 && (body.key?.startsWith("browser-") || ["up", "down", "left", "right", "ok", "system", "video-fullscreen"].includes(body.key))) return say("Firefox на телевизоре сейчас не активен. Откройте ТВ-режим и повторите.", true);
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

async function activateRemote(token, restored = false) {
  csrf = token;
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
  connecting.hidden = true;
  loginPanel.hidden = true;
  controls.hidden = false;
  showPage("remote");
  if (!restored) say("Телефон подключён.");
  void refreshAudio();
  void refreshDisplayTimer();
  void refreshStatus();
  if (statusTimer !== null) clearInterval(statusTimer);
  if (audioTimer !== null) clearInterval(audioTimer);
  statusTimer = setInterval(refreshStatus, 1000);
  audioTimer = setInterval(() => { if (!audioDragging) void refreshAudio(); }, 5000);
  displayTimerPoll = setInterval(refreshDisplayTimer, 5000);
}
async function restoreLogin() {
  try {
    const response = await fetch("/api/session", {cache:"no-store"});
    if (response.ok) {
      const data = await response.json();
      if (typeof data.csrf === "string" && data.csrf) {
        await activateRemote(data.csrf, true);
        return;
      }
    }
  } catch (_) { /* Keep PIN entry available when the server cannot be reached. */ }
  connecting.hidden = true;
  loginPanel.hidden = false;
}
void restoreLogin();

loginForm.onsubmit = async event => {
  event.preventDefault();
  const pin = pinInput.value;
  try {
    const response = await fetch("/api/login", {
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
    say("Нет связи с Beelink. Проверьте Wi-Fi и повторите попытку.", true);
  }
};

document.querySelector("#audio-refresh").onclick = refreshAudio;
document.querySelector("#audio-test").onclick = async () => {
  const notice = document.querySelector("#audio-status");
  notice.textContent = "Проверяем звук…";
  try {
    const response = await fetch("/api/audio", {
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
document.querySelector("#history-forward").onclick = () =>
  post("/api/input", {key:"browser-forward"}, "Открываем следующую страницу…");
document.querySelector("#menu-tab").onclick = () =>
  post("/api/input", {key:"tab"}, "Фокус на следующем элементе.");
document.querySelector("#menu-shift-tab").onclick = () =>
  post("/api/input", {key:"shift-tab"}, "Фокус на предыдущем элементе.");
const remoteFace = document.querySelector("#remote-face");
const keyboardPage = document.querySelector("#remote-keyboard-page");
const timerPage = document.querySelector("#remote-timer-page");
const menuPage = document.querySelector("#remote-menu-page");
const sharePage = document.querySelector("#remote-share-page");
function showPage(page) {
  remoteFace.hidden = page !== "remote";
  keyboardPage.hidden = page !== "keyboard";
  timerPage.hidden = page !== "timer";
  menuPage.hidden = page !== "menu";
  sharePage.hidden = page !== "share";
  window.scrollTo(0, 0);
  if (page === "keyboard") document.querySelector("#remote-text").focus();
}
document.querySelector("#show-keyboard").onclick = () => showPage("keyboard");
document.querySelector("#show-timer").onclick = () => {
  showPage("timer");
  void refreshDisplayTimer();
};
document.querySelector("#show-menu").onclick = () => showPage("menu");
document.querySelector("#show-share").onclick = async () => {
  showPage("share");
  const qr = document.querySelector("#share-qr");
  const link = document.querySelector("#share-url");
  const note = document.querySelector("#share-status");
  qr.hidden = true;
  link.hidden = true;
  note.textContent = "Готовим QR-код…";
  try {
    const response = await fetch("/api/services", {cache: "no-store"});
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
document.querySelector("#show-system").onclick = async () => {
  if (!await post("/api/command", {command: "home"}, "Открываем Систему…")) return;
  let ready = false;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 400));
    try {
      const response = await fetch("/api/status");
      if (!response.ok) break;
      const state = await response.json();
      if (state.extension_online && state.pending_commands === 0) { ready = true; break; }
    } catch (_) { break; }
  }
  if (!ready) return say("Система не открылась. Проверьте подключение Firefox и повторите.", true);
  await new Promise(resolve => setTimeout(resolve, 300));
  if (await post("/api/input", {key: "system"}, "Система открыта на телевизоре.")) showPage("remote");
};
document.querySelectorAll(".return-remote").forEach(button => {
  button.onclick = () => showPage("remote");
});
let navigationSequence = Promise.resolve();
let inputMode = "keys";
function sendArrow(key) {
  if (key !== "ok") inputMode = "keys";
  navigationSequence = navigationSequence.then(() => post("/api/input", {key}, ""));
  return navigationSequence;
}
const touchpad = document.querySelector("#remote-touchpad");
const touchIndicators = [document.querySelector("#touch-indicator"), document.querySelector("#touch-indicator-2")];
const fingers = new Map();
let pendingX = 0;
let pendingY = 0;
let pendingScroll = 0;
let drainTimer = null;
const pointerInflight = new Set();
const maxPointerInflight = 1;
let scrollFraction = 0;
let pointerErrorShown = false;
async function sendPointer(action) {
  try {
    const response = await fetch("/api/pointer", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(action),
    });
    if (response.status === 401 || response.status === 403) return requireLogin();
    if (!response.ok) throw new Error("pointer unavailable");
    pointerErrorShown = false;
  } catch (_) {
    if (!pointerErrorShown) say("Курсор недоступен. Проверьте ТВ-режим и Wi-Fi.", true);
    pointerErrorShown = true;
  }
}
function hasPointerWork() {
  return Math.abs(pendingX) >= 1 || Math.abs(pendingY) >= 1 || pendingScroll !== 0;
}
function dispatchPointer(action) {
  const request = sendPointer(action);
  pointerInflight.add(request);
  void request.finally(() => {
    pointerInflight.delete(request);
    pumpPointer();
  });
}
function pumpPointer() {
  if (drainTimer !== null) clearTimeout(drainTimer);
  drainTimer = null;
  while (pointerInflight.size < maxPointerInflight &&
      (Math.abs(pendingX) >= 1 || Math.abs(pendingY) >= 1)) {
    const dx = Math.max(-600, Math.min(600, Math.round(pendingX)));
    const dy = Math.max(-600, Math.min(600, Math.round(pendingY)));
    pendingX -= dx;
    pendingY -= dy;
    if (dx || dy) dispatchPointer({dx, dy});
  }
  // One request at a time keeps compositor actions in gesture order.
  if (pointerInflight.size === 0 && pendingScroll) {
    const scroll = Math.max(-24, Math.min(24, pendingScroll));
    pendingScroll -= scroll;
    dispatchPointer({scroll});
  }
}
async function drainPointer() {
  pumpPointer();
  while (hasPointerWork() || pointerInflight.size) {
    if (pointerInflight.size) await Promise.race(pointerInflight);
    else pumpPointer();
  }
}
function schedulePointerDrain() {
  if (drainTimer === null && pointerInflight.size < maxPointerInflight)
    drainTimer = setTimeout(pumpPointer, 16);
}
function schedulePointerMove(dx, dy) {
  pendingX = Math.max(-4800, Math.min(4800, pendingX + dx * 3));
  pendingY = Math.max(-4800, Math.min(4800, pendingY + dy * 3));
  schedulePointerDrain();
}
function schedulePointerScroll(dy) {
  inputMode = "pointer";
  scrollFraction -= dy * 2;
  const steps = Math.trunc(scrollFraction);
  scrollFraction -= steps;
  pendingScroll = Math.max(-96, Math.min(96, pendingScroll + steps));
  schedulePointerDrain();
}
function showTouches() {
  const rect = touchpad.getBoundingClientRect();
  const active = Array.from(fingers.values());
  touchIndicators.forEach((indicator, index) => {
    const finger = active[index];
    indicator.hidden = !finger;
    if (!finger) return;
    indicator.style.left = `${finger.x - rect.left}px`;
    indicator.style.top = `${finger.y - rect.top}px`;
  });
}
touchpad.addEventListener("pointerdown", event => {
  event.preventDefault();
  touchpad.setPointerCapture(event.pointerId);
  const arrow = event.target.closest("[data-arrow]")?.dataset.arrow || null;
  fingers.set(event.pointerId, {
    startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY,
    time: Date.now(), moved: false, multi: false, arrow,
  });
  if (fingers.size > 1) for (const finger of fingers.values()) finger.multi = true;
  if (fingers.size > 1) { pendingX = 0; pendingY = 0; }
  showTouches();
  touchpad.classList.add("touch-active");
});
touchpad.addEventListener("pointermove", event => {
  const finger = fingers.get(event.pointerId);
  if (!finger) return;
  event.preventDefault();
  const dx = event.clientX - finger.x;
  const dy = event.clientY - finger.y;
  finger.x = event.clientX;
  finger.y = event.clientY;
  if (fingers.size > 1) {
    schedulePointerScroll(dy / fingers.size);
  } else if (!finger.multi) {
    // Keep a painted key press despite normal finger jitter; a deliberate drag still moves the cursor.
    const dragDistance = finger.arrow ? 32 : 9;
    const wasMoving = finger.moved;
    if (Math.hypot(event.clientX - finger.startX, event.clientY - finger.startY) > dragDistance) finger.moved = true;
    if (finger.moved) {
      inputMode = "pointer";
      schedulePointerMove(
      wasMoving ? dx : event.clientX - finger.startX,
      wasMoving ? dy : event.clientY - finger.startY,
      );
    }
  }
  showTouches();
});
function finishTouch(event, cancelled = false) {
  const finger = fingers.get(event.pointerId);
  if (!finger) return;
  event.preventDefault();
  fingers.delete(event.pointerId);
  if (!fingers.size) touchpad.classList.remove("touch-active");
  if (fingers.size === 1) {
    const remaining = fingers.values().next().value;
    if (remaining.multi) {
      remaining.multi = false;
      remaining.moved = true;
      remaining.arrow = null;
      remaining.startX = remaining.x;
      remaining.startY = remaining.y;
    }
  }
  showTouches();
  if (cancelled) {
    if (drainTimer !== null) clearTimeout(drainTimer);
    drainTimer = null;
    pendingX = 0;
    pendingY = 0;
    pendingScroll = 0;
    scrollFraction = 0;
    return;
  }
  if (finger.multi) return;
  if (finger.moved) return void drainPointer();
  if (!finger.arrow && Date.now() - finger.time > 650) return;
  if (finger.arrow) void sendArrow(finger.arrow);
  else if (inputMode === "keys") void sendArrow("ok");
  else void drainPointer().then(() => sendPointer({click: true}));
}
touchpad.addEventListener("pointerup", event => finishTouch(event));
touchpad.addEventListener("pointercancel", event => finishTouch(event, true));
touchpad.addEventListener("keydown", event => {
  const key = {ArrowUp:"up", ArrowDown:"down", ArrowLeft:"left", ArrowRight:"right"}[event.key];
  if (key) { event.preventDefault(); void sendArrow(key); }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (inputMode === "keys") void sendArrow("ok");
    else void drainPointer().then(() => sendPointer({click: true}));
  }
});
document.querySelectorAll("[data-c]").forEach(button => {
  button.onclick = () => { if (button.dataset.c === "home") inputMode = "keys"; return post("/api/command", {command: button.dataset.c}, ""); };
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
