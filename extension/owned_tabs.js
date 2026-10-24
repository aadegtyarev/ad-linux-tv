"use strict";
const BASE = "http://127.0.0.1:8765";
const storageFactory = typeof module !== "undefined"
  ? require("./tab_storage.js").createTabStorage : createTabStorage;
const mediaVolume = typeof module !== "undefined"
  ? require("./player_volume.js").playerMediaVolume : playerMediaVolume;
const pinVolume = typeof module !== "undefined"
  ? require("./player_volume.js").pinMediaVolume : pinMediaVolume;
class PermanentCommandError extends Error {}
function createOwnedTabs(api, fetcher = fetch) {
  const state = storageFactory(api);
  const managed = () => state.managed();
  const findLauncher = () => state.findLauncher();
  const prepare = async item => {
    if (item.command === "open") {
      const response = await fetcher(`${BASE}/api/services`);
      if (!response.ok) throw new Error("service list unavailable");
      const services = (await response.json()).services;
      const service = services.find(value => value.id === item.service_id);
      if (!service) throw new PermanentCommandError("unknown service");
      const entry = managed()[service.id];
      const tab = entry ? await api.tabs.get(entry.tabId).catch(() => null) : null;
      return {service, tab};
    }
    if (item.command === "home") return {active: await state.activeTab()};
    if (item.command === "back" || item.command === "refresh") {
      const active = await state.activeTab();
      return {active: state.owns(active) ? active : null};
    }
    if (["player_get", "player_set", "player_pause"].includes(item.command)) {
      const active = await state.activeTab();
      if (!state.owns(active) || !/^https?:\/\//i.test(active.url || ""))
        throw new PermanentCommandError("no_media");
      return {active};
    }
    if (["up", "down", "left", "right", "ok"].includes(item.command)) {
      return {launcher: await findLauncher()};
    }
    throw new PermanentCommandError("unsupported command");
  };

  async function openService(serviceId, prepared) {
    let data = prepared?.service;
    if (!data) {
      const response = await fetcher(`${BASE}/api/services`);
      if (!response.ok) throw new Error("service list unavailable");
      data = (await response.json()).services.find(value => value.id === serviceId);
    }
    if (!data || data.id !== serviceId) throw new PermanentCommandError("unknown service");
    const entry = managed()[serviceId];
    let tab = prepared?.tab || (entry ? await api.tabs.get(entry.tabId).catch(() => null) : null);
    if (tab) {
      entry.windowId = tab.windowId;
      tab = await api.tabs.update(tab.id, {url: data.url, active: true});
    } else {
      tab = await api.tabs.create({url: data.url, active: true});
      managed()[serviceId] = {tabId: tab.id, windowId: tab.windowId};
    }
    await state.persist();
    await state.focus(tab);
  }

  async function execute(item, prepared) {
    const command = item.command;
    if (command === "open") return openService(item.service_id, prepared);
    if (command === "home") {
      if (state.owns(prepared.active)) await api.tabs.remove(prepared.active.id);
      await state.focus(await state.ensureLauncher());
      return;
    }
    if (command === "back" || command === "refresh") {
      if (!prepared.active) return;
      if (command === "refresh") return api.tabs.reload(prepared.active.id);
      try { await api.tabs.goBack(prepared.active.id); }
      catch (error) {
        if (!/cannot.*(?:back|history)|no.*(?:back|history)|(?:back|history).*(?:empty|missing|unavailable)/i.test(String(error.message))) throw error;
      }
      return;
    }
    if (["player_get", "player_set", "player_pause"].includes(command)) {
      const active = await state.activeTab();
      if (!active || active.id !== prepared.active.id || !state.owns(active) ||
          !/^https?:\/\//i.test(active.url || ""))
        throw new PermanentCommandError("no_media");
      const frames = await api.scripting.executeScript({
        target:{tabId:active.id, allFrames:true},
        func:mediaVolume,
        args:[command === "player_set" ? "set" : command === "player_pause" ? "pause" : "get",
          item.volume ?? null],
      });
      const found = frames.find(frame => Number.isInteger(frame.result) &&
        frame.result >= 0 && frame.result <= 100);
      if (!found) throw new PermanentCommandError("no_media");
      if (command === "player_pause") {
        await new Promise(resolve => setTimeout(resolve, 700));
        if ((await api.tabs.query({audible:true})).some(tab => tab.audible === true))
          throw new PermanentCommandError("audio_active");
      }
      return {volume:found.result};
    }
    const launcher = prepared.launcher || await state.ensureLauncher();
    await state.focus(launcher);
    const result = await api.tabs.sendMessage(launcher.id, {command});
    if (command === "ok" && result?.service_id) return {service_id: result.service_id};
  }

  async function normalizeMedia(tabId) {
    const active = await state.activeTab();
    if (!active || active.id !== tabId || !state.owns(active) ||
        !/^https?:\/\//i.test(active.url || "")) return;
    await api.scripting.executeScript({
      target:{tabId:active.id, allFrames:true}, func:pinVolume,
    });
  }

  return {restore:state.restore, ensureLauncher:state.ensureLauncher, prepare, execute, openService,
    onRemoved:state.onRemoved, normalizeMedia, getState:state.getState};
}

if (typeof module !== "undefined") module.exports = {createOwnedTabs, PermanentCommandError};
