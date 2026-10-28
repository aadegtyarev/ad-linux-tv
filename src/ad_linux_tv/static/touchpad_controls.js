"use strict";

function createPhoneTouchpad(post, request, getAcceleration, onAuth, onError) {
  let navigationSequence = Promise.resolve();
  let stopped = false;
  let generation = 0;
  function sendKey(key) {
    if (["up", "down", "left", "right", "tab", "shift-tab"].includes(key))
      setPadSelectionMode(true);
    if (stopped) return Promise.resolve();
    const epoch = generation;
    navigationSequence = navigationSequence.then(() => stopped || epoch !== generation ? undefined : post("/api/input", {key}, ""));
    return navigationSequence;
  }
  document.querySelector("#pad-tab").onclick = () => sendKey("tab");
  document.querySelector("#pad-shift-tab").onclick = () => sendKey("shift-tab");
  document.querySelector("#pad-enter").onclick = () => sendKey("enter");
  const touchpad = document.querySelector("#remote-touchpad");
  let padSelectionMode = false;
  function setPadSelectionMode(selection) {
    padSelectionMode = selection;
    document.querySelector("#touch-action-text").textContent = selection ? "Выбрать" : "Клик";
    touchpad.setAttribute("aria-label", selection
      ? "Навигация: стрелки или Tab выбирают элемент; тап активирует его; проведите пальцем для курсора"
      : "Тачпад: ведите пальцем для курсора; тап кликает по курсору; края — стрелки; два пальца — прокрутка");
  }
  const touchIndicators = [document.querySelector("#touch-indicator"), document.querySelector("#touch-indicator-2")];
  const fingers = new Map();
  let pendingX = 0;
  let pendingY = 0;
  let pendingScroll = 0;
  let pendingScrollX = 0;
  let drainTimer = null;
  const pointerInflight = new Set();
  // Several ordered messages may be in flight on the same WebSocket.
  const maxPointerInflight = 3;
  let scrollFraction = 0;
  let scrollFractionX = 0;
  let pointerErrorShown = false;
  async function sendPointer(action) {
    if (stopped) return;
    const epoch = generation;
    try {
      const response = await request(action);
      if (stopped || epoch !== generation) return;
      if (response.status === 401 || response.status === 403) return onAuth();
      if (!response.ok) throw new Error("pointer unavailable");
      pointerErrorShown = false;
    } catch (_) {
      if (stopped || epoch !== generation) return;
      pendingX = 0;
      pendingY = 0;
      pendingScroll = 0;
      scrollFraction = 0;
      pendingScrollX = scrollFractionX = 0;
      if (!pointerErrorShown) onError("Курсор недоступен. Проверьте ТВ-режим и Wi-Fi.");
      pointerErrorShown = true;
    }
  }
  function hasPointerWork() {
    return Math.abs(pendingX) >= 1 || Math.abs(pendingY) >= 1 || pendingScroll !== 0 || pendingScrollX !== 0;
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
    if (stopped) return;
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
    if (pointerInflight.size === 0 && (pendingScroll || pendingScrollX)) {
      const scroll = Math.max(-24, Math.min(24, pendingScroll));
      const scrollX = Math.max(-24, Math.min(24, pendingScrollX));
      pendingScroll -= scroll;
      pendingScrollX -= scrollX;
      dispatchPointer(scrollX ? {scroll, scroll_x:scrollX} : {scroll});
    }
  }
  async function drainPointer() {
    const epoch = generation;
    pumpPointer();
    while (epoch === generation && !stopped && (hasPointerWork() || pointerInflight.size)) {
      if (pointerInflight.size) await Promise.race(pointerInflight);
      else pumpPointer();
    }
  }
  function schedulePointerDrain() {
    if (drainTimer === null && pointerInflight.size < maxPointerInflight)
      drainTimer = setTimeout(pumpPointer, 16);
  }
  function schedulePointerMove(finger, dx, dy, time) {
    setPadSelectionMode(false);
    const moved = finger.acceleration.move(dx, dy, time);
    pendingX = Math.max(-4800, Math.min(4800, pendingX + moved.dx));
    pendingY = Math.max(-4800, Math.min(4800, pendingY + moved.dy));
    schedulePointerDrain();
  }
  function schedulePointerScroll(dx,dy) {
    setPadSelectionMode(false);
    scrollFraction -= dy * 2;
    scrollFractionX -= dx * 2;
    const steps = Math.trunc(scrollFraction), stepsX = Math.trunc(scrollFractionX);
    scrollFraction -= steps;
    scrollFractionX -= stepsX;
    pendingScroll = Math.max(-96, Math.min(96, pendingScroll + steps));
    pendingScrollX = Math.max(-96, Math.min(96, pendingScrollX + stepsX));
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
    if (stopped) return;
    event.preventDefault();
    touchpad.setPointerCapture(event.pointerId);
    const arrow = event.target.closest("[data-arrow]")?.dataset.arrow || null;
    fingers.set(event.pointerId, {
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY,
      time: Date.now(), moved: false, multi: false, arrow,
      acceleration: new PointerAcceleration(getAcceleration()),
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
      schedulePointerScroll(dx / fingers.size,dy / fingers.size);
    } else if (!finger.multi) {
      // Keep a painted key press despite normal finger jitter; a deliberate drag still moves the cursor.
      const dragDistance = finger.arrow ? 32 : 9;
      const wasMoving = finger.moved;
      if (Math.hypot(event.clientX - finger.startX, event.clientY - finger.startY) > dragDistance) finger.moved = true;
      if (finger.moved) {
        schedulePointerMove(finger,
        wasMoving ? dx : event.clientX - finger.startX,
        wasMoving ? dy : event.clientY - finger.startY,
        Number.isFinite(event.timeStamp) ? event.timeStamp : Date.now(),
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
      pendingScrollX = scrollFractionX = 0;
      return;
    }
    if (finger.multi) return;
    if (finger.moved) return void drainPointer();
    if (!finger.arrow && Date.now() - finger.time > 650) return;
    if (finger.arrow) void sendKey(finger.arrow);
    else if (padSelectionMode) void sendKey("enter");
    else {
      const epoch = generation;
      void drainPointer().then(() => { if (!stopped && epoch === generation) return sendPointer({click: true}); });
    }
  }
  touchpad.addEventListener("pointerup", event => finishTouch(event));
  touchpad.addEventListener("pointercancel", event => finishTouch(event, true));
  touchpad.addEventListener("keydown", event => {
    const key = {ArrowUp:"up", ArrowDown:"down", ArrowLeft:"left", ArrowRight:"right"}[event.key];
    if (key) { event.preventDefault(); void sendKey(key); }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void sendKey("enter");
    }
  });
  function reset() {
    generation += 1;
    navigationSequence = Promise.resolve();
    pointerInflight.clear();
    if (drainTimer !== null) clearTimeout(drainTimer);
    drainTimer = null;
    pendingX = pendingY = pendingScroll = scrollFraction = pendingScrollX = scrollFractionX = 0;
    fingers.clear();
    touchpad.classList.remove("touch-active");
    touchIndicators.forEach(indicator => { indicator.hidden = true; });
  }
  function stop() { reset(); stopped = true; }
  return {sendKey, reset, stop, isIdle: () => pointerInflight.size === 0};
}

if (typeof module !== "undefined") module.exports = {createPhoneTouchpad};
