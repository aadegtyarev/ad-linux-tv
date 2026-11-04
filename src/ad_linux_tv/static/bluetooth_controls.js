"use strict";

// This panel has no transport or authentication authority of its own.
class BluetoothControls {
  constructor(root, request, options = {}) {
    this.root = root;
    this.document = root.ownerDocument;
    this.request = request;
    this.options = options;
    const clock = options.clock || globalThis;
    this.later = clock.setTimeout.bind(clock);
    this.clear = clock.clearTimeout.bind(clock);
    this.now = clock.now ? clock.now.bind(clock) : () => globalThis.performance.now();
    this.nextRefresh = null;
    this.serial = Promise.resolve();
    this.transportPending = false;
    this.transportEpoch = 0;
    this.generation = 0;
    this.view = 0;
    this.active = false;
    this.lease = null;
    this.ownerReason = null;
    this.state = null;
    this.pending = false;
    this.timer = null;
    this.selected = null;
    this.action = "ok";
    this.message = "Откройте настройки Bluetooth.";
    this.challenge = null;
    this.observation = null;
    this.confirmation = null;
    this.retiredOperation = null;
    this.testAttempt = null;
    this.bindAttempt = null;
    this.onVisibility = () => { if (!this.visible()) this.deactivate(); };
    this.render();
  }

  static actions = Object.freeze({
    up: "Вверх", down: "Вниз", left: "Влево", right: "Вправо", ok: "Выбрать (OK)",
    back: "Назад", home: "На главную", play_pause: "Пауза / воспроизведение",
    seek_backward: "Назад на 10 секунд", seek_forward: "Вперёд на 10 секунд",
    volume_down: "Тише", volume_up: "Громче", mute: "Выключить / включить звук",
  });

  static keys = Object.freeze([
    "KEY_ESC", "KEY_ENTER", "KEY_KPENTER", "KEY_HOME", "KEY_UP", "KEY_LEFT", "KEY_RIGHT",
    "KEY_DOWN", "KEY_MUTE", "KEY_VOLUMEDOWN", "KEY_VOLUMEUP", "KEY_PAUSE", "KEY_BACK",
    "KEY_NEXTSONG", "KEY_PLAYPAUSE", "KEY_PREVIOUSSONG", "KEY_REWIND", "KEY_HOMEPAGE",
    "KEY_PLAY", "KEY_FASTFORWARD", "KEY_OK", "KEY_SELECT",
  ]);

  static messages = Object.freeze({
    busy: "Bluetooth занят другим управлением. Дождитесь завершения и нажмите «Повторить управление».",
    stale: "Срок управления истёк. Нажмите «Повторить управление».",
    invalid_lease: "Срок управления истёк. Нажмите «Повторить управление».",
    revision_mismatch: "Назначения изменились. Проверьте текущий список перед новым действием.",
    unavailable: "Bluetooth недоступен. Проверьте адаптер.",
    adapter_off: "Адаптер Bluetooth выключен. Вы можете включить его здесь.",
    helper_unavailable: "Управление кнопками недоступно. Обратитесь к администратору.",
    unsupported: "Это действие или кнопка не поддерживается.",
    identity_unproven: "Не удалось подтвердить устройство как пульт. Выберите другое устройство.",
    invalidated: "Устройство или операция изменились. Выберите устройство заново.",
    expired: "Время операции истекло. При необходимости запустите её заново.",
    cancelled: "Операция отменена. Уже отправленное действие могло выполниться; проверьте состояние.",
    uncertain: "Результат неизвестен. Проверьте состояние; запрос не будет повторён.",
    denied: "Действие не разрешено.", failed: "Не удалось выполнить действие. Проверьте состояние.",
    save_failed: "Не удалось сохранить назначения. Проверьте текущий список.",
  });

  text(code) {
    return Object.hasOwn(BluetoothControls.messages, code) ? BluetoothControls.messages[code] :
      "Не удалось выполнить действие. Проверьте состояние Bluetooth.";
  }

  visible() {
    return !this.document.hidden && !this.root.closest("[hidden]");
  }

  current(generation) { return this.active && this.generation === generation; }

  activate() {
    if (this.active || !this.visible()) return Promise.resolve();
    this.active = true;
    const generation = ++this.generation;
    this.document.addEventListener("visibilitychange", this.onVisibility);
    this.message = "Проверяем Bluetooth…";
    return this.run(async () => {
      if (!await this.receive("GET", null, generation)) return;
      await this.receive("POST", {op: "acquire"}, generation);
    });
  }

  deactivate() {
    const lease = this.lease;
    this.cleanup("Управление Bluetooth закрыто.");
    // Release is best effort, once for the captured lease. Expiry remains the guarantee.
    if (lease) void this.exchange("POST", {op: "release", lease}, null).catch(() => {});
  }

  retire() {
    ++this.transportEpoch;
    this.cleanup("Связь прервана. Откройте настройки заново после восстановления связи.");
  }

  cleanup(message) {
    this.active = false;
    ++this.generation;
    this.document.removeEventListener("visibilitychange", this.onVisibility);
    this.clear(this.timer);
    this.timer = null;
    this.nextRefresh = null;
    this.lease = null;
    this.ownerReason = null;
    this.pending = false;
    this.state = null;
    this.selected = null;
    this.retiredOperation = null;
    this.clearPrivate();
    this.message = message;
    this.render();
  }

  clearPrivate() {
    this.wipeInputs();
    if (this.challenge) this.challenge.value = "";
    this.challenge = null;
    this.observation = null;
    this.confirmation = null;
    this.answeredChallenge = null;
    this.forgetAttempt = null;
    this.testAttempt = null;
    this.bindAttempt = null;
  }

  wipeInputs() {
    for (const field of this.root.querySelectorAll("input")) field.value = "";
    // Also erase detached-node references held by integrations or browser autofill.
    for (const field of this.root.querySelectorAll("[data-secret]")) field.textContent = "";
  }

  actions() {
    if (!this.active || !this.visible()) return [];
    return Array.from(this.root.querySelectorAll("button, input, select"))
      .filter(element => !element.disabled && !element.closest("[hidden]"));
  }

  ownerPollDue() {
    return !!this.lease && this.nextRefresh !== null && this.now() >= this.nextRefresh;
  }

  schedule() {
    this.clear(this.timer);
    this.timer = null;
    if (!this.active) return;
    if (this.nextRefresh === null) this.nextRefresh = this.now() + 5000;
    this.timer = this.later(() => {
      this.timer = null;
      if (!this.visible()) { this.deactivate(); return; }
      // Keep the deadline overdue while busy; run() services it before enabling
      // more controls. Mutations never reset the heartbeat deadline.
      if (this.pending) return;
      const generation = this.generation;
      void this.run(() => this.receive(this.lease ? "POST" : "GET",
        this.lease ? {op: "poll", lease: this.lease} : null, generation));
    }, Math.max(0, this.nextRefresh - this.now()));
  }

  authorized(generation, transportEpoch) {
    return transportEpoch === this.transportEpoch &&
      (generation === null || (this.current(generation) && this.visible()));
  }

  // One serial lane, including priority heartbeats. Revalidate a queued mutation
  // after its heartbeat: polling may retire its operation, challenge or revision.
  exchange(method, body, generation, beforeDispatch) {
    const transportEpoch = this.transportEpoch;
    const task = this.serial.then(async () => {
      if (!this.authorized(generation, transportEpoch)) return null;
      if (generation !== null && body && !["acquire", "poll", "release"].includes(body.op)) {
        if (this.ownerPollDue()) {
          const poll = {op: "poll", lease: this.lease};
          const reply = await this.dispatch("POST", poll, generation, transportEpoch);
          if (!this.accept(reply, "POST", poll, generation)) return null;
        }
        if (!this.authorized(generation, transportEpoch) || !this.lease || body.lease !== this.lease) return null;
      }
      if (beforeDispatch && !beforeDispatch()) return null;
      return this.dispatch(method, body, generation, transportEpoch);
    });
    // Do not retain the last envelope (lease/challenge) in the serial tail.
    this.serial = task.then(() => undefined, () => undefined);
    return task;
  }

  // Bound the entire Response/body. The injected API has no abort parameter;
  // an unsettled timed-out request blocks replacement requests rather than
  // accumulating concurrent work. There is no microtask between the final
  // authority check and actual supplied request invocation.
  async dispatch(method, body, generation, transportEpoch) {
    if (!this.authorized(generation, transportEpoch)) return null;
    if (this.transportPending) throw new Error("transport still pending");
    this.transportPending = true;
    let timeout;
    try {
      return await Promise.race([
        (async () => {
          if (method === "GET" || ["acquire", "poll"].includes(body?.op))
            this.nextRefresh = this.now() + 5000;
          if (!this.authorized(generation, transportEpoch)) return null;
          const response = await this.request(method, "/api/bluetooth", ...(body ? [body] : []));
          if (response.status === 401 || response.status === 403)
            return {status: response.status, ok: false, body: null};
          return {status: response.status, ok: response.ok, body: await response.json()};
        })().finally(() => { this.transportPending = false; }),
        new Promise((resolve, reject) => {
          timeout = this.later(() => reject(new Error("timeout")), 8000);
        }),
      ]);
    } finally { this.clear(timeout); }
  }

  async run(work) {
    if (!this.active || this.pending || !this.visible()) return;
    const generation = this.generation;
    this.pending = true;
    this.render();
    try {
      await work();
      if (this.current(generation) && this.visible() && this.ownerPollDue())
        await this.receive("POST", {op: "poll", lease: this.lease}, generation);
    }
    catch {
      if (this.current(generation)) {
        this.retire();
        this.message = this.text("uncertain") + " Откройте настройки заново после восстановления связи.";
        this.render();
      }
    } finally {
      if (this.current(generation)) {
        this.pending = false;
        this.render();
        this.schedule();
      }
    }
  }

  async receive(method, body, generation, beforeDispatch) {
    return this.accept(await this.exchange(method, body, generation, beforeDispatch), method, body, generation);
  }

  accept(reply, method, body, generation) {
    if (!this.current(generation)) return false;
    if (!this.visible()) { this.deactivate(); return false; }
    if (!reply) return false;
    if (reply.status === 401 || reply.status === 403) {
      this.retire();
      this.message = "Доступ завершён. Войдите в пульт заново.";
      this.render();
      this.options.onAuthLost?.();
      return false;
    }
    const envelope = reply.body;
    if (!envelope || !this.validState(envelope.state)) throw new Error("invalid response");
    const oldOperation = this.state?.operation?.id;
    const oldTarget = this.state?.operation?.device_id;
    this.state = envelope.state;
    const operation = this.operation();
    if (oldOperation !== operation?.id) {
      this.clearPrivate();
      if (operation && operation.id !== this.retiredOperation) this.retiredOperation = null;
    }
    if (this.challenge) this.challenge.value = "";
    this.challenge = null;
    this.observation = null;
    this.confirmation = null;
    if (method === "POST" && body.op === "acquire" && reply.ok &&
        typeof envelope.lease === "string" && /^[0-9a-f]{32}$/.test(envelope.lease))
      this.lease = envelope.lease;
    if (body?.op === "acquire" && this.lease) this.ownerReason = null;
    if (method === "POST" && body.op === "acquire" && reply.ok && !this.lease)
      throw new Error("missing lease");
    if (["stale", "invalid_lease"].includes(envelope.error) ||
        (body?.op === "acquire" && !reply.ok)) {
      this.lease = null;
      this.ownerReason = envelope.error || "failed";
      this.clearPrivate();
    }
    if (operation && this.lease && method === "POST") {
      const target = this.state.devices.find(device => device.id === operation.device_id);
      const remote = this.state.remote;
      if ((oldOperation === operation.id && oldTarget !== operation.device_id) ||
          (operation.device_id !== null && !target) ||
          (["pair", "learn", "forget"].includes(operation.kind) && !target) ||
          (operation.kind === "learn" && (!target?.connected || !target.input_available ||
            remote?.device_id !== operation.device_id || !remote?.connected || !remote?.input_available))) {
        this.clearPrivate();
        this.retiredOperation = operation.id;
      }
    }
    if (this.lease && method === "POST" && operation && operation.phase !== "finished" &&
        operation.id !== this.retiredOperation) {
      const challenge = envelope.challenge;
      if (operation.kind === "pair" && challenge && this.handle(challenge.id) &&
          !(this.answeredChallenge?.operation_id === operation.id && this.answeredChallenge.id === challenge.id) &&
          ["pin", "passkey", "confirmation", "display_pin", "display_passkey"].includes(challenge.kind) &&
          Number.isInteger(challenge.remaining_ms) && challenge.remaining_ms > 0 &&
          (challenge.value === undefined || (typeof challenge.value === "string" && challenge.value.length <= 16)))
        this.challenge = {...challenge, operation_id: operation.id};
      const observation = envelope.observation;
      if (operation.kind === "learn" && observation && this.handle(observation.id) &&
          BluetoothControls.keys.includes(observation.key) &&
          Object.hasOwn(BluetoothControls.actions, observation.action) &&
          typeof observation.complete === "boolean" && typeof observation.tested === "boolean")
        this.observation = {...observation, operation_id: operation.id};
      if (operation.kind === "forget" && operation.id !== this.forgetAttempt &&
          operation.phase === "confirm" && this.handle(envelope.confirmation_id))
        this.confirmation = {id: envelope.confirmation_id, operation_id: operation.id};
    }
    if (!this.state.devices.some(device => device.id === this.selected))
      this.selected = this.state.devices.find(device => device.selected)?.id || null;
    this.message = envelope.error ? this.text(envelope.error) : !reply.ok ? this.text("failed") :
      reply.status === 202 ? "Запрос принят. Дождитесь подтверждения состояния устройства." : "";
    this.render();
    return reply.ok;
  }

  handle(value) { return typeof value === "string" && value.length > 0 && value.length <= 128; }

  validState(state) {
    const boolean = value => typeof value === "boolean";
    const deviceId = value => value === null || this.handle(value);
    const name = value => typeof value === "string" && Array.from(value).length <= 80;
    return state && boolean(state.available) && typeof state.reason === "string" && Number.isSafeInteger(state.revision) &&
      state.revision >= 0 && Array.isArray(state.devices) && state.devices.length <= 64 &&
      state.devices.every(device => device && this.handle(device.id) && name(device.name) &&
        ((device.bluez_name === undefined && device.alias === undefined) ||
          (name(device.bluez_name) && name(device.alias))) &&
        [device.paired, device.connected, device.selected, device.input_available].every(boolean)) &&
      (state.adapter === null || (state.adapter && this.handle(state.adapter.id) &&
        boolean(state.adapter.powered) && boolean(state.adapter.discovering))) &&
      (state.adapters === undefined || (Array.isArray(state.adapters) && state.adapters.length <= 8 &&
        state.adapters.every(a => a && this.handle(a.id) && typeof a.name === "string" &&
          Array.from(a.name).length <= 80 && typeof a.label === "string" &&
          /^…(?:[0-9A-F]{2}:){3}[0-9A-F]{2}$/.test(a.label) &&
          [a.powered, a.discovering, a.selectable].every(boolean)))) &&
      (state.adapter_preference === undefined || boolean(state.adapter_preference)) &&
      (state.operation === null || (state.operation && this.handle(state.operation.id) &&
        typeof state.operation.kind === "string" && typeof state.operation.phase === "string" &&
        deviceId(state.operation.device_id) && typeof state.operation.error === "string" &&
        Number.isSafeInteger(state.operation.remaining_ms) && state.operation.remaining_ms >= 0)) &&
      (state.remote === null || (state.remote && deviceId(state.remote.device_id) &&
        boolean(state.remote.connected) && boolean(state.remote.input_available) && typeof state.remote.reason === "string" &&
        state.remote.bindings && typeof state.remote.bindings === "object" && !Array.isArray(state.remote.bindings) &&
        Object.keys(state.remote.bindings).length <= 32));
  }

  deviceName(device) {
    if (!device) return "Без имени";
    // A legacy server has only `name`; do not infer its origin.
    if (device.bluez_name === undefined) return device.name || "Без имени";
    const name = device.bluez_name;
    const alias = device.alias;
    if (name && alias && name !== alias) return `${name} (псевдоним: ${alias})`;
    return name || alias || "Без имени";
  }

  operation() {
    const operation = this.state?.operation;
    return operation && operation.remaining_ms > 0 ? operation : null;
  }

  mutate(op, fields = {}) {
    if (!this.lease || !this.active || this.pending) return Promise.resolve();
    const body = {op, lease: this.lease, ...fields};
    const generation = this.generation;
    if (fields.operation_id && fields.operation_id !== this.operation()?.id) return Promise.resolve();
    const remoteId = this.state?.remote?.device_id;
    const clear = () => {
      this.wipeInputs();
      if (this.challenge) this.challenge.value = "";
      this.challenge = null;
      this.observation = null;
      this.confirmation = null;
    };
    // Cancel retires secrets immediately, even when an overdue heartbeat must
    // run first. Other staged identities remain available for revalidation.
    this.wipeInputs();
    if (op === "cancel") { this.retiredOperation = fields.operation_id; clear(); }
    const beforeDispatch = () => {
      if (!this.current(generation)) return false;
      const valid = (!fields.operation_id || fields.operation_id === this.operation()?.id) &&
        (!fields.device_id || this.state.devices.some(device => device.id === fields.device_id)) &&
        (!fields.adapter_id || (this.state.adapters || []).some(adapter => adapter.id === fields.adapter_id && adapter.selectable)) &&
        (fields.revision === undefined || fields.revision === this.state.revision) &&
        (op !== "answer" || fields.challenge_id === this.challenge?.id) &&
        (op !== "forget_confirm" || fields.confirmation_id === this.confirmation?.id) &&
        (!["test", "bind"].includes(op) ||
          (fields.observation_id === this.observation?.id && this.observation.complete &&
            (op !== "test" || !this.observation.tested))) &&
        (op !== "learn" || (remoteId === this.state.remote?.device_id &&
          this.state.remote?.connected && this.state.remote?.input_available));
      if (!valid) {
        this.message = this.text(fields.revision !== undefined ? "revision_mismatch" : "invalidated");
        return false;
      }
      if (op === "answer") this.answeredChallenge = {operation_id: fields.operation_id, id: fields.challenge_id};
      if (op === "forget_confirm") this.forgetAttempt = fields.operation_id;
      if (["cancel", "answer", "bind", "select_remote", "forget_confirm"].includes(op)) {
        clear();
        this.render();
      }
      return true;
    };
    return this.run(() => this.receive("POST", body, generation, beforeDispatch));
  }

  retry() {
    if (this.lease) return Promise.resolve();
    const generation = this.generation;
    return this.run(() => this.receive("POST", {op: "acquire"}, generation));
  }

  element(tag, text, parent, key) {
    const element = this.document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (key) element.dataset.btKey = key;
    parent.append(element);
    return element;
  }

  button(parent, key, label, enabled, handler) {
    const button = this.element("button", label, parent, key);
    button.type = "button";
    button.disabled = !enabled || this.pending || !this.active;
    const view = this.view;
    button.onclick = () => {
      if (this.view === view && this.active && this.visible() && !button.disabled) void handler();
    };
    return button;
  }

  render() {
    const focus = this.document.activeElement;
    const localFocus = this.root.contains(focus);
    const focusKey = localFocus ? focus.dataset.btKey : null;
    const selection = localFocus && focus.tagName === "INPUT" ? [focus.selectionStart, focus.selectionEnd] : null;
    // Preserve a draft only while the exact same current challenge is displayed.
    const previousInput = this.root.querySelector("input");
    const draft = this.challenge && previousInput?.dataset.challenge === this.challenge.id ? previousInput.value : "";
    this.wipeInputs();
    this.root.replaceChildren();
    ++this.view;
    this.content = this.element("section", undefined, this.root);
    this.content.className = "bluetooth-controls";
    this.element("h3", "Bluetooth", this.content);
    const status = this.element("p", this.message, this.content);
    status.className = localFocus ? "bt-feedback bt-focus-anchor" : "bt-feedback";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.tabIndex = -1;
    // Keep focus local during a pending request, without adding a navigation action.
    if (focusKey) status.dataset.btKey = focusKey;
    if (this.active) this.renderPanel(draft);
    if (localFocus && this.active && this.visible()) {
      const actions = this.actions();
      const next = actions.find(element => element.dataset.btKey === focusKey) || actions[0] || status;
      if (next) {
        next.focus();
        if (selection && next.tagName === "INPUT" && next.dataset.btKey === focusKey)
          next.setSelectionRange?.(...selection);
      }
    }
    this.options.onActionsChanged?.();
  }

  renderPanel(draft) {
    const state = this.state;
    if (!state) return;
    const operation = this.operation();
    const powered = state.available && state.adapter?.powered;
    const free = !!this.lease && powered && !operation;
    const adapters = state.adapters || [];
    if (state.adapters) {
      this.element("h4", "Адаптер Bluetooth", this.content);
      this.element("p", "Названия адаптеров могут совпадать или отсутствовать. Сверяйте окончание адреса; номера в списке могут меняться.", this.content);
      if (state.adapter_preference && !state.adapter)
        this.element("p", "Выбранный адаптер недоступен. Подключите его или выберите другой.", this.content);
      const scanning = adapters.some(adapter => adapter.discovering);
      if (scanning && !operation)
        this.element("p", "Поиск Bluetooth уже идёт. Дождитесь его завершения перед сменой адаптера.", this.content);
      const canChoose = !!this.lease && !operation && !scanning;
      this.button(this.content, "adapter:auto", "Автоматически", canChoose && !!state.adapter_preference,
        () => this.mutate("adapter_auto", {revision: state.revision}));
      for (const [index, adapter] of adapters.entries()) {
        const selected = adapter.id === state.adapter?.id;
        const button = this.button(this.content, `adapter:${adapter.id}`,
          `${index + 1}. ${adapter.name || "Без названия"} ${adapter.label} · ${adapter.powered ? "включён" : "выключен"}${adapter.selectable ? "" : " · неоднозначный адрес"}`,
          canChoose && adapter.selectable && (!selected || !state.adapter_preference),
          () => this.mutate("select_adapter", {adapter_id: adapter.id, revision: state.revision}));
        button.setAttribute("aria-pressed", String(selected));
      }
      if (state.adapter && !state.adapter.powered)
        this.button(this.content, "adapter:power", "Включить выбранный адаптер", canChoose &&
          adapters.some(adapter => adapter.id === state.adapter.id && adapter.selectable),
          () => this.mutate("power_on", {adapter_id: state.adapter.id}));
    }
    this.element("p", !state.available ? this.text(state.reason || "unavailable") : !state.adapter ?
      this.text("unavailable") : !state.adapter.powered ? this.text("adapter_off") :
      state.adapter.discovering ? "Поиск устройств идёт…" : "Адаптер Bluetooth включён.", this.content);
    if (!this.lease) {
      this.element("p", this.ownerReason ? this.text(this.ownerReason) : "Сейчас доступен только просмотр состояния.", this.content);
      this.button(this.content, "retry", "Повторить управление", true, () => this.retry());
    }
    this.button(this.content, "discover", "Найти устройства (30 с)", free, () => this.mutate("discover"));
    if (operation) {
      const kinds = {discover: "Поиск", power_on: "Включение адаптера", pair: "Сопряжение", connect: "Подключение", disconnect: "Отключение",
        select_remote: "Выбор пульта", learn: "Обучение кнопки", forget: "Удаление сопряжения"};
      const phases = {queued: "в очереди", requested: "запрошено", accepted: "запрос принят",
        waiting: "ожидаем устройство", finished: "ожидаем подтверждение состояния",
        observed: "получено состояние", confirm: "требуется подтверждение"};
      this.element("p", `${Object.hasOwn(kinds, operation.kind) ? kinds[operation.kind] : "Операция"}: ` +
        `${Object.hasOwn(phases, operation.phase) ? phases[operation.phase] : "ожидаем результат"}. ` +
        `Осталось ${Math.ceil(operation.remaining_ms / 1000)} с.`, this.content);
      if (operation.error) this.element("p", this.text(operation.error), this.content);
      this.button(this.content, "cancel", "Отменить операцию", !!this.lease,
        () => this.mutate("cancel", {operation_id: operation.id}));
    } else if (state.operation?.error) this.element("p", this.text(state.operation.error), this.content);

    const devices = this.element("div", undefined, this.content);
    devices.className = "bt-devices";
    devices.setAttribute("aria-label", "Устройства Bluetooth");
    if (!state.devices.length) this.element("p", "Устройств пока нет. Включите режим сопряжения на устройстве и начните поиск.", devices);
    for (const device of state.devices) {
      const row = this.element("div", undefined, devices);
      row.className = "bt-device";
      const button = this.button(row, `device:${device.id}`, this.deviceName(device), !operation, () => {
        this.selected = device.id;
        this.clearPrivate();
        this.render();
      });
      button.setAttribute("aria-pressed", String(this.selected === device.id));
      this.element("span", `${device.connected ? "Подключено" : "Не подключено"} · ` +
        `${device.paired ? "Сопряжено" : "Не сопряжено"}`, row);
    }
    const device = state.devices.find(item => item.id === this.selected);
    if (device) {
      this.element("h4", `Устройство: ${this.deviceName(device)}`, this.content);
      const commands = this.element("div", undefined, this.content);
      commands.className = "bt-buttons";
      for (const [op, label, allowed] of [
        ["pair", "Создать сопряжение", !device.paired],
        ["connect", "Подключить", device.paired && !device.connected],
        ["disconnect", "Отключить", device.connected],
        ["forget_prepare", "Забыть устройство…", device.paired],
      ]) this.button(commands, op, label, free && allowed, () => this.mutate(op, {device_id: device.id}));
    }
    if (this.challenge) this.renderChallenge(draft);
    if (this.confirmation) {
      const target = state.devices.find(item => item.id === operation.device_id);
      const group = this.element("section", undefined, this.content);
      group.className = "bt-confirm";
      this.element("p", `Забыть устройство «${this.deviceName(target)}»? Сопряжение и его назначения будут удалены.`, group);
      const confirmation = this.confirmation;
      this.button(group, "forget-confirm", "Да, забыть устройство", !!this.lease, () =>
        this.mutate("forget_confirm", {operation_id: confirmation.operation_id, confirmation_id: confirmation.id}));
      this.button(group, "forget-cancel", "Сохранить устройство", !!this.lease, () =>
        this.mutate("cancel", {operation_id: confirmation.operation_id}));
    }
  }

  renderChallenge(draft) {
    const challenge = this.challenge;
    const group = this.element("section", undefined, this.content);
    group.className = "bt-challenge";
    const display = ["confirmation", "display_pin", "display_passkey"].includes(challenge.kind);
    const instructions = {pin: "Введите PIN устройства.", passkey: "Введите шестизначный код устройства.",
      confirmation: "Сравните код с устройством и подтвердите совпадение.",
      display_pin: "Введите этот PIN на устройстве.", display_passkey: "Введите этот код на устройстве."};
    this.element("p", instructions[challenge.kind], group);
    if (display) {
      const value = this.element("strong", challenge.value || "—", group);
      value.dataset.secret = "true";
      value.className = "bt-passkey";
      if (challenge.kind === "display_passkey" && Number.isInteger(challenge.entered))
        this.element("p", `Введено цифр: ${Math.max(0, Math.min(6, challenge.entered))}.`, group);
    }
    let input;
    if (!display) {
      const label = this.element("label", challenge.kind === "pin" ? "PIN устройства" : "Код из 6 цифр", group);
      input = this.element("input", undefined, label, `answer:${challenge.id}`);
      input.type = "password";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.maxLength = challenge.kind === "pin" ? 16 : 6;
      input.inputMode = challenge.kind === "pin" ? "text" : "numeric";
      input.dataset.challenge = challenge.id;
      input.value = draft;
      input.disabled = this.pending;
    }
    const answer = value => {
      const fields = {operation_id: challenge.operation_id, challenge_id: challenge.id, answer: value};
      return this.mutate("answer", fields);
    };
    if (input) this.button(group, "answer-submit", "Отправить код", !!this.lease, () => {
      const value = input.value;
      if (!(challenge.kind === "pin" ? /^[\x21-\x7e]{1,16}$/ : /^[0-9]{6}$/).test(value)) {
        input.value = "";
        this.message = challenge.kind === "pin" ? "Введите PIN: от 1 до 16 символов без пробелов." : "Введите ровно 6 цифр.";
        this.render();
        return;
      }
      return answer(challenge.kind === "pin" ? {pin: value} : {passkey: value});
    });
    if (challenge.kind === "confirmation") {
      this.button(group, "answer-yes", "Код совпадает", !!this.lease, () => answer({confirm: true}));
      this.button(group, "answer-no", "Код не совпадает", !!this.lease, () => answer({confirm: false}));
    }
  }

}
