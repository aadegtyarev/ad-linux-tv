"use strict";

class SettingsControls {
  constructor(root, request, onPinChange = () => {}, onState = () => {}) {
    this.root = root;
    this.request = request;
    this.onPinChange = onPinChange;
    this.onState = onState;
    this.state = null;
    this.magnifierShortcut = null;
    this.field = name => root.querySelector(`[data-role="${name}"]`);
    this.fields = name => Array.from(root.querySelectorAll(`[data-role="${name}"]`));
    this.field("pin-mode").onchange = () => this.renderFields();
    this.field("proxy-mode").onchange = () => this.renderFields();
    this.field("pin-form").onsubmit = event => { event.preventDefault(); void this.savePin(); };
    this.field("proxy-form").onsubmit = event => { event.preventDefault(); void this.saveProxy(); };
    if (this.field("magnifier")) this.field("magnifier").onclick = () =>
      void this.change("magnifier", !this.state?.magnifier);
    this.field("restart").onclick = () => void this.change("restart", true);
    if (this.field("pointer-acceleration")) {
      const slider = this.field("pointer-acceleration");
      slider.oninput = () => { this.field("pointer-acceleration-value").textContent = `${slider.value}%`; };
      slider.onchange = () => void this.change("pointer_acceleration", Number(slider.value));
    }
  }

  actions() {
    return Array.from(this.root.querySelectorAll("input,select,button"));
  }

  bindMagnifierShortcut(button) {
    this.magnifierShortcut = button;
    button.onclick = async () => {
      if (await this.refresh()) await this.change("magnifier", !this.state.magnifier);
    };
  }

  notice(text, error = false) {
    const status = this.field("settings-status");
    status.textContent = text;
    status.dataset.error = String(error);
  }

  renderFields() {
    const pinOn = this.field("pin-mode").value === "on";
    for (const field of this.fields("pin-fields")) field.hidden = !pinOn;
    const custom = this.field("proxy-mode").value === "custom";
    for (const field of this.fields("proxy-fields")) field.hidden = !custom;
  }

  render(state) {
    this.state = state;
    this.onState(state);
    if (this.field("pointer-acceleration")) {
      const level = state.pointer_acceleration ?? 50;
      this.field("pointer-acceleration").value = level;
      this.field("pointer-acceleration-value").textContent = `${level}%`;
    }
    this.field("pin-mode").value = state.require_pin ? "on" : "off";
    if (this.field("magnifier")) {
      this.field("magnifier").textContent = state.magnifier ? "Выключить лупу" : "Включить ×2,5";
      this.field("magnifier").setAttribute("aria-pressed", String(state.magnifier));
    }
    if (this.magnifierShortcut) {
      this.magnifierShortcut.setAttribute("aria-pressed", String(state.magnifier));
      this.magnifierShortcut.setAttribute("aria-label", state.magnifier
        ? "Выключить лупу под курсором" : "Включить лупу под курсором");
      this.magnifierShortcut.querySelector("span").textContent = state.magnifier ? "⊖" : "⊕";
    }
    this.field("proxy-mode").value = state.proxy.mode;
    this.field("proxy-protocol").value = state.proxy.protocol || "http";
    this.field("proxy-host").value = state.proxy.host || "";
    this.field("proxy-port").value = state.proxy.port || "";
    this.field("proxy-restart").hidden = !state.proxy_restart_required;
    this.field("pin").value = "";
    this.field("pin-confirm").value = "";
    this.renderFields();
  }

  async refresh() {
    try {
      const response = await this.request("GET", null);
      if (!response.ok) throw new Error("unavailable");
      this.render(await response.json());
      this.notice("");
      return true;
    } catch (_) {
      this.notice("Настройки недоступны. Повторите позже.", true);
      return false;
    }
  }

  async change(setting, value) {
    try {
      const response = await this.request("POST", {setting, value});
      if (!response.ok) throw new Error("rejected");
      this.render(await response.json());
      this.notice(setting === "proxy" ? "Прокси сохранён. Перезапустите ТВ-режим для применения."
        : setting === "restart" ? "Перезапускаем ТВ-режим…" : "Сохранено.");
      if (setting === "pin") this.onPinChange();
    } catch (_) {
      this.notice("Не удалось сохранить. Проверьте данные и повторите.", true);
    }
  }

  async savePin() {
    const enabled = this.field("pin-mode").value === "on";
    const pin = enabled ? this.field("pin").value : null;
    const confirm = enabled ? this.field("pin-confirm").value : null;
    if (enabled && (!/^[0-9]{4}$/.test(pin) || pin !== confirm)) {
      this.notice("Введите одинаковый четырёхзначный PIN в оба поля.", true);
      return;
    }
    await this.change("pin", {enabled, pin, confirm});
  }

  async saveProxy() {
    const mode = this.field("proxy-mode").value;
    const value = mode === "custom" ? {
      mode, protocol: this.field("proxy-protocol").value,
      host: this.field("proxy-host").value.trim(), port: Number(this.field("proxy-port").value),
    } : {mode};
    await this.change("proxy", value);
  }
}
