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
    this.feedback = document.querySelector("#media-feedback");
    this.feedbackText = "";
    this.feedbackTimer = null;
    this.buttons = {
      previous: document.querySelector("#media-previous"),
      play: document.querySelector("#media-play"),
      next: document.querySelector("#media-next"),
    };
    this.timer = null;
    this.revision = 0;
    this.epoch = 0;
    this.active = true;
    this.dragging = false;
    this.inFlight = new Set();
    this.refreshRequest = null;
    this.lastPoll = 0;
    this.pendingSeek = null;
    this.pendingPlayback = null;
    this.message = "";
    this.state = null;
    this.position.addEventListener("pointerdown", () => { this.dragging = true; });
    for (const name of ["pointerup", "pointercancel"])
      this.position.addEventListener(name, () => { this.dragging = false; });
    this.position.oninput = () => {
      this.elapsed.textContent = PhoneMediaControls.time(Number(this.position.value));
    };
    this.position.onchange = () => {
      this.dragging = false;
      if (this.state?.can_seek) void this.command("seek", Number(this.position.value));
    };
    this.buttons.previous.onclick = () => void this.command("previous");
    this.buttons.next.onclick = () => void this.command("next");
    this.buttons.play.onclick = () => void this.command(this.state?.playing ? "pause" : "play");
  }

  static time(seconds) {
    const value = Math.max(0, Math.floor(seconds || 0));
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
  }

  static playbackIcon(playing) {
    // Fixed vector markup, never server text or platform-dependent emoji glyphs.
    const path = playing ? '<path d="M8 5h6v22H8zm10 0h6v22h-6z"/>'
      : '<path d="m10 5 17 11-17 11z"/>';
    return `<svg viewBox="0 0 32 32" aria-hidden="true" data-icon="${playing ? "pause" : "play"}">${path}</svg>`;
  }

  render(state, confirm = true) {
    if (!state || typeof state !== "object") throw new Error("invalid media state");
    this.state = state.available === true ? state : null;
    this.panel.hidden = !this.state;
    if (this.state) this.face.classList.add("has-media");
    else this.face.classList.remove("has-media");
    if (!this.state) {
      this.pendingSeek = this.pendingPlayback = null;
      this.message = "";
      this.showFeedback("");
      return;
    }
    const pending = this.pendingPlayback || this.pendingSeek;
    if (pending?.mediaId && pending.mediaId !== state.media_id) {
      this.pendingPlayback = this.pendingSeek = null;
      this.message = "Источник воспроизведения изменился";
    }
    if (confirm && this.pendingPlayback && state.playing === this.pendingPlayback.playing) {
      this.pendingPlayback = null;
      this.message = "";
    }
    if (confirm && this.pendingSeek && state.position !== null
        && Math.abs(state.position - this.pendingSeek.target) <= 3) {
      this.pendingSeek = null;
      this.message = "";
    }
    if ((this.pendingPlayback && Date.now() >= this.pendingPlayback.deadline)
        || (this.pendingSeek && Date.now() >= this.pendingSeek.deadline)) {
      this.pendingPlayback = this.pendingSeek = null;
      this.message = "Плеер не подтвердил команду";
    }
    const busy = this.inFlight.size > 0 || !!this.pendingPlayback || !!this.pendingSeek;
    this.panel.setAttribute("aria-busy", String(busy));
    this.title.textContent = state.title || "Воспроизведение";
    this.title.setAttribute("aria-label", this.title.textContent);
    this.buttons.previous.disabled = busy || !state.can_previous;
    this.buttons.next.disabled = busy || !state.can_next;
    const shownPlaying = this.pendingPlayback ? this.pendingPlayback.playing : state.playing === true;
    this.buttons.play.disabled = busy || (state.playing ? !state.can_pause : !state.can_play);
    this.buttons.play.setAttribute("data-pending", String(!!this.pendingPlayback));
    this.buttons.play.innerHTML = PhoneMediaControls.playbackIcon(shownPlaying);
    this.buttons.play.setAttribute("aria-label", shownPlaying ? "Пауза" : "Воспроизвести");
    this.position.disabled = busy || !state.can_seek;
    this.position.max = state.duration || 1;
    this.duration.textContent = state.duration === null ? "—" : PhoneMediaControls.time(state.duration);
    if (!this.dragging && !this.pendingSeek) {
      this.position.value = state.position ?? 0;
      this.elapsed.textContent = state.position === null ? "—" : PhoneMediaControls.time(state.position);
    }
    this.showFeedback(busy ? "Ожидаем подтверждение…" : this.message);
  }

  showFeedback(text) {
    if (!this.feedback || text === this.feedbackText) return;
    this.feedbackText = text;
    if (this.feedbackTimer !== null) clearTimeout(this.feedbackTimer);
    this.feedbackTimer = null;
    this.feedback.textContent = text;
    if (text) this.feedbackTimer = setTimeout(() => {
      this.feedback.textContent = "";
      this.feedbackTimer = null;
    }, 5000);
  }

  current(token) {
    return this.active && token.epoch === this.epoch && token.revision === this.revision;
  }

  async refresh() {
    if (!this.active || this.inFlight.size || this.refreshRequest) return;
    const token = {epoch:this.epoch, revision:++this.revision};
    this.refreshRequest = token;
    this.lastPoll = Date.now();
    try {
      const response = await this.request("GET", "/api/media");
      if (!this.current(token)) return;
      if (response.status === 401 || response.status === 403) return this.onAuth();
      if (!response.ok) throw new Error("media unavailable");
      const state = await response.json();
      if (this.current(token)) this.render(state);
    } catch (_) {
      if (this.current(token)) this.render({available:false});
    } finally {
      if (this.refreshRequest === token) this.refreshRequest = null;
    }
  }

  reconcile() {
    if (!this.active || this.inFlight.size) return;
    // A backgrounded WebView may retain a GET whose transport never settled.
    // Retire only that read; never resend a playback/seek command on resume.
    this.revision += 1;
    this.refreshRequest = null;
    void this.refresh();
  }

  async command(action, position) {
    if (!this.active || !this.state || this.inFlight.size || this.pendingPlayback || this.pendingSeek) return;
    const token = {epoch:this.epoch, revision:++this.revision};
    this.refreshRequest = null; // Old GET may finish, but cannot block/rewrite this operation.
    const mediaId = this.state.media_id;
    if (action === "play" || action === "pause") {
      this.pendingPlayback = {playing:action === "play", deadline:Date.now() + 5000, mediaId};
    } else if (action === "seek") {
      this.pendingSeek = {target:position, deadline:Date.now() + 5000, mediaId};
    }
    this.inFlight.add(token);
    this.message = "";
    this.render(this.state, false); // Immediate provisional feedback, not playback confirmation.
    try {
      const body = {action};
      if (action === "seek") body.position = position;
      if (mediaId) body.media_id = mediaId;
      const response = await this.request("POST", "/api/media", body);
      if (!this.current(token)) return;
      if (response.status === 401 || response.status === 403) return this.onAuth();
      if (!response.ok) throw new Error("media command failed");
      const state = await response.json();
      if (this.current(token)) this.render(state, false);
    } catch (_) {
      if (this.current(token)) {
        this.pendingPlayback = this.pendingSeek = null;
        this.message = "Команда не подтверждена; повторите при необходимости";
      }
    } finally {
      this.inFlight.delete(token);
      if (this.current(token)) {
        if (this.state) this.render(this.state, false);
        void this.refresh(); // Read-only reconciliation; never resend an uncertain command.
      }
    }
  }

  start() {
    this.stop();
    this.active = true;
    void this.refresh();
    this.timer = setInterval(() => {
      if (this.pendingPlayback || this.pendingSeek || Date.now() - this.lastPoll >= 2000)
        void this.refresh();
    }, 250);
  }

  stop() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.epoch += 1;
    this.revision += 1;
    this.active = false;
    this.dragging = false;
    this.inFlight.clear();
    this.refreshRequest = null;
    this.pendingSeek = this.pendingPlayback = null;
    this.render({available:false});
  }
}
