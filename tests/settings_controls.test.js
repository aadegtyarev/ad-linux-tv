"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function panel() {
  const roles = ["pin-form", "pin-mode", "pin-fields", "pin", "pin-confirm", "magnifier",
    "proxy-form", "proxy-mode", "proxy-fields", "proxy-protocol", "proxy-host", "proxy-port",
    "proxy-restart", "restart", "settings-status", "pointer-acceleration",
    "pointer-acceleration-value", "magnifier-scale", "magnifier-scale-value", "magnifier-hint",
    "view-form", "view-scope", "view-inherited", "view-mode", "view-zoom", "view-zoom-value", "view-default", "view-hint",
    "about", "server-version", "server-build", "app-info", "app-version", "app-build",
    "locale-form", "browser-locale", "locale-hint"];
  const fields = Object.fromEntries(roles.map(role => [role, {value:"", hidden:false, disabled:false, dataset:{},
    textContent:"", setAttribute() {}}]));
  fields["view-scope"].options = [{value:"common", textContent:"Все сайты"}];
  fields["view-scope"].remove = index => fields["view-scope"].options.splice(index, 1);
  fields["view-scope"].append = option => fields["view-scope"].options.push(option);
  const pinExtra = {hidden:false};
  const proxyExtras = Array.from({length:3}, () => ({hidden:false}));
  const root = {
    querySelector(selector) { return fields[selector.match(/data-role="([^"]+)"/)[1]]; },
    querySelectorAll(selector) {
      if (selector === '[data-role="pin-fields"]') return [fields["pin-fields"], pinExtra];
      if (selector === '[data-role="proxy-fields"]') return [fields["proxy-fields"], ...proxyExtras];
      return Object.values(fields);
    },
  };
  const calls = [];
  const context = {window:{}, document:{createElement:() => ({value:"",textContent:""})}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/settings_controls.js", "utf8") +
    "\nglobalThis.SettingsControls = SettingsControls;", context);
  const state = {require_pin:false, magnifier:false, proxy:{mode:"system"},
    proxy_restart_required:false, pointer_acceleration:50, magnifier_scale:2.5,
    magnifier_applied_scale:2.5, restart_required:false,
    view:{mode:"desktop",zoom:125}, service_views:[
      {id:"kinopoisk",name:"Кино <b>Поиск",view:null,effective_view:{mode:"desktop",zoom:125}},
      {id:"youtube",name:"YouTube",view:{mode:"mobile",zoom:180},effective_view:{mode:"mobile",zoom:180}},
    ], view_profile_ready:true, view_bridge_ready:true, view_restart_required:false,
    browser_locale:"ru", browser_locales_installed:["ru", "en"], browser_locale_restart_required:false};
  const controls = new context.SettingsControls(root, async (method, action) => {
    calls.push({method, action});
    if (method === "POST" && action.setting === "view") {
      state.view = action.value || {mode:"desktop",zoom:125};
      state.view_restart_required = state.restart_required = false;
    }
    if (method === "POST" && action.setting === "service_view") {
      const service = state.service_views.find(item => item.id === action.value.id);
      service.view = action.value.view;
      service.effective_view = action.value.view || state.view;
    }
    if (method === "POST" && action.setting === "magnifier_scale") {
      state.magnifier_scale = action.value;
      state.restart_required = action.value !== state.magnifier_applied_scale;
    }
    if (method === "POST" && action.setting === "magnifier") state.magnifier = action.value;
    if (method === "POST" && action.setting === "browser_locale") {
      state.browser_locale = action.value;
      state.browser_locale_restart_required = state.restart_required = true;
    }
    if (method === "POST" && action.setting === "pointer_acceleration")
      state.pointer_acceleration = action.value;
    return {ok:true, json:async () => state};
  });
  return {controls, fields, calls, state, pinExtra, proxyExtras, window:context.window};
}

test("about shows actual server and native values with no additional requests or actions", async () => {
  const ui = panel();
  ui.state.server = {version:"1.2.3+local", build:"0123456789abcdef"};
  ui.window.adLinuxTvAppInfo = {version:"2.3.4", build:2147483647};
  await ui.controls.refresh();
  assert.equal(ui.fields["server-version"].textContent, "1.2.3+local");
  assert.equal(ui.fields["server-build"].textContent, "0123456789abcdef");
  assert.equal(ui.fields["app-info"].hidden, false);
  assert.equal(ui.fields["app-version"].textContent, "2.3.4");
  assert.equal(ui.fields["app-build"].textContent, "2147483647");
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.calls[0].method, "GET");
});

test("older counterparts and unknown sentinels remain honest", async () => {
  const ui = panel();
  await ui.controls.refresh();
  assert.equal(ui.fields["app-info"].hidden, true);
  for (const role of ["server-version", "server-build", "app-version", "app-build"])
    assert.equal(ui.fields[role].textContent, "неизвестно");
  ui.state.server = {version:"unknown", build:"unknown"};
  ui.window.adLinuxTvAppInfo = {version:"unknown", build:0};
  await ui.controls.refresh();
  assert.equal(ui.fields["app-info"].hidden, false);
  for (const role of ["server-version", "server-build", "app-version", "app-build"])
    assert.equal(ui.fields[role].textContent, "неизвестно");
  // Each field fails independently; a missing distribution version need not hide a build.
  ui.state.server.build = "abcdef0123456789";
  ui.window.adLinuxTvAppInfo.build = 1;
  ui.controls.render(ui.state);
  assert.equal(ui.fields["server-build"].textContent, "abcdef0123456789");
  assert.equal(ui.fields["app-build"].textContent, "1");
});

test("late native constant is read on ordinary settings sync and local About opening", async () => {
  const ui = panel();
  await ui.controls.refresh();
  ui.window.adLinuxTvAppInfo = {version:"late", build:6};
  ui.fields.about.open = true;
  ui.fields.about.ontoggle();
  assert.equal(ui.fields["app-version"].textContent, "late");
  assert.equal(ui.calls.length, 1);
  delete ui.window.adLinuxTvAppInfo;
  await ui.controls.refresh();
  assert.equal(ui.fields["app-info"].hidden, true);
  ui.window.adLinuxTvAppInfo = {version:"synced", build:7};
  await ui.controls.refresh();
  assert.equal(ui.fields["app-version"].textContent, "synced");
  assert.equal(ui.calls.length, 3);
  assert.ok(ui.calls.every(call => call.method === "GET" && call.action === null));
});

test("about bounds metadata and treats hostile strings as text, never markup", () => {
  const ui = panel();
  for (const field of Object.values(ui.fields)) Object.defineProperty(field, "innerHTML", {
    set() { assert.fail("metadata must not use innerHTML"); },
  });
  const invalidVersions = [null, 42, {}, "", " ", "x".repeat(81), "a\n", "a\u007f", "a\u0085", "a\ud800", "a\udfff", "😀"];
  for (const version of invalidVersions) {
    ui.window.adLinuxTvAppInfo = {version, build:1};
    ui.controls.render(ui.state);
    assert.equal(ui.fields["app-version"].textContent, "неизвестно", JSON.stringify(version));
  }
  for (const build of [undefined, null, "6", 0, -1, 1.5, 2147483648, NaN, Infinity, {}]) {
    ui.window.adLinuxTvAppInfo = {version:"valid", build};
    ui.controls.render(ui.state);
    assert.equal(ui.fields["app-build"].textContent, "неизвестно");
  }
  const hostile = '</span><script>alert("x")</script>';
  ui.window.adLinuxTvAppInfo = {version:hostile, build:6};
  ui.state.server = {version:hostile, build:hostile};
  ui.controls.render(ui.state);
  assert.equal(ui.fields["app-version"].textContent, hostile);
  assert.equal(ui.fields["server-version"].textContent, "неизвестно");
  assert.equal(ui.fields["server-build"].textContent, "неизвестно");
  for (const version of ["x".repeat(81), "1.2\n", "версия", 123, {}, ""]) {
    ui.state.server.version = version;
    ui.controls.render(ui.state);
    assert.equal(ui.fields["server-version"].textContent, "неизвестно");
  }
  for (const build of ["0123456789abcde", "0123456789abcdef0", "ABCDEF0123456789", 123, {}, null]) {
    ui.state.server.build = build;
    ui.controls.render(ui.state);
    assert.equal(ui.fields["server-build"].textContent, "неизвестно");
  }
  ui.window.adLinuxTvAppInfo.version = "я".repeat(80);
  ui.controls.render(ui.state);
  assert.equal(ui.fields["app-version"].textContent.length, 80);
  assert.equal(ui.calls.length, 0);
});

test("settings form keeps hidden fields out of default view and sends confirmed PIN", async () => {
  const ui = panel();
  await ui.controls.refresh();
  assert.equal(ui.fields["pin-fields"].hidden, true);
  assert.equal(ui.fields["proxy-fields"].hidden, true);
  ui.fields["pin-mode"].value = "on";
  ui.fields["pin-mode"].onchange();
  assert.equal(ui.pinExtra.hidden, false);
  ui.fields.pin.value = "1234";
  ui.fields["pin-confirm"].value = "4321";
  await ui.controls.savePin();
  assert.equal(ui.calls.length, 1);
  ui.fields["pin-confirm"].value = "1234";
  await ui.controls.savePin();
  assert.equal(ui.calls[1].action.setting, "pin");
  assert.equal(ui.calls[1].action.value.pin, "1234");
  assert.equal(ui.fields.pin.value, "");
});

test("browser language saves explicitly and asks for a TV-session restart", async () => {
  const ui = panel();
  await ui.controls.refresh();
  assert.equal(ui.fields["browser-locale"].value, "ru");
  assert.equal(ui.fields["locale-hint"].textContent, "");
  ui.fields["browser-locale"].value = "en";
  ui.fields["locale-form"].onsubmit({preventDefault() {}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(JSON.stringify(ui.calls.at(-1).action), JSON.stringify({setting:"browser_locale", value:"en"}));
  assert.equal(ui.fields["proxy-restart"].hidden, false);
  assert.match(ui.fields["locale-hint"].textContent, /перезапуска/);
  ui.state.browser_locale = "ru";
  ui.state.browser_locale_restart_required = false;
  ui.state.browser_locales_installed = ["en"];
  await ui.controls.refresh();
  assert.match(ui.fields["locale-hint"].textContent, /не установлен/);
});

test("common site view is explicit save/reset with desktop125 default", async () => {
  const ui=panel();await ui.controls.refresh();
  assert.equal(ui.fields["view-mode"].value,"desktop");
  assert.equal(ui.fields["view-zoom"].value,125);
  assert.match(ui.fields["view-hint"].textContent,/следующем открытии плитки/);
  ui.fields["view-mode"].value="desktop";ui.fields["view-mode"].onchange();
  ui.fields["view-zoom"].value="175";ui.fields["view-zoom"].oninput();
  assert.equal(ui.calls.length,1);
  assert.match(ui.fields["view-hint"].textContent,/не сохранены/);
  ui.fields["view-form"].onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ui.calls.at(-1).action.setting,"view");
  assert.equal(ui.calls.at(-1).action.value.mode,"desktop");
  assert.equal(ui.calls.at(-1).action.value.zoom,175);
  assert.equal(ui.fields["proxy-restart"].hidden,true);
  ui.fields["view-default"].onclick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ui.calls.at(-1).action.value,null);
  assert.equal(ui.fields["view-mode"].value,"desktop");
  assert.ok(ui.calls.every(c=>c.action?.setting!=="restart"));
});

test("individual view inherits, saves only its override, and reset restores inheritance", async () => {
  const ui=panel(); await ui.controls.refresh();
  const scope=ui.fields["view-scope"];
  assert.deepEqual(scope.options.map(option=>option.value),["common","kinopoisk","youtube"]);
  assert.equal(scope.options[1].textContent,"Кино <b>Поиск");
  scope.value="kinopoisk"; scope.onchange();
  assert.equal(ui.fields["view-inherited"].textContent,"Используются общие настройки");
  assert.equal(ui.fields["view-mode"].value,"desktop");
  scope.value="youtube"; scope.onchange();
  assert.equal(ui.fields["view-inherited"].hidden,true);
  assert.equal(ui.fields["view-mode"].value,"mobile");
  ui.fields["view-zoom"].value="190"; ui.fields["view-zoom"].oninput();
  assert.equal(ui.calls.length,1);
  ui.fields["view-form"].onsubmit({preventDefault(){}}); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(JSON.stringify(ui.calls.at(-1).action),JSON.stringify({setting:"service_view",value:{id:"youtube",view:{mode:"mobile",zoom:190}}}));
  ui.fields["view-default"].onclick(); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(JSON.stringify(ui.calls.at(-1).action),JSON.stringify({setting:"service_view",value:{id:"youtube",view:null}}));
  assert.equal(ui.fields["view-inherited"].hidden,false);
});

test("scope changes do not submit and stale save replies cannot alter the new scope", async () => {
  const ui=panel(); await ui.controls.refresh();
  let finish;
  ui.controls.request=async (method, action) => {
    if (method === "POST") return new Promise(resolve => { finish=resolve; });
    return {ok:true,json:async()=>ui.state};
  };
  ui.fields["view-zoom"].value="140"; ui.fields["view-zoom"].oninput();
  ui.fields["view-form"].onsubmit({preventDefault(){}});
  ui.fields["view-scope"].value="youtube"; ui.fields["view-scope"].onchange();
  assert.equal(ui.fields["view-zoom"].value,180);
  assert.equal(ui.controls.viewDirty,false);
  finish({ok:true,json:async()=>({...ui.state,view:{mode:"mobile",zoom:140}})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ui.fields["view-scope"].value,"youtube");
  assert.equal(ui.fields["view-zoom"].value,180);
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
const clone = value => JSON.parse(JSON.stringify(value));
const reply = state => ({ok:true, json:async () => clone(state)});
const tick = () => new Promise(resolve => setImmediate(resolve));
function editZoom(ui, zoom) {
  ui.fields["view-zoom"].value = String(zoom);
  ui.fields["view-zoom"].oninput();
}
function selectScope(ui, scope) {
  ui.fields["view-scope"].value = scope;
  ui.fields["view-scope"].onchange();
}

for (const operation of ["saveView", "resetView"]) {
  test(`${operation}: delayed JSON ACK preserves mode-only edit on an individual site`, async () => {
    const ui = panel(); await ui.controls.refresh(); selectScope(ui, "kinopoisk");
    const body = deferred(); let posts = 0;
    const saved = clone(ui.state);
    saved.service_views[0].view = operation === "saveView" ? {mode:"desktop",zoom:150} : null;
    saved.service_views[0].effective_view = saved.service_views[0].view || saved.view;
    ui.controls.request = async (method, action) => {
      if (method === "GET") return reply(ui.state);
      posts++;
      assert.equal(action.setting, "service_view");
      assert.equal(action.value.id, "kinopoisk");
      assert.equal(action.value.view === null, operation === "resetView");
      return {ok:true,json:() => body.promise};
    };
    editZoom(ui, 150);
    const writing = ui.controls[operation](); await tick();
    ui.fields["view-mode"].value = "mobile"; ui.fields["view-mode"].onchange();
    // Repeated UI actions while a write is uncertain are not queued.
    const duplicateSave = ui.controls.saveView(), duplicateReset = ui.controls.resetView();
    body.resolve(saved); await Promise.all([writing, duplicateSave, duplicateReset]);
    assert.equal(posts, 1);
    assert.equal(ui.fields["view-mode"].value, "mobile");
    assert.equal(Number(ui.fields["view-zoom"].value), 150);
    assert.equal(ui.controls.viewDirty, true);
    assert.equal(ui.controls.state.service_views[0].effective_view.zoom, operation === "saveView" ? 150 : 125);
    await ui.controls.refresh();
    assert.equal(posts, 1);
    assert.equal(ui.fields["view-mode"].value, "mobile");
  });

  for (const timing of ["before", "during"]) test(`${operation}: GET started ${timing} write cannot restore stale cache or fields`, async () => {
    const ui = panel(); await ui.controls.refresh();
    const old = clone(ui.state), read = deferred(), write = deferred();
    const saved = {...old, view:{mode:"desktop",zoom:operation === "saveView" ? 170 : 125}};
    old.view.zoom = 110;
    ui.controls.request = method => method === "POST" ? write.promise : read.promise;
    let reading;
    if (timing === "before") reading = ui.controls.refresh();
    editZoom(ui, 170);
    const writing = ui.controls[operation]();
    assert.equal(ui.controls.viewDirty, true);
    if (timing === "during") reading = ui.controls.refresh();
    write.resolve(reply(saved)); await writing;
    read.resolve(reply(old)); await reading;
    assert.equal(Number(ui.fields["view-zoom"].value), saved.view.zoom);
    assert.equal(ui.controls.state.view.zoom, saved.view.zoom);
    assert.equal(ui.controls.viewDirty, false);
    assert.match(ui.fields["settings-status"].textContent, operation === "saveView" ? /Вид сохранён/ : /восстановлен/);
    // Exclusion ends with the write; a genuinely fresh read still works.
    ui.controls.request = async () => reply({...saved,view:{mode:"mobile",zoom:210}});
    await ui.controls.refresh();
    assert.equal(Number(ui.fields["view-zoom"].value), 210);
  });

  test(`${operation}: pending write and late ACK preserve newer zoom and mode edits`, async () => {
    const ui = panel(); await ui.controls.refresh();
    const write = deferred();
    ui.controls.request = method => method === "POST" ? write.promise : Promise.resolve(reply(ui.state));
    editZoom(ui, 160);
    const writing = ui.controls[operation]();
    await ui.controls.refresh();
    assert.equal(Number(ui.fields["view-zoom"].value), 160);
    assert.equal(ui.controls.viewDirty, true);
    editZoom(ui, 190);
    ui.fields["view-mode"].value = "mobile"; ui.fields["view-mode"].onchange();
    write.resolve(reply({...ui.state,view:{mode:"desktop",zoom:operation === "saveView" ? 160 : 125}}));
    await writing;
    assert.equal(Number(ui.fields["view-zoom"].value), 190);
    assert.equal(ui.fields["view-mode"].value, "mobile");
    assert.equal(ui.controls.viewDirty, true);
    assert.match(ui.fields["view-hint"].textContent, /не сохранены/);
    assert.match(ui.fields["settings-status"].textContent, /не сохранены/);
    await ui.controls.refresh();
    assert.equal(Number(ui.fields["view-zoom"].value), 190);
  });

  for (const failure of ["transport", "json", "http"]) {
    test(`${operation}: ${failure} rejection in void handler keeps draft, reports failure, never replays`, async () => {
      const ui = panel(); await ui.controls.refresh();
      const write = deferred(); let posts = 0;
      ui.controls.request = method => {
        if (method === "POST") { posts++; return write.promise; }
        return Promise.resolve(reply(ui.state));
      };
      editZoom(ui, 165);
      if (operation === "saveView") ui.fields["view-form"].onsubmit({preventDefault(){}});
      else ui.fields["view-default"].onclick();
      editZoom(ui, 195);
      if (failure === "transport") write.reject(new Error("offline"));
      else write.resolve(failure === "http" ? {ok:false} : {ok:true,json:async () => { throw new Error("bad json"); }});
      await tick(); // node:test also fails this test on any unhandled rejection.
      assert.equal(ui.fields["settings-status"].dataset.error, "true");
      assert.match(ui.fields["settings-status"].textContent, /Не удалось/);
      assert.equal(ui.controls.viewDirty, true);
      assert.equal(Number(ui.fields["view-zoom"].value), 195);
      await ui.controls.refresh(); await tick();
      assert.equal(posts, 1);
      assert.equal(Number(ui.fields["view-zoom"].value), 195);
      // Retry is only an explicit user action, with the current draft.
      ui.controls.request = async (method, action) => {
        if (method === "POST") { posts++; assert.equal(action.value.zoom, 195); }
        return reply({...ui.state,view:{mode:"desktop",zoom:195}});
      };
      await ui.controls.saveView();
      assert.equal(posts, 2);
      assert.equal(ui.controls.viewDirty, false);
    });
  }

  for (const failed of [false, true]) for (const returnToScope of [false, true]) {
    test(`${operation}: late ${failed ? "failure" : "success"} cannot affect ${returnToScope ? "a returned" : "another"} scope`, async () => {
      const ui = panel(); await ui.controls.refresh();
      const write = deferred(); ui.controls.request = () => write.promise;
      editZoom(ui, 155); const writing = ui.controls[operation]();
      selectScope(ui, "youtube"); editZoom(ui, 205);
      if (returnToScope) selectScope(ui, "common");
      editZoom(ui, 215);
      ui.controls.notice("Новая область");
      if (failed) write.reject(new Error("offline"));
      else write.resolve(reply({...clone(ui.state),view:{mode:"mobile",zoom:155},
        view_profile_ready:false,view_restart_required:true,restart_required:true,pointer_acceleration:12}));
      await writing;
      assert.equal(ui.controls.state.view_restart_required, false);
      assert.equal(ui.fields["proxy-restart"].hidden, true);
      assert.equal(ui.controls.state.pointer_acceleration, 50);
      assert.equal(Number(ui.fields["view-zoom"].value), 215);
      assert.equal(ui.controls.viewDirty, true);
      assert.equal(ui.controls.state.view.zoom, 125);
      assert.equal(ui.fields["settings-status"].textContent, "Новая область");
    });
  }
}

// Full independent snapshots model backend fingerprint readiness, not the simple
// panel's shared-object shortcut. Assert before any later GET/POST can mask ACK UI.
for (const scope of ["common", "kinopoisk"]) for (const operation of ["saveView", "resetView"]) {
  for (const readiness of ["required", "cleared", "proxy", "magnifier", "unready"]) {
    test(`${scope} ${operation}: matching ACK immediately renders ${readiness} readiness`, async () => {
      const ui = panel();
      const initial = clone(ui.state);
      initial.view = {mode:"desktop",zoom:170};
      initial.service_views[0].view = {mode:"mobile",zoom:190};
      initial.service_views[0].effective_view = clone(initial.service_views[0].view);
      initial.view_restart_required = initial.restart_required = readiness === "cleared";
      initial.view_profile_ready = readiness !== "cleared";
      initial.proxy_restart_required = readiness === "proxy";
      if (readiness === "magnifier") initial.magnifier_scale = 3.5;
      initial.restart_required ||= initial.proxy_restart_required || readiness === "magnifier";
      ui.controls.request = async () => reply(initial);
      await ui.controls.refresh(); selectScope(ui, scope);
      assert.equal(ui.fields["proxy-restart"].hidden, !initial.restart_required);
      const saved = clone(initial);
      const view = operation === "resetView" ? null : {mode:"desktop",zoom:210};
      if (scope === "common") {
        saved.view = view || {mode:"desktop",zoom:125};
      } else {
        saved.service_views[0].view = view;
        saved.service_views[0].effective_view = clone(view || saved.view);
      }
      saved.view_restart_required = readiness === "required";
      saved.view_profile_ready = !["required", "unready"].includes(readiness);
      saved.view_bridge_ready = readiness !== "unready";
      saved.restart_required = saved.view_restart_required || saved.proxy_restart_required || readiness === "magnifier";
      const calls = [];
      ui.controls.request = async (method, action) => {
        calls.push({method,action:clone(action)}); return reply(saved);
      };
      ui.fields["view-mode"].value = "desktop"; ui.fields["view-mode"].onchange();
      editZoom(ui, 210); await ui.controls[operation]();
      assert.equal(ui.fields["proxy-restart"].hidden, !saved.restart_required);
      assert.equal(ui.controls.state.view_restart_required, saved.view_restart_required);
      const hint = ui.fields["view-hint"].textContent;
      const status = ui.fields["settings-status"].textContent;
      if (readiness === "required") {
        assert.match(hint, /Перезапустите ТВ-режим/);
        assert.match(status, /Перезапустите ТВ-режим/);
        assert.doesNotMatch(hint + status, /если это действительно требуется|Применится при следующем/);
      } else if (readiness === "unready") {
        assert.match(hint + status, /не готов/);
        assert.doesNotMatch(hint + status, /Применится при следующем/);
      } else {
        assert.match(hint, /Применится при следующем открытии плитки/);
        assert.match(status, /Применится при следующем открытии плитки/);
      }
      assert.equal(ui.controls.viewDirty, false);
      assert.equal(calls.length, 1); // no automatic restart/navigation/read/replay
      assert.equal(calls[0].method, "POST");
      assert.equal(calls[0].action.setting, scope === "common" ? "view" : "service_view");
      assert.equal(calls[0].action.value === null || calls[0].action.value.view === null, operation === "resetView");
    });
  }
}

test("late matching view ACK retains newer non-view state and dirty draft while exposing restart", async () => {
  const ui = panel(); await ui.controls.refresh();
  const old = clone(ui.controls.state), write = deferred();
  ui.controls.request = async (method, action) => action.setting === "view" ? write.promise
    : reply({...old, pointer_acceleration:83, proxy_restart_required:true, restart_required:true});
  editZoom(ui, 170); const writing = ui.controls.saveView();
  editZoom(ui, 220);
  await ui.controls.change("pointer_acceleration", 83);
  const saved = clone(old);
  saved.view = {mode:"desktop",zoom:170};
  saved.view_profile_ready = false; saved.view_restart_required = saved.restart_required = true;
  write.resolve(reply(saved)); await writing;
  assert.equal(ui.controls.state.pointer_acceleration, 83);
  assert.equal(ui.controls.state.proxy_restart_required, true);
  assert.equal(ui.fields["pointer-acceleration"].value, 83);
  assert.equal(Number(ui.fields["view-zoom"].value), 220);
  assert.equal(ui.controls.viewDirty, true);
  assert.match(ui.fields["settings-status"].textContent, /не сохранены/);
  assert.match(ui.fields["settings-status"].textContent, /Перезапустите/);
  assert.equal(ui.fields["proxy-restart"].hidden, false);
});

test("legacy settings state without service_views keeps only common view", async () => {
  const ui=panel(); ui.state.service_views=undefined; await ui.controls.refresh();
  assert.equal(ui.fields["view-scope"].disabled,true);
  assert.equal(ui.fields["view-scope"].value,"common");
  ui.fields["view-scope"].value="common"; ui.fields["view-scope"].onchange();
  ui.fields["view-zoom"].value="160"; ui.fields["view-zoom"].oninput();
  ui.fields["view-form"].onsubmit({preventDefault(){}}); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ui.calls.at(-1).action.setting,"view");
});

test("cursor acceleration is shared through settings", async () => {
  const ui = panel();
  await ui.controls.refresh();
  assert.equal(ui.fields["pointer-acceleration"].value, 50);
  ui.fields["pointer-acceleration"].value = "80";
  ui.fields["pointer-acceleration"].oninput();
  assert.equal(ui.fields["pointer-acceleration-value"].textContent, "80%");
  ui.fields["pointer-acceleration"].onchange();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls.at(-1).action.setting, "pointer_acceleration");
  assert.equal(ui.calls.at(-1).action.value, 80);
});

test("magnifier scale saves on release, keeps applied label honest and offers explicit restart", async () => {
  const ui = panel();
  await ui.controls.refresh();
  ui.fields["magnifier-scale"].value = "3.5";
  ui.fields["magnifier-scale"].oninput();
  assert.equal(ui.calls.length,1);
  assert.equal(ui.fields["magnifier-scale-value"].textContent,"3,5×");
  ui.fields["magnifier-scale"].onchange();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls.at(-1).action.setting,"magnifier_scale");
  assert.equal(ui.calls.at(-1).action.value,3.5);
  assert.equal(ui.fields["magnifier"].textContent,"Включить ×2,5");
  assert.equal(ui.fields["proxy-restart"].hidden,false);
  assert.match(ui.fields["magnifier-hint"].textContent,/после перезапуска/);
  assert.ok(ui.calls.every(call => call.action?.setting !== "restart"));
});

test("proxy form sends custom endpoint and magnifier toggles", async () => {
  const ui = panel();
  await ui.controls.refresh();
  ui.fields["proxy-mode"].value = "custom";
  ui.fields["proxy-mode"].onchange();
  assert.ok(ui.proxyExtras.every(field => field.hidden === false));
  ui.fields["proxy-protocol"].value = "socks5";
  ui.fields["proxy-host"].value = " proxy.example ";
  ui.fields["proxy-port"].value = "1080";
  await ui.controls.saveProxy();
  assert.equal(ui.calls.at(-1).action.value.host, "proxy.example");
  assert.equal(ui.calls.at(-1).action.value.port, 1080);
  const icon = {textContent:""};
  const shortcut = {setAttribute(name, value) { this[name] = value; },
    querySelector() { return icon; }};
  ui.controls.bindMagnifierShortcut(shortcut);
  await shortcut.onclick();
  assert.equal(ui.calls.at(-1).action.value, true);
  assert.equal(shortcut["aria-pressed"], "true");
  assert.equal(icon.textContent, "⊖");
});

test("matching view ACK also refreshes read-only About metadata and a late native constant", async () => {
  const ui = panel(); await ui.controls.refresh();
  ui.controls.request = async () => reply({...clone(ui.state),
    view:{mode:"desktop",zoom:170},server:{version:"0.1.1",build:"1234567890abcdef"}});
  ui.window.adLinuxTvAppInfo = {version:"0.2.5",build:6};
  editZoom(ui,170); await ui.controls.saveView();
  assert.equal(ui.fields["server-version"].textContent,"0.1.1");
  assert.equal(ui.fields["server-build"].textContent,"1234567890abcdef");
  assert.equal(ui.fields["app-version"].textContent,"0.2.5");
  assert.equal(ui.fields["app-build"].textContent,"6");
});

function viewSlice(state) {
  return clone(Object.fromEntries(Object.entries(state).filter(([key]) =>
    key === "view" || key === "service_views" || key === "effective_service_views" || key.startsWith("view_"))));
}

for (const scope of ["common", "kinopoisk"]) {
  for (const operation of ["saveView", "resetView"]) {
    for (const delivery of ["response", "json"]) {
      test(`late pointer ${delivery} after ${scope} ${operation} preserves the whole ACKed view slice`, async () => {
        const ui = panel();
        if (operation === "resetView") {
          if (scope === "common") {
            ui.state.view = {mode:"mobile",zoom:200};
            ui.state.service_views[0].effective_view = {mode:"mobile",zoom:200};
          } else {
            ui.state.service_views[0].view = {mode:"mobile",zoom:200};
            ui.state.service_views[0].effective_view = {mode:"mobile",zoom:200};
          }
        }
        await ui.controls.refresh(); selectScope(ui, scope);
        const old = clone(ui.state), latest = clone(old), late = deferred();
        const value = operation === "resetView" ? null : {mode:"desktop",zoom:170};
        latest.pointer_acceleration = 80;
        if (scope === "common") {
          latest.view = value || {mode:"desktop",zoom:125};
          latest.service_views[0].effective_view = clone(latest.view);
        } else {
          latest.service_views[0].view = value;
          latest.service_views[0].effective_view = value || clone(latest.view);
        }
        latest.view_exceptions_count = latest.service_views.filter(item => item.view).length;
        latest.effective_service_views = latest.service_views.map(item => clone(item.effective_view));
        latest.view_profile_ready = false;
        latest.view_bridge_ready = false;
        latest.view_restart_required = true;
        latest.restart_required = true;
        ui.controls.request = async (method, action) => action.setting === "pointer_acceleration"
          ? delivery === "response" ? late.promise : {ok:true,json:() => late.promise}
          : reply(latest);
        const other = ui.controls.change("pointer_acceleration",80); await tick();
        editZoom(ui,170); await ui.controls[operation]();
        const expected = viewSlice(ui.controls.state);
        assert.deepEqual(expected,viewSlice(latest));
        assert.equal(ui.controls.viewDirty,false);
        const stale = {...old,pointer_acceleration:80};
        late.resolve(delivery === "response" ? reply(stale) : clone(stale)); await other;
        assert.deepEqual(viewSlice(ui.controls.state),expected);
        assert.equal(ui.controls.state.pointer_acceleration,80);
        assert.equal(Number(ui.fields["pointer-acceleration"].value),80);
        assert.equal(ui.fields["settings-status"].textContent,"Сохранено.");
        assert.equal(ui.fields["proxy-restart"].hidden,false);
        assert.match(ui.fields["view-hint"].textContent,/Перезапустите/);
        selectScope(ui,scope === "common" ? "kinopoisk" : "common");
        selectScope(ui,scope);
        assert.equal(Number(ui.fields["view-zoom"].value),value?.zoom || 125);
      });
    }
  }
}

for (const phase of ["draft", "pending", "failed", "scope", "scope-return"]) {
  test(`unrelated successful POST during ${phase} cannot replace view cache or draft`, async () => {
    const ui = panel(); await ui.controls.refresh();
    const old = clone(ui.state), late = deferred(), writing = deferred();
    let pins = 0;
    ui.controls.onPinChange = () => pins++;
    ui.controls.request = async (method, action) => action.setting === "pin" ? late.promise : writing.promise;
    const other = ui.controls.change("pin",{enabled:false,pin:null,confirm:null});
    editZoom(ui,190);
    let saving;
    if (phase === "pending" || phase === "failed") saving = ui.controls.saveView();
    if (phase === "failed") { writing.reject(new Error("offline")); await saving; }
    if (phase.startsWith("scope")) {
      selectScope(ui,"youtube");
      if (phase === "scope-return") selectScope(ui,"common");
    }
    const expected = viewSlice(ui.controls.state), zoom = ui.fields["view-zoom"].value;
    const stale = clone(old);
    stale.view = {mode:"mobile",zoom:75};
    stale.service_views[1].view = stale.service_views[1].effective_view = {mode:"desktop",zoom:90};
    stale.view_bridge_ready = false;
    late.resolve(reply(stale)); await other;
    assert.deepEqual(viewSlice(ui.controls.state),expected);
    assert.equal(ui.fields["view-zoom"].value,zoom);
    assert.equal(ui.fields["settings-status"].textContent,"Сохранено.");
    assert.equal(pins,1,"unrelated PIN ACK callback must still run");
    if (!phase.startsWith("scope")) {
      assert.equal(ui.controls.viewDirty,true);
      assert.match(ui.fields["view-hint"].textContent,/не сохранены/);
    }
    if (phase === "pending") { writing.resolve(reply({...old,view:{mode:"desktop",zoom:190}})); await saving; }
  });
}

test("unrelated POST begun during a view write stays fenced after that write ACKs", async () => {
  const ui = panel(); await ui.controls.refresh();
  const old = clone(ui.state), write = deferred(), late = deferred();
  ui.controls.request = async (method, action) => action.setting === "view" ? write.promise : late.promise;
  editZoom(ui,170); const saving = ui.controls.saveView();
  const other = ui.controls.change("pointer_acceleration",80);
  write.resolve(reply({...old,view:{mode:"desktop",zoom:170}})); await saving;
  late.resolve(reply({...old,pointer_acceleration:80})); await other;
  assert.equal(ui.controls.state.view.zoom,170);
  assert.equal(ui.controls.state.pointer_acceleration,80);
  assert.equal(ui.controls.viewDirty,false);
});

for (const phase of ["draft", "scope", "scope-return"]) {
  test(`GET view slice cannot replace cache after a newer ${phase} lifecycle`, async () => {
    const ui = panel(); await ui.controls.refresh();
    const expected = viewSlice(ui.controls.state), body = deferred();
    const stale = clone(ui.state); stale.view.zoom = 75;
    stale.service_views[1].view.zoom = stale.service_views[1].effective_view.zoom = 85;
    ui.controls.request = async () => ({ok:true,json:() => body.promise});
    const reading = ui.controls.refresh(); await tick();
    if (phase === "draft") editZoom(ui,190);
    else { selectScope(ui,"youtube"); if (phase === "scope-return") selectScope(ui,"common"); }
    const zoom = ui.fields["view-zoom"].value;
    body.resolve(stale); await reading;
    assert.deepEqual(viewSlice(ui.controls.state),expected);
    assert.equal(ui.fields["view-zoom"].value,zoom);
  });
}

test("an earlier unrelated POST cannot supersede a newer accepted GET view snapshot", async () => {
  const ui = panel(); await ui.controls.refresh();
  const old = clone(ui.state), late = deferred();
  const latest = {...clone(old),view:{mode:"desktop",zoom:175}};
  ui.controls.request = async method => method === "POST" ? late.promise : reply(latest);
  const other = ui.controls.change("pointer_acceleration",80);
  await ui.controls.refresh();
  late.resolve(reply({...old,pointer_acceleration:80})); await other;
  assert.equal(ui.controls.state.view.zoom,175);
  assert.equal(Number(ui.fields["view-zoom"].value),175);
  assert.equal(ui.controls.state.pointer_acceleration,80);
});

test("out-of-order GET bodies cannot restore older cache; a fresh GET can update it", async () => {
  const ui = panel(); await ui.controls.refresh();
  const old = clone(ui.state), late = deferred(); let gets = 0;
  const latest = {...clone(old),view:{mode:"desktop",zoom:185}};
  ui.controls.request = async () => ++gets === 1 ? {ok:true,json:() => late.promise} : reply(latest);
  const reading = ui.controls.refresh(); await tick();
  await ui.controls.refresh(); late.resolve(old); await reading;
  assert.equal(ui.controls.state.view.zoom,185);
  ui.controls.request = async () => reply({...latest,view:{mode:"desktop",zoom:195}});
  await ui.controls.refresh(); assert.equal(ui.controls.state.view.zoom,195);
});

for (const failure of ["auth", "json", "transport"]) {
  test(`late unrelated ${failure} failure remains visible without damaging a newer ACK`, async () => {
    const ui = panel(); await ui.controls.refresh();
    const old = clone(ui.state), late = deferred();
    ui.controls.request = async (method, action) => action.setting === "pointer_acceleration"
      ? late.promise : reply({...old,view:{mode:"desktop",zoom:170}});
    const other = ui.controls.change("pointer_acceleration",80);
    editZoom(ui,170); await ui.controls.saveView();
    if (failure === "auth") late.resolve({ok:false,status:403,json:async () => { throw Error("must not parse"); }});
    else if (failure === "json") late.resolve({ok:true,json:async () => { throw Error("invalid JSON"); }});
    else late.reject(new Error("offline"));
    await other;
    assert.equal(ui.controls.state.view.zoom,170);
    assert.equal(Number(ui.fields["view-zoom"].value),170);
    assert.equal(ui.fields["settings-status"].dataset.error,"true");
    assert.match(ui.fields["settings-status"].textContent,/Не удалось сохранить/);
    assert.equal(ui.controls.viewDirty,false);
  });
}
