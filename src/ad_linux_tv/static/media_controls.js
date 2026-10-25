"use strict";

class PhoneMediaControls {
  constructor(request, onAuth) {
    this.request = request;
    this.onAuth = onAuth;
    this.panel = document.querySelector("#media-panel");
    this.face = document.querySelector("#remote-face");
    this.title = document.querySelector("#media-title");
    this.elapsed = document.querySelector("#media-elapsed");
    this.duration = document.querySelector("#media-duration");
    this.position = document.querySelector("#media-position");
    this.buttons = {
      previous: document.querySelector("#media-previous"),
      play: document.querySelector("#media-play"),
      next: document.querySelector("#media-next"),
    };
    this.timer = null;
    this.revision = 0;
    this.dragging = false;
    this.commandsInFlight = 0;
    this.pendingSeek = null;
    this.state = null;
    this.position.addEventListener("pointerdown", () => { this.dragging = true; });
    for (const name of ["pointerup", "pointercancel"])
      this.position.addEventListener(name, () => { this.dragging = false; });
    this.position.oninput = () => {
      this.elapsed.textContent = PhoneMediaControls.time(Number(this.position.value));
    };
    this.position.onchange = () => {
      this.dragging = false;
      if (this.state?.can_seek) {
        const target = Number(this.position.value);
        this.pendingSeek = {target, deadline: Date.now() + 5000};
        void this.command("seek", target);
      }
    };
    this.buttons.previous.onclick = () => void this.command("previous");
    this.buttons.next.onclick = () => void this.command("next");
    this.buttons.play.onclick = () => void this.command(this.state?.playing ? "pause" : "play");
  }

  static time(seconds) {
    const value = Math.max(0, Math.floor(seconds || 0));
    const minutes = Math.floor(value / 60);
    const tail = String(value % 60).padStart(2, "0");
    return `${minutes}:${tail}`;
  }

  render(state, confirmSeek = true) {
    this.state = state.available ? state : null;
    this.panel.hidden = !state.available;
    if (state.available) this.face.classList.add("has-media");
    else this.face.classList.remove("has-media");
    if (!state.available) {
      this.pendingSeek = null;
      return;
    }
    if (confirmSeek && this.pendingSeek && (
      (state.position !== null && Math.abs(state.position - this.pendingSeek.target) <= 3)
      || Date.now() >= this.pendingSeek.deadline
    )) this.pendingSeek = null;
    this.title.textContent = state.title || "Воспроизведение";
    this.title.setAttribute("aria-label", this.title.textContent);
    this.buttons.previous.disabled = !state.can_previous;
    this.buttons.next.disabled = !state.can_next;
    this.buttons.play.disabled = state.playing ? !state.can_pause : !state.can_play;
    this.buttons.play.textContent = state.playing ? "⏸" : "▶";
    this.buttons.play.setAttribute("aria-label", state.playing ? "Пауза" : "Воспроизвести");
    this.position.disabled = !state.can_seek;
    this.position.max = state.duration || 1;
    this.duration.textContent = state.duration === null ? "—" : PhoneMediaControls.time(state.duration);
    if (!this.dragging && !this.pendingSeek) {
      this.position.value = state.position ?? 0;
      this.elapsed.textContent = state.position === null ? "—" : PhoneMediaControls.time(state.position);
    }
  }

  async refresh() {
    if (this.commandsInFlight) return;
    const revision = ++this.revision;
    try {
      const response = await this.request("GET", "/api/media");
      if (response.status === 401 || response.status === 403) return this.onAuth();
      if (!response.ok) throw new Error("media unavailable");
      const state = await response.json();
      if (revision === this.revision) this.render(state);
    } catch (_) {
      if (revision === this.revision) this.render({available:false});
    }
  }

  async command(action, position) {
    if (!this.state) return;
    const revision = ++this.revision;
    this.commandsInFlight += 1;
    try {
      const body = {action};
      if (action === "seek") body.position = position;
      const response = await this.request("POST", "/api/media", body);
      if (response.status === 401 || response.status === 403) return this.onAuth();
      if (!response.ok) throw new Error("media command failed");
      const state = await response.json();
      // SetPosition can reply before the next MPRIS snapshot has settled.
      if (revision === this.revision) this.render(state, false);
    } catch (_) {
      if (action === "seek" && this.pendingSeek?.target === position) this.pendingSeek = null;
    } finally {
      this.commandsInFlight -= 1;
      if (revision === this.revision) void this.refresh();
    }
  }

  start() {
    this.stop();
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), 2000);
  }

  stop() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.revision += 1;
    this.pendingSeek = null;
    this.render({available:false});
  }
}
