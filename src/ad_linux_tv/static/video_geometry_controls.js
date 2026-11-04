"use strict";

// One explicit request at a time. A queue receipt is not proof that the
// extension actually applied the effect; a lost/late result is never replayed.
class VideoGeometryControls {
  constructor(root, request, onAuth, notify) {
    this.root = root;
    this.request = request;
    this.onAuth = onAuth;
    this.notify = notify;
    this.mode = root.querySelector('[data-video="mode"]');
    this.mirror = root.querySelector('[data-video="mirror"]');
    this.applyButton = root.querySelector('[data-video="apply"]');
    this.note = root.querySelector('[data-video="status"]');
    this.active = false;
    this.busy = false;
    this.epoch = 0;
    this.mediaId = null;
    this.applyButton.onclick = () => void this.apply();
    this.render();
  }

  render() {
    const disabled = !this.active || this.busy || !this.mediaId;
    this.mode.disabled = disabled;
    this.mirror.disabled = disabled;
    this.applyButton.disabled = disabled;
    this.root.setAttribute("aria-busy", String(this.busy));
  }

  current(epoch) { return this.active && epoch === this.epoch; }

  async state(epoch) {
    const response = await this.request("GET", "/api/video-geometry");
    if (!this.current(epoch)) return null;
    if (response.status === 401 || response.status === 403) { this.onAuth(); return null; }
    if (!response.ok) throw new Error("unavailable");
    const state = await response.json();
    if (!this.current(epoch)) return null;
    if (typeof state?.available !== "boolean" ||
        !(state.media_id === null || (typeof state.media_id === "string" &&
          /^[0-9a-f]{32}$/.test(state.media_id))) || state.available !== (state.media_id !== null))
      throw new Error("invalid state");
    return state;
  }

  activate() {
    this.active = true;
    this.busy = false;
    this.mediaId = null;
    const epoch = ++this.epoch;
    this.note.textContent = "Проверяем видео…";
    this.render();
    void this.state(epoch).then(state => {
      if (!state || !this.current(epoch)) return;
      this.mediaId = state.available ? state.media_id : null;
      this.note.textContent = this.mediaId ? "Выберите формат и зеркало, затем нажмите «Применить»." :
        "Нет доступного видео или расширение нужно обновить.";
      this.render();
    }).catch(() => {
      if (!this.current(epoch)) return;
      this.note.textContent = "Не удалось проверить видео.";
      this.render();
    });
  }

  deactivate() {
    this.active = false;
    this.busy = false;
    this.mediaId = null;
    this.epoch++;
    this.render();
  }

  async apply() {
    if (!this.active || this.busy || !this.mediaId) return;
    const epoch = this.epoch, expected = this.mediaId;
    const mode = this.mode.value, mirror = this.mirror.checked;
    if (!["original", "4:3", "16:9"].includes(mode) || typeof mirror !== "boolean") return;
    this.busy = true;
    this.note.textContent = "Применяем…";
    this.render();
    try {
      const state = await this.state(epoch);
      if (!state || !this.current(epoch)) return;
      if (!state.available || state.media_id !== expected) throw new Error("changed");
      const response = await this.request("POST", "/api/video-geometry", {
        action:"apply", media_id:expected, mode, mirror,
      });
      if (!this.current(epoch)) return;
      if (response.status === 401 || response.status === 403) { this.onAuth(); return; }
      if (response.status !== 202) throw new Error("unavailable");
      const {id} = await response.json();
      if (!this.current(epoch)) return;
      if (typeof id !== "string" || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) throw new Error("invalid");
      const until = Date.now() + 7000;
      while (this.current(epoch) && Date.now() < until) {
        const result = await this.request("POST", "/api/video-geometry", {action:"result", id});
        if (!this.current(epoch)) return;
        if (result.status === 401 || result.status === 403) { this.onAuth(); return; }
        if (result.status === 200) {
          const receipt = await result.json();
          if (!this.current(epoch)) return;
          if (receipt?.id !== id || receipt.outcome !== "completed") throw new Error("unavailable");
          const latest = await this.state(epoch);
          if (!latest || !this.current(epoch)) return;
          if (!latest.available || latest.media_id !== expected) throw new Error("changed");
          this.note.textContent = "Настройка применена.";
          this.notify("Настройка видео применена.", false);
          return;
        }
        if (result.status !== 202) throw new Error("unavailable");
        await new Promise(resolve => setTimeout(resolve, 350));
      }
      throw new Error("unconfirmed");
    } catch (_) {
      if (!this.current(epoch)) return;
      this.note.textContent = "Плеер не поддерживается или результат не подтверждён.";
      this.notify("Не удалось изменить видео на этом плеере.", true);
    } finally {
      if (this.current(epoch)) { this.busy = false; this.render(); }
    }
  }
}
if (typeof module !== "undefined") module.exports = {VideoGeometryControls};
