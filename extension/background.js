const BASE = "http://127.0.0.1:8765";
let launcher = null;
const managedTabs = new Map();

async function services() {
  return (await (await fetch(`${BASE}/api/services`)).json()).services;
}

async function isServiceTab(tab) {
  if (!tab || !tab.url) return false;
  const origins = new Set((await services()).map(service => new URL(service.url).origin));
  return origins.has(new URL(tab.url).origin);
}

async function launcherTab() {
  if (launcher && await browser.tabs.get(launcher).catch(() => null)) return launcher;
  const existing = await browser.tabs.query({url: `${BASE}/*`});
  const tab = existing[0] || await browser.tabs.create({url: `${BASE}/`});
  launcher = tab.id;
  return launcher;
}

async function execute(item) {
  const active = (await browser.tabs.query({active: true, currentWindow: true}))[0];
  if (item.command === "open") {
    const service = (await services()).find(entry => entry.id === item.service_id);
    if (!service) return;
    const tabs = await browser.tabs.query({});
    let tab = tabs.find(candidate => managedTabs.get(candidate.id) === service.id);
    if (!tab) {
      tab = tabs.find(candidate => candidate.url &&
        new URL(candidate.url).origin === new URL(service.url).origin);
      if (tab) managedTabs.set(tab.id, service.id);
    }
    if (tab) await browser.tabs.update(tab.id, {active: true});
    else {
      tab = await browser.tabs.create({url: service.url, active: true});
      managedTabs.set(tab.id, service.id);
    }
    return;
  }
  if (item.command === "home") {
    if (active && await isServiceTab(active)) await browser.tabs.remove(active.id);
    await browser.tabs.update(await launcherTab(), {active: true});
  } else if (item.command === "back" && await isServiceTab(active)) {
    await browser.tabs.goBack(active.id).catch(() => {});
  } else if (item.command === "refresh" && await isServiceTab(active)) {
    await browser.tabs.reload(active.id);
  } else if (["up", "down", "left", "right", "ok"].includes(item.command)) {
    if (launcher) await browser.tabs.sendMessage(launcher, {command: item.command}).catch(() => {});
  }
}

async function poll() {
  try {
    const response = await fetch(`${BASE}/extension/poll`);
    for (const item of await response.json()) await execute(item);
    await fetch(`${BASE}/extension/heartbeat`);
  } catch (_) {}
}

browser.tabs.onRemoved.addListener(tabId => managedTabs.delete(tabId));
browser.runtime.onStartup.addListener(launcherTab);
browser.runtime.onInstalled.addListener(launcherTab);
setInterval(poll, 1000);
poll();
