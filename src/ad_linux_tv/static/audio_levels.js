"use strict";

class AudioLevelsControls {
  constructor(prefix, levels, change, dragging = () => {}) {
    this.browserMute = document.querySelector(`#${prefix}-browser-mute`);
    if (this.browserMute) this.browserMute.onclick = () => {
      if (!this.browserMute.disabled)
        void change({browser_muted: this.browserMute.dataset.muted !== "true"});
    };
    this.controls = levels.map(([name, action]) => {
      const slider = document.querySelector(`#${prefix}-${name}-volume`);
      const value = document.querySelector(`#${prefix}-${name}-value`);
      const hint = document.querySelector(`#${prefix}-${name}-hint`);
      slider.oninput = () => { value.textContent = `${slider.value}%`; };
      slider.onchange = () => void change({[action]: Number(slider.value)});
      for (const eventName of ["pointerdown", "pointerup", "pointercancel"])
        slider.addEventListener(eventName, () => dragging(eventName === "pointerdown"));
      return {name, slider, value, hint};
    });
  }

  sliders() { return this.controls.map(control => control.slider); }

  actions() { return [...this.sliders(), ...(this.browserMute ? [this.browserMute] : [])]; }

  render(state) {
    for (const {name, slider, value, hint} of this.controls) {
      const level = name === "output" ? state.volume : state[`${name}_target`] ?? 100;
      slider.value = level;
      value.textContent = `${level}%`;
      if (!hint) continue;
      if (name === "browser") hint.textContent = state.browser_volume === null
        ? "Поток Firefox сейчас не играет; применится при запуске."
        : state.browser_muted ? `Поток Firefox заглушён; уровень ${state.browser_volume}%.`
          : `Сейчас: ${state.browser_volume}%.`;
      if (name === "player") hint.textContent = state.browser_volume === null
        ? "Плеер сейчас не играет; применится при запуске."
        : "Применится к доступному плееру страницы.";
    }
    if (this.browserMute) {
      const muted = state.browser_muted;
      this.browserMute.disabled = typeof muted !== "boolean";
      this.browserMute.dataset.muted = String(muted);
      this.browserMute.textContent = typeof muted !== "boolean"
        ? "Нет потока" : muted ? "Включить" : "Отключить";
      this.browserMute.setAttribute("aria-label", typeof muted !== "boolean"
        ? "Звук Firefox недоступен: нет потока"
        : muted ? "Включить звук Firefox" : "Выключить звук Firefox");
    }
  }
}
