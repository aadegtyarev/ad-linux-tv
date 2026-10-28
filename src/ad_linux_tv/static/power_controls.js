"use strict";

// Explicit actions only: a hold prepares a confirmation, never dispatches shutdown.
class RemotePowerControls {
  constructor(options) {
    this.options = options;
    this.button = document.querySelector("#remote-power");
    this.dialog = document.querySelector("#power-dialog");
    this.confirm = document.querySelector("#power-confirm");
    this.cancel = document.querySelector("#power-cancel");
    this.note = document.querySelector("#power-note");
    this.active = false;
    this.epoch = 0;
    this.revision = 0;
    this.lifecycle = 0;
    this.lastTap = -Infinity;
    this.phase = "idle";
    this.available = null;
    this.lastError = null;
    this.busy = false;
    this.timerState = {asleep:false,phase:"idle"};
    this.suppressClickUntil = 0;
    this.hold = null;
    this.expiry = null;
    this.gesture = null;
    this.challenge = null;
    this.button.addEventListener("pointerdown", event => {
      if (event.isPrimary === false || (event.button !== undefined && event.button !== 0)) return;
      event.preventDefault();
      if (this.gesture) { this.cancelGesture(); return; }
      this.begin(event.pointerId, event.clientX, event.clientY);
      try { this.button.setPointerCapture(event.pointerId); } catch (_) { /* cancelled pointer */ }
    });
    this.button.addEventListener("pointermove", event => {
      const point = this.gesture;
      if (point && point.id === event.pointerId && Math.hypot(event.clientX-point.x,event.clientY-point.y)>12)
        this.cancelGesture();
    });
    this.button.addEventListener("pointerup", event => { event.preventDefault(); this.end(event.pointerId); });
    this.button.addEventListener("pointercancel", () => this.cancelGesture());
    this.button.addEventListener("lostpointercapture", () => this.cancelGesture());
    this.button.addEventListener("click", event => {
      event.preventDefault();
      if (Date.now() > this.suppressClickUntil) void this.tap();
    });
    this.button.addEventListener("keydown", event => {
      if (!["Enter"," "].includes(event.key)) return;
      event.preventDefault();
      if (!event.repeat) this.begin("keyboard",0,0);
    });
    this.button.addEventListener("keyup", event => {
      if (["Enter"," "].includes(event.key)) { event.preventDefault(); this.end("keyboard"); }
    });
    this.button.addEventListener("contextmenu", event => { event.preventDefault(); void this.open(); });
    this.confirm.addEventListener("click", () => { void this.shutdown(); });
    this.cancel.addEventListener("click", () => this.dismiss());
    this.dialog.addEventListener("cancel", event => { event.preventDefault(); this.dismiss(); });
    this.dialog.addEventListener("keydown", event => { if (event.key === "Escape") this.dismiss(); });
    window.addEventListener("blur", () => this.dismiss());
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.dismiss(); });
  }

  begin(id,x,y) {
    if (!this.active || this.busy || this.phase !== "idle") return;
    this.cancelGesture();
    this.gesture = {id,x,y,held:false};
    this.button.classList.add("power-holding");
    this.hold = setTimeout(() => {
      this.hold = null;
      if (!this.gesture) return;
      this.gesture.held = true;
      void this.open();
    },1200);
  }

  end(id) {
    this.suppressClickUntil = Date.now()+650;
    if (this.gesture?.id !== id) return;
    const held = this.gesture.held;
    this.cancelGesture();
    if (!held) void this.tap();
  }

  cancelGesture() {
    if (this.hold !== null) clearTimeout(this.hold);
    this.hold = null;
    this.gesture = null;
    this.suppressClickUntil = Date.now()+650;
    this.button.classList.remove("power-holding");
  }

  renderTimer(state) {
    this.timerState = state;
    const waking = state.asleep || state.phase === "pausing";
    this.button.setAttribute("aria-label", `${waking ? "Включить ТВ" : "Выключить ТВ"}. Удерживайте для полного выключения компьютера`);
    this.button.setAttribute("data-asleep", String(!!state.asleep));
    this.button.setAttribute("aria-busy", String(this.busy || state.phase === "pausing"));
    if (state.error && state.error !== this.lastError) {
      const text = state.error === "audio_active" ? "Звук ещё играет. ТВ оставлен включённым." :
        state.error === "pause_unavailable" ? "Не удалось остановить плеер. ТВ оставлен включённым." : "Не удалось изменить питание HDMI.";
      this.options.say(text,true);
    }
    this.lastError = state.error || null;
  }

  async read(method,path,body) {
    const response = await this.options.request(method,path,body);
    if (response.status === 401 || response.status === 403) { this.options.auth(); throw new Error("auth"); }
    return response;
  }

  async refresh() {
    const revision = this.revision, epoch = this.epoch;
    try {
      const response = await this.read("GET","/api/power");
      if (!response.ok) return;
      const state = await response.json();
      if (!this.active || revision !== this.revision || epoch !== this.epoch) return;
      if (typeof state.available === "boolean") this.available = state.available;
      if (["idle","dispatching","requested","uncertain"].includes(state.phase)) this.phase = state.phase;
      this.button.disabled = this.phase !== "idle";
    } catch (_) { /* Short output control remains available if host power is unavailable. */ }
  }

  async tap() {
    if (!this.active || this.busy || this.phase !== "idle" || Date.now()-this.lastTap < 650) return;
    this.lastTap = Date.now();
    const lifecycle = this.lifecycle;
    this.busy = true;
    this.lastError = null;
    const timerRevision = this.options.beforeTimer();
    const action = this.timerState.asleep || this.timerState.phase === "pausing" ? {wake:true,cec:true} : {sleep:true};
    this.renderTimer(this.timerState);
    try {
      const response = await this.read("POST","/api/display-timer",action);
      const state = await response.json();
      if (!this.active || lifecycle !== this.lifecycle) return;
      const valid = state && typeof state.asleep === "boolean" && ["idle","countdown","pausing","asleep"].includes(state.phase);
      if (valid) this.options.timer(state,timerRevision);
      if (!response.ok) {
        if (!valid || !state.error) throw new Error("power unavailable");
        return;
      }
      if (!valid) throw new Error("invalid power state");
      if (action.wake) this.options.say(state.cec_wake === "requested"
        ? "Включение ТВ запрошено. Если картинки нет, включите ТВ штатным пультом."
        : "Видеовыход включён. Если картинки нет, включите ТВ штатным пультом.",false,true);
    } catch (_) {
      if (this.active && lifecycle === this.lifecycle) this.options.say("Не удалось подтвердить переключение питания. Команда не повторялась.",true);
    } finally {
      if (this.active && lifecycle === this.lifecycle) { this.busy = false; this.renderTimer(this.timerState); }
    }
  }

  async open() {
    if (!this.active || this.busy || this.phase !== "idle" || this.dialog.open) return;
    this.cancelGesture();
    this.challenge = null;
    const epoch = ++this.epoch;
    this.confirm.disabled = true;
    this.note.textContent = "Подготовка подтверждения…";
    if (typeof this.dialog.showModal === "function") this.dialog.showModal();
    else this.dialog.setAttribute("open", "");
    this.cancel.focus();
    if (this.available === false) {
      this.note.textContent = "Полное выключение сейчас недоступно. Ничего не выключено.";
      return;
    }
    const started = Date.now();
    try {
      const response = await this.read("POST","/api/power",{action:"prepare"});
      const data = await response.json();
      if (!this.active || epoch !== this.epoch || !this.dialog.open) return;
      if (!response.ok || !/^[A-Za-z0-9_-]{43}$/.test(data.challenge) || data.expires_in !== 20)
        throw new Error("confirmation unavailable");
      const remaining = started+20_000-Date.now();
      if (remaining <= 0) throw new Error("expired");
      this.challenge = data.challenge;
      this.confirm.disabled = false;
      this.note.textContent = "";
      this.expiry = setTimeout(() => {
        if (epoch !== this.epoch) return;
        this.challenge = null; this.confirm.disabled = true;
        this.note.textContent = "Подтверждение истекло. Закройте окно и удержите кнопку заново.";
      },remaining);
    } catch (_) {
      if (this.active && epoch === this.epoch) this.note.textContent = "Полное выключение сейчас недоступно. Ничего не выключено.";
    }
  }

  async shutdown() {
    if (!this.active || !this.challenge || this.confirm.disabled || this.phase !== "idle") return;
    const challenge = this.challenge, epoch = this.epoch;
    this.challenge = null;
    this.confirm.disabled = true;
    this.phase = "dispatching";
    this.button.disabled = true;
    this.revision += 1;
    if (this.expiry !== null) clearTimeout(this.expiry);
    this.expiry = null;
    this.note.textContent = "Отправляем выключение…";
    try {
      const response = await this.read("POST","/api/power",{action:"shutdown",challenge});
      const state = await response.json();
      if (!this.active || epoch !== this.epoch) return;
      this.phase = response.status === 202 && state.phase === "requested" ? "requested" : "uncertain";
      this.note.textContent = this.phase === "requested" ? "Выключение принято. Компьютер завершает работу." : "Результат выключения не подтверждён. Повтора не будет.";
    } catch (_) {
      if (!this.active || epoch !== this.epoch) return;
      this.phase = "uncertain";
      this.note.textContent = "Результат выключения не подтверждён. Повтора не будет.";
    }
  }

  dismiss() {
    this.epoch += 1;
    this.cancelGesture();
    if (this.expiry !== null) clearTimeout(this.expiry);
    this.expiry = null;
    this.challenge = null;
    this.confirm.disabled = true;
    if (typeof this.dialog.close === "function") this.dialog.close();
    else this.dialog.removeAttribute("open");
  }

  start() { this.active = true; this.lastTap = -Infinity; this.button.disabled = this.phase !== "idle"; void this.refresh(); }
  stop() { this.active = false; this.busy = false; this.lifecycle += 1; this.dismiss(); this.revision += 1; }
}

if (typeof module !== "undefined") module.exports = {RemotePowerControls};
