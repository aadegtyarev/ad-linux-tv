"use strict";
const LAUNCHER = "http://127.0.0.1:8765/";
const URL_PATTERN = "http://127.0.0.1/*";

function createTabStorage(api) {
  let launcherId = null;
  let managed = {};
  let restorePromise = null;
  let launcherPromise = null;
  let savePromise = Promise.resolve();

  function persist() {
    const snapshot = Object.fromEntries(Object.entries(managed).map(([key, value]) => [key, {...value}]));
    savePromise = savePromise.then(() => api.storage.session.set({managedTabs: snapshot}));
    return savePromise;
  }

  async function findLauncher() {
    const tabs = await api.tabs.query({url: URL_PATTERN});
    return tabs.find(tab => tab.url === LAUNCHER) || null;
  }

  async function restore() {
    if (restorePromise) return restorePromise;
    restorePromise = (async () => {
      const saved = await api.storage.session.get("managedTabs");
      managed = saved.managedTabs || {};
      for (const [service, entry] of Object.entries(managed)) {
        try { entry.windowId = (await api.tabs.get(entry.tabId)).windowId; }
        catch (_) { delete managed[service]; }
      }
      launcherId = (await findLauncher())?.id ?? null;
      await persist();
    })().catch(error => { restorePromise = null; throw error; });
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
  async function activeTab() {
    return (await api.tabs.query({active: true, lastFocusedWindow: true}))[0] || null;
  }
  function owns(tab) {
    return Boolean(tab && Object.values(managed).some(entry => entry.tabId === tab.id));
  }
  async function onRemoved(tabId) {
    if (launcherId === tabId) launcherId = null;
    for (const [id, entry] of Object.entries(managed)) if (entry.tabId === tabId) delete managed[id];
    await persist();
  }
  return {restore, findLauncher, ensureLauncher, focus, activeTab, owns, onRemoved, persist,
    managed: () => managed, getState: () => ({launcherId, managed})};
}
if (typeof module !== "undefined") module.exports = {createTabStorage, LAUNCHER, URL_PATTERN};
