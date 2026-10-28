"use strict";

class SettingsControls {
  constructor(root, request, onPinChange = () => {}, onState = () => {}) {
    this.root = root;
    this.request = request;
    this.onPinChange = onPinChange;
    this.onState = onState;
    this.state = null;
    this.magnifierShortcut = null;
    this.viewScope = "";
    this.viewDirty = false;
    this.viewRevision = 0;
    this.viewEditRevision = 0;
    this.viewWriteRevision = 0;
    this.viewWritePending = false;
    this.refreshRevision = 0;
    this.viewSnapshotRevision = 0;
    this.viewAppliedSnapshot = 0;
    this.field = name => root.querySelector(`[data-role="${name}"]`);
    this.fields = name => Array.from(root.querySelectorAll(`[data-role="${name}"]`));
    this.field("pin-mode").onchange = () => this.renderFields();
    this.field("proxy-mode").onchange = () => this.renderFields();
    this.field("pin-form").onsubmit = event => { event.preventDefault(); void this.savePin(); };
    this.field("proxy-form").onsubmit = event => { event.preventDefault(); void this.saveProxy(); };
    if (this.field("locale-form")) this.field("locale-form").onsubmit = event => {
      event.preventDefault();
      void this.change("browser_locale", this.field("browser-locale").value);
    };
    if (this.field("magnifier")) this.field("magnifier").onclick = () =>
      void this.change("magnifier", !this.state?.magnifier);
    this.field("restart").onclick = () => void this.change("restart", true);
    if (this.field("about")) this.field("about").ontoggle = () => {
      if (this.field("about").open) this.renderAbout();
    };
    if (this.field("view-form")) {
      this.field("view-form").onsubmit = event => {
        event.preventDefault();
        void this.saveView();
      };
      this.field("view-default").onclick = () => void this.resetView();
      this.field("view-scope").onchange = () => {
        this.viewScope = this.field("view-scope").value;
        this.viewDirty = false;
        this.viewRevision++;
        this.applyViewState();
      };
      this.field("view-zoom").oninput = () => {
        this.viewEditRevision++;
        this.viewDirty = true;
        this.field("view-zoom-value").textContent = `${this.field("view-zoom").value}%`;
        this.field("view-hint").textContent = "Изменения ещё не сохранены.";
      };
      this.field("view-mode").onchange = () => {
        this.viewEditRevision++;
        this.viewDirty = true;
        this.field("view-hint").textContent = "Изменения ещё не сохранены.";
      };
    }
    if (this.field("magnifier-scale")) {
      const slider = this.field("magnifier-scale");
      slider.oninput = () => { this.field("magnifier-scale-value").textContent = `${Number(slider.value).toLocaleString("ru-RU")}×`; };
      slider.onchange = () => void this.change("magnifier_scale", Number(slider.value));
    }
    if (this.field("pointer-acceleration")) {
      const slider = this.field("pointer-acceleration");
      slider.oninput = () => { this.field("pointer-acceleration-value").textContent = `${slider.value}%`; };
      slider.onchange = () => void this.change("pointer_acceleration", Number(slider.value));
    }
  }

  actions() {
    return Array.from(this.root.querySelectorAll("input,select,button,summary"));
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

  renderAbout() {
    // Public display metadata only: a page may supply its own app-info object.
    const unknown = "неизвестно";
    const server = this.state?.server;
    const version = server?.version;
    const build = server?.build;
    if (this.field("server-version")) this.field("server-version").textContent =
      typeof version === "string" && /^[A-Za-z0-9.+!_-]{1,80}$/.test(version) && version === version.trim() && version !== "unknown" ? version : unknown;
    if (this.field("server-build")) this.field("server-build").textContent =
      typeof build === "string" && build.length === 16 && /^[a-f0-9]{16}$/.test(build) ? build : unknown;
    const app = window.adLinuxTvAppInfo;
    if (this.field("app-info")) this.field("app-info").hidden = !app || typeof app !== "object";
    const appVersion = app?.version;
    const appBuild = app?.build;
    if (this.field("app-version")) this.field("app-version").textContent =
      typeof appVersion === "string" && appVersion.length >= 1 && appVersion.length <= 80 &&
      appVersion.trim() && !/[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/.test(appVersion) && appVersion !== "unknown"
        ? appVersion : unknown;
    if (this.field("app-build")) this.field("app-build").textContent =
      Number.isInteger(appBuild) && appBuild >= 1 && appBuild <= 2147483647 ? String(appBuild) : unknown;
  }

  viewSnapshot() {
    return {sequence:++this.viewSnapshotRevision, write:this.viewWriteRevision,
      pending:this.viewWritePending, scope:this.viewRevision, edit:this.viewEditRevision};
  }

  mergeViewState(state, snapshot) {
    const accept = !this.state || (!this.viewDirty && !snapshot.pending && !this.viewWritePending &&
      snapshot.write === this.viewWriteRevision && snapshot.scope === this.viewRevision &&
      snapshot.edit === this.viewEditRevision && snapshot.sequence >= this.viewAppliedSnapshot);
    if (accept) {
      this.viewAppliedSnapshot = snapshot.sequence;
      return state;
    }
    // Settings replies are full snapshots, even for unrelated writes. Keep the
    // entire view slice together, not just the visible fields of the active scope.
    return this.withViewState(state, this.state);
  }

  withViewState(state, viewState) {
    const merged = {...state};
    const isView = key => key === "view" || key === "service_views" ||
      key === "effective_service_views" || key.startsWith("view_");
    for (const key of Object.keys(merged)) if (isView(key)) delete merged[key];
    for (const [key, value] of Object.entries(viewState)) if (isView(key)) merged[key] = value;
    merged.restart_required = !!(merged.proxy_restart_required || merged.browser_locale_restart_required ||
      (merged.magnifier_scale ?? 2.5) !== (merged.magnifier_applied_scale ?? 2.5) ||
      merged.view_restart_required);
    return merged;
  }

  render(state, snapshot = this.viewSnapshot()) {
    state = this.mergeViewState(state, snapshot);
    this.state = state;
    this.renderAbout();
    this.onState(state);
    if (this.field("pointer-acceleration")) {
      const level = state.pointer_acceleration ?? 50;
      this.field("pointer-acceleration").value = level;
      this.field("pointer-acceleration-value").textContent = `${level}%`;
    }
    const scale = state.magnifier_scale ?? 2.5;
    const appliedScale = state.magnifier_applied_scale ?? 2.5;
    if (this.field("magnifier-scale")) {
      this.field("magnifier-scale").value = scale;
      this.field("magnifier-scale-value").textContent = `${scale.toLocaleString("ru-RU")}×`;
      this.field("magnifier-hint").textContent = scale !== appliedScale
        ? "Новый масштаб применится после перезапуска ТВ-режима. Просмотр сейчас не прерывается."
        : `Текущий масштаб: ${appliedScale.toLocaleString("ru-RU")}×`;
    }
    if (this.field("view-form")) {
      const scope = this.field("view-scope");
      const selected = scope.value || "common";
      const services = Array.isArray(state.service_views) ? state.service_views : null;
      if (services && scope.options) {
        const wanted = selected;
        while (scope.options.length > 1) scope.remove(1);
        for (const service of services) {
          const option = document.createElement("option");
          option.value = service.id;
          option.textContent = service.name;
          scope.append(option);
        }
        scope.value = services.some(item => item.id === wanted) ? wanted : "common";
      } else {
        while (scope.options && scope.options.length > 1) scope.remove(1);
        scope.value = "common";
      }
      this.viewScope = scope.value || "common";
      this.applyViewState();
    }
    this.field("pin-mode").value = state.require_pin ? "on" : "off";
    if (this.field("magnifier")) {
      this.field("magnifier").textContent = state.magnifier ? "Выключить лупу" : `Включить ×${appliedScale.toLocaleString("ru-RU")}`;
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
    if (this.field("browser-locale")) {
      const locale = state.browser_locale || "ru";
      const installed = state.browser_locales_installed || ["ru", "en"];
      this.field("browser-locale").value = locale;
      this.field("locale-hint").textContent = state.browser_locale_restart_required
        ? "Язык применится после перезапуска ТВ-режима."
        : installed.includes(locale) ? "" : "Языковой пакет не установлен: Firefox останется на английском.";
    }
    this.renderRestart();
    this.field("pin").value = "";
    this.field("pin-confirm").value = "";
    this.renderFields();
  }

  renderRestart() {
    this.field("proxy-restart").hidden = !(this.state.restart_required ?? this.state.proxy_restart_required);
  }

  async refresh() {
    const revision = ++this.refreshRevision;
    const scopeRevision = this.viewRevision;
    const writeRevision = this.viewWriteRevision;
    const pending = this.viewWritePending;
    const snapshot = this.viewSnapshot();
    const current = () => revision === this.refreshRevision &&
      writeRevision === this.viewWriteRevision && !pending && !this.viewWritePending;
    try {
      const response = await this.request("GET", null);
      if (!response.ok) throw new Error("unavailable");
      const state = await response.json();
      if (!current()) return false;
      this.render(state, snapshot);
      if (scopeRevision !== this.viewRevision) return true;
      this.notice("");
      return true;
    } catch (_) {
      if (current() && scopeRevision === this.viewRevision)
        this.notice("Настройки недоступны. Повторите позже.", true);
      return false;
    }
  }

  async change(setting, value) {
    const snapshot = this.viewSnapshot();
    try {
      const response = await this.request("POST", {setting, value});
      if (!response.ok) throw new Error("rejected");
      this.render(await response.json(), snapshot);
      this.notice(setting === "proxy" ? "Прокси сохранён. Перезапустите ТВ-режим для применения."
        : setting === "browser_locale" ? "Язык сохранён. Перезапустите ТВ-режим для применения."
        : setting === "magnifier_scale" && this.state.restart_required ? "Масштаб сохранён. Для применения нужен перезапуск ТВ-режима."
        : setting === "restart" ? "Перезапускаем ТВ-режим…" : "Сохранено.");
      if (setting === "pin") this.onPinChange();
    } catch (_) {
      this.notice("Не удалось сохранить. Проверьте данные и повторите.", true);
    }
  }

  viewForScope(state = this.state) {
    if (this.viewScope === "common") return {view:state?.view ?? {mode:"desktop",zoom:125}, explicit:true};
    const service = state?.service_views?.find(item => item.id === this.viewScope);
    return service ? {view:service.view || service.effective_view, explicit:!!service.view} : null;
  }

  applyViewState() {
    if (!this.state || !this.field("view-form")) return;
    const selected = this.viewForScope();
    if (!selected) return;
    if (!this.viewDirty) {
      this.field("view-mode").value = selected.view.mode;
      this.field("view-zoom").value = selected.view.zoom;
    }
    this.field("view-zoom-value").textContent = `${this.field("view-zoom").value}%`;
    const individual = this.viewScope !== "common";
    this.field("view-default").textContent = individual ? "Как для всех сайтов" : "По умолчанию";
    const notice = individual && !selected.explicit ? "Используются общие настройки" : "";
    this.field("view-inherited").textContent = notice;
    this.field("view-inherited").hidden = !notice;
    const legacy = !Array.isArray(this.state.service_views);
    this.field("view-scope").disabled = legacy;
    if (!this.viewDirty) this.field("view-hint").textContent = this.viewApplyHint();
  }

  viewApplyHint() {
    return this.state.view_restart_required
      ? "Перезапустите ТВ-режим, затем откройте плитку заново. Просмотр сейчас не прерывается."
      : this.state.view_profile_ready && this.state.view_bridge_ready
        ? "Применится при следующем открытии плитки. Текущая страница не перезагружается."
        : "Состояние профиля и расширения: " +
          `${this.state.view_profile_ready ? "профиль готов" : "профиль не готов"}, ` +
          `${this.state.view_bridge_ready ? "расширение готово" : "расширение не готово"}.`;
  }

  async saveView() {
    const view = {mode:this.field("view-mode").value, zoom:Number(this.field("view-zoom").value)};
    await this.writeView(view);
  }

  async resetView() {
    await this.writeView(null);
  }

  async writeView(view) {
    // Do not queue or replay uncertain writes, including double clicks.
    if (this.viewWritePending) {
      this.notice("Дождитесь завершения сохранения и повторите.");
      return;
    }
    const scope = this.viewScope;
    const revision = this.viewRevision;
    const editRevision = this.viewEditRevision;
    const current = () => scope === this.viewScope && revision === this.viewRevision;
    this.viewWritePending = true;
    this.viewWriteRevision++;
    this.viewDirty = true;
    try {
      const response = await this.request("POST", scope === "common"
        ? {setting:"view", value:view}
        : {setting:"service_view", value:{id:scope, view}});
      if (!response.ok) throw new Error("rejected");
      const state = await response.json();
      if (!current()) return;
      // A view write changes only the view slice. A delayed full ACK must not
      // roll back newer unrelated settings accepted while this write was pending.
      this.state = this.withViewState({...this.state, server:state.server}, state);
      this.renderAbout();
      this.renderRestart();
      this.viewDirty = editRevision !== this.viewEditRevision;
      this.applyViewState();
      const saved = this.viewDirty ? "Вид сохранён. Новые изменения ещё не сохранены."
        : view !== null ? "Вид сохранён."
        : scope === "common" ? "Общий вид восстановлен: обычный, 125%." : "Используются общие настройки.";
      this.notice(`${saved} ${this.viewApplyHint()}`);
    } catch (_) {
      if (current()) this.notice(view !== null
        ? "Не удалось подтвердить сохранение вида сайтов. Проверьте настройки и повторите."
        : "Не удалось подтвердить сброс вида сайта. Проверьте настройки и повторите.", true);
    } finally {
      // Also fence GETs started during the write, even if they finish after it.
      this.viewWriteRevision++;
      this.viewWritePending = false;
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
