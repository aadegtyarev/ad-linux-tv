"use strict";
const BASE = "http://127.0.0.1:8765";
const LAUNCHER = `${BASE}/`;
function createTabController(api, fetcher = fetch) {
  let launcherId = null;
  let managed = {};
  let restorePromise = null;
  let launcherPromise = null;
  let savePromise = Promise.resolve();

  function persist() {
    const snapshot = Object.fromEntries(Object.entries(managed).map(([key, value]) => [key, {...value}]));
    savePromise = savePromise.then(() => api.storage.local.set({managedTabs: snapshot}));
    return savePromise;
  }
  async function findLauncher() {
    const tabs = await api.tabs.query({url: `${BASE}/*`});
    return tabs.find(tab => tab.url === LAUNCHER) || null;
  }
  async function restore() {
    if (restorePromise) return restorePromise;
    restorePromise = (async () => {
      const stored = await api.storage.local.get("managedTabs");
      managed = stored.managedTabs || {};
      for (const [serviceId, entry] of Object.entries(managed)) {
        try {
          const tab = await api.tabs.get(entry.tabId);
          entry.windowId = tab.windowId;
        } catch (_) {
          delete managed[serviceId];
        }
      }
      launcherId = (await findLauncher())?.id ?? null;
      await persist();
    })();
    return restorePromise;
  }
  function ensureLauncher() {
    if (launcherPromise) return launcherPromise;
    launcherPromise = (async () => {
      await restore();
      let tab = launcherId === null ? null : await api.tabs.get(launcherId).catch(() => null);
      if (!tab || tab.url !== LAUNCHER) tab = await findLauncher();
      if (!tab) tab = await api.tabs.create({url: LAUNCHER, active: true});
      launcherId = tab.id;
      return tab;
    })().finally(() => { launcherPromise = null; });
    return launcherPromise;
  }
  async function focus(tab) {
    await api.windows.update(tab.windowId, {focused: true});
    await api.tabs.update(tab.id, {active: true});
  }

  async function execute(item) {
    const active = (await api.tabs.query({active: true, lastFocusedWindow: true}))[0];
    if (item.command === "open") {
      const services = (await (await fetcher(`${BASE}/api/services`)).json()).services;
      const service = services.find(value => value.id === item.service_id);
      if (!service) throw new Error("unknown browser command");
      const entry = managed[service.id];
      let tab = entry ? await api.tabs.get(entry.tabId).catch(() => null) : null;
      if (tab) {
        entry.windowId = tab.windowId;
        tab = await api.tabs.update(tab.id, {url: service.url, active: true});
        await persist();
      }
      else {
        tab = await api.tabs.create({url: service.url, active: true});
        managed[service.id] = {tabId: tab.id, windowId: tab.windowId};
        await persist();
      }
      await focus(tab);
    } else if (item.command === "home") {
      if (active && Object.values(managed).some(entry => entry.tabId === active.id)) await api.tabs.remove(active.id);
      await focus(await ensureLauncher());
    } else if (item.command === "back" || item.command === "refresh") {
      if (!active || !Object.values(managed).some(entry => entry.tabId === active.id)) return;
      if (item.command === "back") await api.tabs.goBack(active.id);
      else await api.tabs.reload(active.id);
    } else if (["up", "down", "left", "right", "ok"].includes(item.command)) {
      const tab = await ensureLauncher();
      await focus(tab);
      await api.tabs.sendMessage(tab.id, {command: item.command});
    } else {
      throw new Error("unsupported browser command");
    }
  }

  async function onRemoved(tabId) {
    if (launcherId === tabId) launcherId = null;
    for (const [serviceId, entry] of Object.entries(managed)) {
      if (entry.tabId === tabId) delete managed[serviceId];
    }
    await persist();
  }

  return {restore, ensureLauncher, execute, onRemoved, getState: () => ({launcherId, managed})};
}
if (typeof module !== "undefined") module.exports = {createTabController, BASE, LAUNCHER};