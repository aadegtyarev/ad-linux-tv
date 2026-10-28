"use strict";
const BASE = "http://127.0.0.1:8765";
const storageFactory = typeof module !== "undefined"
  ? require("./tab_storage.js").createTabStorage : createTabStorage;
const mediaVolume = typeof module !== "undefined"
  ? require("./player_volume.js").playerMediaVolume : playerMediaVolume;
const pinVolume = typeof module !== "undefined"
  ? require("./player_volume.js").pinMediaVolume : pinMediaVolume;
const timingMedia = typeof module !== "undefined"
  ? require("./player_media.js").playerMedia : playerMedia;
const viewFactory = typeof module !== "undefined"
  ? require("./view_policy.js").createViewPolicy : createViewPolicy;
const mediaPulse = typeof module !== "undefined"
  ? require("./player_media.js").pulseOwnedMedia : pulseOwnedMedia;
class PermanentCommandError extends Error {}
function createOwnedTabs(api, fetcher = fetch) {
  const state = storageFactory(api);
  const viewPolicy = viewFactory(api, tab => state.owns(tab));
  let viewsRestored = null;
  let viewReady = true;
  async function restore() {
    await state.restore();
    if (!viewsRestored) viewsRestored = (async () => {
      for (const entry of Object.values(state.managed())) {
        if (entry.view !== undefined) {
          const tab = await api.tabs.get(entry.tabId).catch(() => null);
          if (tab && state.owns(tab)) {
            try { await viewPolicy.bind(tab, entry.view); }
            catch (_) { viewReady = false; } // Optional policy cannot disable Home/legacy controls.
          }
        }
      }
    })().catch(error => { viewsRestored = null; throw error; });
    await viewsRestored;
  }
  const managed = () => state.managed();
  let lastMedia = null;
  let snapshotRead = 0;
  const findLauncher = () => state.findLauncher();
  const prepare = async item => {
    if (item.command === "open") {
      const response = await fetcher(`${BASE}/api/services`);
      if (!response.ok) throw new Error("service list unavailable");
      const services = (await response.json()).services;
      const service = services.find(value => value.id === item.service_id);
      if (!service) throw new PermanentCommandError("unknown service");
      try { await viewPolicy.prepare(service.view); }
      catch (_) { throw new PermanentCommandError("invalid view"); }
      const entry = managed()[service.id];
      const tab = entry ? await api.tabs.get(entry.tabId).catch(() => null) : null;
      return {service, tab};
    }
    if (item.command === "home") return {};
    if (item.command === "back" || item.command === "refresh") {
      const active = await state.activeTab();
      return {active: state.owns(active) ? active : null};
    }
    if (item.command === "media") {
      const active = await state.activeTab();
      if (!state.owns(active) || !/^https?:\/\//i.test(active?.url || "") ||
          !lastMedia || lastMedia.tabId !== active.id || lastMedia.url !== active.url ||
          item.media_id !== lastMedia.media_id || !["play", "pause", "seek"].includes(item.action) ||
          !Number.isSafeInteger(item.deadline) || Date.now() > item.deadline ||
          (item.action === "seek" ? !Number.isInteger(item.position) || item.position < 0 || item.position > 86400 : item.position !== null))
        throw new PermanentCommandError("no_media");
      return {active, media:{...lastMedia}};
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

  async function closeManagedTabs(exceptId = null) {
    for (const [serviceId, entry] of Object.entries(managed())) {
      if (entry.tabId === exceptId) continue;
      const tab = await api.tabs.get(entry.tabId).catch(() => null);
      viewPolicy.forget(entry.tabId);
      if (tab) await api.tabs.remove(tab.id);
      delete managed()[serviceId];
    }
    await state.persist();
  }

  async function openService(serviceId, prepared) {
    let data = prepared?.service;
    if (!data) {
      const response = await fetcher(`${BASE}/api/services`);
      if (!response.ok) throw new Error("service list unavailable");
      data = (await response.json()).services.find(value => value.id === serviceId);
    }
    if (!data || data.id !== serviceId) throw new PermanentCommandError("unknown service");
    const presentation = await viewPolicy.prepare(data.view);
    let entry = managed()[serviceId];
    let tab = prepared?.tab || (entry ? await api.tabs.get(entry.tabId).catch(() => null) : null);
    const resetZoom = Boolean(entry?.view && presentation === undefined);
    await closeManagedTabs(tab?.id);
    const existing = Boolean(tab);
    if (!tab) {
      // Reserve ownership before MOBILE headers/first service navigation.
      tab = await api.tabs.create({url:presentation ? "about:blank" : data.url, active:!presentation});
      entry = managed()[serviceId] = {tabId:tab.id,windowId:tab.windowId};
    }
    entry.windowId = tab.windowId;
    if (presentation) entry.view = presentation;
    else delete entry.view;
    await state.persist();
    try {
      await viewPolicy.bind(tab, presentation);
      await viewPolicy.zoom(tab, resetZoom ? {mode:"desktop",zoom:100} : presentation);
      if (existing || presentation) tab = await api.tabs.update(tab.id, {url:data.url,active:true});
      if (presentation) viewReady = true;
    } catch (error) {
      if (presentation || resetZoom) viewReady = false;
      throw error;
    }
    await state.focus(tab);
  }

  async function execute(item, prepared) {
    const command = item.command;
    if (command === "open") return openService(item.service_id, prepared);
    if (command === "home") {
      await closeManagedTabs();
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
    if (command === "media") {
      const active = await state.activeTab();
      if (!state.owns(active) || active?.id !== prepared.active.id || active.url !== prepared.active.url ||
          Date.now() > item.deadline) throw new PermanentCommandError("no_media");
      const frames = await api.scripting.executeScript({
        target:{tabId:active.id, frameIds:[prepared.media.frameId]}, func:timingMedia,
        args:[item.action, item.media_id, item.position, item.deadline],
      });
      if (!frames.some(frame => frame.result?.media_id === item.media_id))
        throw new PermanentCommandError("no_media");
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
        if ((await api.tabs.get(active.id)).audible === true)
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
    const entry = Object.values(managed()).find(value => value.tabId === active.id);
    try {
      await viewPolicy.bind(active, entry?.view);
      await viewPolicy.zoom(active, entry?.view);
    } catch (_) { viewReady = false; }
    const response = await fetcher(`${BASE}/extension/audio-target`, {
      headers:{"X-AD-Linux-TV-Bridge":"ad-linux-tv-v1"},
    });
    if (!response.ok) throw new Error("audio target unavailable");
    const target = (await response.json()).volume;
    if (!Number.isInteger(target) || target < 0 || target > 100)
      throw new Error("invalid audio target");
    await api.scripting.executeScript({
      target:{tabId:active.id, allFrames:true}, func:pinVolume, args:[target],
    });
    const current = await state.activeTab();
    if (state.owns(current) && current?.id === active.id && current.url === active.url)
      await api.scripting.executeScript({target:{tabId:active.id}, func:mediaPulse});
  }

  async function mediaSnapshot() {
    const generation = ++snapshotRead;
    const deadline = Date.now() + 1000;
    const active = await state.activeTab();
    if (!state.owns(active) || !/^https?:\/\//i.test(active?.url || "")) { lastMedia = null; return null; }
    const frames = await api.scripting.executeScript({
      target:{tabId:active.id, allFrames:true}, func:timingMedia, args:["status"],
    });
    const current = await state.activeTab();
    if (generation !== snapshotRead || Date.now() > deadline) return null;
    if (!state.owns(current) || current?.id !== active.id || current.url !== active.url) {
      lastMedia = null; return null;
    }
    const found = frames.filter(frame => /^[0-9a-f]{32}$/.test(frame.result?.media_id || ""));
    const playing = found.filter(frame => frame.result.playing === true);
    const chosen = playing.length === 1 ? playing[0] : playing.length > 1 ? null :
      found.find(frame => frame.result.media_id === lastMedia?.media_id && active.id === lastMedia?.tabId) ||
      (found.length === 1 ? found[0] : null);
    if (!chosen || !Number.isInteger(chosen.frameId)) { lastMedia = null; return null; }
    lastMedia = {tabId:active.id, url:active.url, frameId:chosen.frameId, media_id:chosen.result.media_id};
    return chosen.result;
  }

  async function normalizeActiveMedia() {
    const active = await state.activeTab();
    if (active) await normalizeMedia(active.id);
  }

  async function onRemoved(tabId) {
    try { viewPolicy.forget(tabId); }
    finally { await state.onRemoved(tabId); }
  }
  return {restore, ensureLauncher:state.ensureLauncher, prepare, execute, openService,
    onRemoved, normalizeMedia, normalizeActiveMedia, mediaSnapshot, isOwned:state.owns,
    capabilities:() => ["html_media_v1", ...(viewReady && viewPolicy.supported() ? ["tab_view_v1"] : [])],
    getState:state.getState};
}

if (typeof module !== "undefined") module.exports = {createOwnedTabs, PermanentCommandError};
