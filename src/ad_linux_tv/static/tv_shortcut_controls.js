"use strict";

// A learned candidate is only a draft until an explicit save. It is scoped to
// this phone socket; late responses and uncertain operations are never replayed.
class TvShortcutControls {
  constructor(root, request, onAuth = () => {}, onSaved = () => {}, wait = ms => new Promise(resolve => setTimeout(resolve, ms))) {
    this.root = root;
    this.wait = wait;
    this.request = request;
    this.onAuth = onAuth;
    this.onSaved = onSaved;
    this.actions = ["ok", "volume_up", "volume_down", "video_panel", "magnifier", "fullscreen"];
    this.field = name => root.querySelector(`[data-shortcut="${name}"]`);
    this.active = false;
    this.epoch = 0;
    this.socketEpoch = 0;
    this.refreshEpoch = 0;
    this.busy = false;
    this.phase = null;
    this.learningId = null;
    this.draft = {};
    this.saved = {};
    this.state = null;
    this.dirty = false;
    this.conflict = false;
    for (const action of this.actions) {
      this.field(`${action}-learn`).onclick = () => void this.learn(action);
      this.field(`${action}-clear`).onclick = () => {
        if (this.busy) return;
        delete this.draft[action];
        this.dirty = true;
        this.notice("Изменения ещё не сохранены.");
        this.render();
      };
    }
    this.field("cancel").onclick = () => this.cancel();
    this.field("save").onclick = () => void this.save();
    this.render();
  }

  notice(text) { this.field("status").textContent = text; }

  same(left, right) {
    return this.actions.every(action => (left?.[action] || null) === (right?.[action] || null));
  }

  render() {
    for (const action of this.actions) {
      this.field(`${action}-key`).textContent = this.draft[action] || "Не назначено";
      const applied = this.state?.tv_shortcuts_applied;
      this.field(`${action}-applied`).textContent = !this.state ? "" :
        !applied || typeof applied !== "object" ? "Сейчас: неизвестно" :
          `Сейчас: ${applied[action] || "не назначено"}`;
      this.field(`${action}-learn`).disabled = !this.active || !this.state || this.busy;
      this.field(`${action}-clear`).disabled = !this.active || !this.state || this.busy || !this.draft[action];
    }
    this.field("cancel").hidden = this.phase !== "learn";
    this.field("save").disabled = !this.active || !this.state || this.busy || !this.dirty;
  }

  async activate() {
    if (this.active) return;
    this.active = true;
    const epoch = ++this.epoch;
    this.state = null;
    this.notice("Проверяем назначения…");
    this.render();
    await this.refresh(epoch);
  }

  deactivate() {
    if (!this.active && !this.busy) return;
    this.active = false;
    this.cancel();
    this.state = null;
    this.draft = {};
    this.saved = {};
    this.dirty = false;
    this.render();
  }

  disconnect() {
    this.active = false;
    ++this.epoch;
    ++this.socketEpoch;
    this.learningId = null;
    this.busy = false;
    this.phase = null;
    this.state = null;
    this.draft = {};
    this.saved = {};
    this.dirty = false;
    this.render();
  }

  cancel() {
    ++this.epoch;
    const id = this.learningId;
    this.learningId = null;
    this.busy = false;
    this.phase = null;
    if (id) void this.request("POST", "/api/tv-shortcut-learn", {action:"cancel", id}).catch(() => {});
    if (this.active) this.notice("Выбор отменён.");
    this.render();
  }

  async refresh(epoch = this.epoch) {
    const generation = ++this.refreshEpoch;
    try {
      const response = await this.request("GET", "/api/settings");
      if (!this.active || epoch !== this.epoch || generation !== this.refreshEpoch) return;
      if (response.status === 401 || response.status === 403) { this.onAuth(); return; }
      if (!response.ok) throw new Error("unavailable");
      const state = await response.json();
      if (!this.active || epoch !== this.epoch || generation !== this.refreshEpoch) return;
      if (!state || !state.tv_shortcuts || typeof state.tv_shortcuts !== "object" || Array.isArray(state.tv_shortcuts))
        throw new Error("unavailable");
      this.state = state;
      const changedElsewhere = this.dirty && !this.same(this.saved, state.tv_shortcuts);
      this.conflict = changedElsewhere;
      if (!this.dirty) {
        this.saved = {...state.tv_shortcuts};
        this.draft = {...this.saved};
      }
      if (changedElsewhere) this.notice("Назначения изменились на другом устройстве. Откройте этот раздел заново.");
      else if (state.tv_shortcuts_restart_required) this.notice("Сохранено. Для применения перезапустите ТВ-режим.");
      else if (state.tv_shortcuts_unavailable) this.notice("Некоторые назначения недоступны. Выберите другие кнопки.");
      else this.notice("Выберите кнопки, затем сохраните назначения.");
    } catch (_) {
      if (this.active && epoch === this.epoch && generation === this.refreshEpoch) {
        this.state = null;
        this.notice("Назначение кнопок сейчас недоступно.");
      }
    }
    this.render();
  }

  async learn(action) {
    if (!this.active || this.busy || !this.state || !this.actions.includes(action)) return;
    const epoch = ++this.epoch, socketEpoch = this.socketEpoch;
    this.busy = true;
    this.phase = "learn";
    this.notice("Посмотрите на ТВ и нажмите выбранную кнопку. Это может выполнить её прежнее действие.");
    this.render();
    try {
      const start = await this.request("POST", "/api/tv-shortcut-learn", {action:"start"});
      if (start.status === 401 || start.status === 403) { if (this.active && epoch === this.epoch) this.onAuth(); return; }
      if (start.status !== 202) throw new Error("unavailable");
      const started = await start.json();
      if (!/^[0-9a-f]{32}$/.test(started?.id || "")) throw new Error("unavailable");
      if (!this.active || epoch !== this.epoch) {
        if (socketEpoch === this.socketEpoch)
          void this.request("POST", "/api/tv-shortcut-learn", {action:"cancel", id:started.id}).catch(() => {});
        return;
      }
      this.learningId = started.id;
      const deadline = Date.now() + 19000;
      while (this.active && epoch === this.epoch && Date.now() < deadline) {
        await this.wait(350);
        if (!this.active || epoch !== this.epoch) return;
        const response = await this.request("POST", "/api/tv-shortcut-learn", {action:"result", id:started.id});
        if (!this.active || epoch !== this.epoch) return;
        if (response.status === 401 || response.status === 403) { this.onAuth(); return; }
        if (!response.ok) throw new Error("unavailable");
        const result = await response.json();
        if (!this.active || epoch !== this.epoch) return;
        if (result?.state === "waiting") continue;
        this.learningId = null;
        if (result?.state === "cancelled") {
          this.notice("Выбор отменён на ТВ.");
          return;
        }
        if (result?.state !== "ready" || !/^XF86[A-Za-z0-9]{1,32}$/.test(result.key || ""))
          throw new Error("unavailable");
        if (this.actions.some(other => other !== action && this.draft[other] === result.key)) {
          this.notice("Эта кнопка уже выбрана для другого действия.");
          return;
        }
        this.draft[action] = result.key;
        this.dirty = true;
        this.notice("Кнопка распознана. Нажмите «Сохранить назначения».");
        return;
      }
      throw new Error("unavailable");
    } catch (_) {
      if (this.active && epoch === this.epoch)
        this.notice("Кнопка недоступна или не распознана. Выберите другую; окно на ТВ закроется.");
    } finally {
      if (this.active && epoch === this.epoch) {
        const id = this.learningId;
        this.learningId = null;
        this.busy = false;
        this.phase = null;
        if (id) void this.request("POST", "/api/tv-shortcut-learn", {action:"cancel", id}).catch(() => {});
        this.render();
      }
    }
  }

  async save() {
    if (!this.active || this.busy || !this.state || !this.dirty) return;
    const epoch = ++this.epoch, draft = {...this.draft};
    this.busy = true;
    this.phase = "save";
    this.notice("Сохраняем…");
    this.render();
    try {
      const response = await this.request("POST", "/api/settings", {
        setting:"tv_shortcuts", value:{expected:{...this.saved}, assignments:draft},
      });
      if (!this.active || epoch !== this.epoch) return;
      if (response.status === 401 || response.status === 403) { this.onAuth(); return; }
      if (!response.ok) throw new Error("unavailable");
      const state = await response.json();
      if (!this.active || epoch !== this.epoch) return;
      if (!state || !state.tv_shortcuts || !this.same(state.tv_shortcuts, draft))
        throw new Error("unavailable");
      this.saved = {...draft};
      this.state = state;
      this.dirty = false;
      this.notice(state.tv_shortcuts_restart_required ? "Сохранено. Для применения перезапустите ТВ-режим." :
        "Назначения сохранены.");
      this.onSaved();
    } catch (_) {
      if (this.active && epoch === this.epoch) {
        await this.refresh(epoch);
        if (this.active && epoch === this.epoch && !this.conflict)
          this.notice("Не удалось сохранить. Кнопка может быть занята или версия ТВ-режима не поддерживается.");
      }
    } finally {
      if (this.active && epoch === this.epoch) { this.busy = false; this.phase = null; this.render(); }
    }
  }
}
if (typeof module !== "undefined") module.exports = {TvShortcutControls};
