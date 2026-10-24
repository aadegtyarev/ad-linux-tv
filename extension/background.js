"use strict";
const tabs = createTabController(browser);
const bridge = createBridgeController(tabs);

browser.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === "launcher-pulse" && sender.url === LAUNCHER) return bridge.wake();
});
browser.tabs.onRemoved.addListener(tabId => { void tabs.onRemoved(tabId); });
browser.tabs.onUpdated.addListener((tabId, change) => {
  if (change.status === "complete" || change.audible === true)
    void tabs.normalizeMedia(tabId).catch(() => {});
});
browser.tabs.onActivated.addListener(info => {
  void tabs.normalizeMedia(info.tabId).catch(() => {});
});
browser.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "bridge-poll") void bridge.wake();
});
browser.runtime.onStartup.addListener(() => { void tabs.ensureLauncher().catch(() => {}); });
browser.runtime.onInstalled.addListener(() => { void tabs.ensureLauncher().catch(() => {}); });
browser.alarms.create("bridge-poll", {periodInMinutes: 1});
void tabs.ensureLauncher().catch(() => {});
