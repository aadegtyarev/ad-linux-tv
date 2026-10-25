"use strict";

class AudioLevelsControls {
  constructor(prefix, levels, change, dragging = () => {}) {
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

  actions() { return this.controls.map(control => control.slider); }

  render(state) {
    for (const {name, slider, value, hint} of this.controls) {
      const level = name === "output" ? state.volume : state[`${name}_target`] ?? 100;
      slider.value = level;
      value.textContent = `${level}%`;
      if (!hint) continue;
      if (name === "browser") hint.textContent = state.browser_volume === null
        ? "Поток Firefox сейчас не играет; применится при запуске."
        : `Сейчас: ${state.browser_volume}%.`;
      if (name === "player") hint.textContent = state.browser_volume === null
        ? "Плеер сейчас не играет; применится при запуске."
        : "Применится к доступному плееру страницы.";
    }
  }
}
