"use strict";

function validateView(raw) {
  if (raw === undefined) return undefined;
  if (!raw || typeof raw !== "object" || Array.isArray(raw) ||
      Object.keys(raw).some(key => !["mode","zoom"].includes(key)) ||
      !["desktop","mobile"].includes(raw.mode)) throw new Error("invalid view");
  const zoom = Object.hasOwn(raw,"zoom") ? raw.zoom : (raw.mode === "mobile" ? 200 : 100);
  if (!Number.isInteger(zoom) || zoom < 50 || zoom > 300) throw new Error("invalid zoom");
  return {mode:raw.mode,zoom};
}

function boundedView(operation, uncertain = false) {
  let timer;
  return Promise.race([operation, new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error("view operation timed out"); error.uncertain = uncertain; reject(error);
    }, 1500);
  })]).finally(() => clearTimeout(timer));
}

function createViewPolicy(api, isOwned) {
  const records = new Map();
  let agent = null;
  function supported() {
    return Boolean(api.webRequest?.onBeforeSendHeaders && api.tabs.getZoomSettings &&
      api.tabs.setZoom && api.runtime?.getBrowserInfo);
  }
  async function prepare(raw) {
    const view = validateView(raw);
    if (view && !supported()) throw new Error("view API unavailable");
    if (view?.mode === "mobile" && !agent) {
      const info = await boundedView(api.runtime.getBrowserInfo());
      const major = Number(String(info.version).split(".")[0]);
      if (!Number.isInteger(major) || major < 100 || major > 999) throw new Error("unsupported browser version");
      agent = `Mozilla/5.0 (Android 13; Mobile; rv:${major}.0) Gecko/${major}.0 Firefox/${major}.0`;
    }
    return view;
  }
  function forget(tabId) {
    const record = records.get(tabId);
    if (!record) return;
    record.enabled = false; // A failed native removal can never keep mutating headers.
    if (record.listener) api.webRequest.onBeforeSendHeaders.removeListener(record.listener);
    records.delete(tabId);
  }
  async function bind(tab, raw) {
    const view = await prepare(raw);
    if (!isOwned(tab)) throw new Error("unowned view target");
    const previous = records.get(tab.id);
    if (previous?.enabled && previous.windowId === tab.windowId &&
        previous.view.mode === view?.mode && previous.view.zoom === view?.zoom) return;
    forget(tab.id);
    if (!view) return;
    const record = {view, windowId:tab.windowId, enabled:true, listener:null};
    if (view.mode === "mobile") {
      record.listener = details => {
        if (!record.enabled || records.get(tab.id) !== record || details.tabId !== tab.id ||
            (details.windowId !== undefined && details.windowId !== tab.windowId) || !isOwned(tab)) return {};
        // Do not read header values other than our fixed replacement. All other
        // opaque entries (including authentication) pass through unchanged.
        const headers = details.requestHeaders;
        if (!Array.isArray(headers) || headers.length > 256) return {};
        let replaced = false;
        const result = headers.map(header => {
          if (header.name.toLowerCase() !== "user-agent") return header;
          replaced = true; return {name:header.name,value:agent};
        });
        if (!replaced) result.push({name:"User-Agent",value:agent});
        return {requestHeaders:result};
      };
      api.webRequest.onBeforeSendHeaders.addListener(record.listener,
        {urls:["http://*/*","https://*/*"],tabId:tab.id,windowId:tab.windowId},["blocking","requestHeaders"]);
    }
    records.set(tab.id,record);
  }
  async function zoom(tab, raw) {
    if (!isOwned(tab)) throw new Error("unowned zoom target");
    const view = validateView(raw);
    if (!view) return;
    const settings = await boundedView(api.tabs.getZoomSettings(tab.id));
    if (!isOwned(tab)) throw new Error("retired zoom target");
    if (settings?.mode !== "automatic" || settings?.scope !== "per-tab")
      throw new Error("unsupported zoom settings");
    await boundedView(api.tabs.setZoom(tab.id,view.zoom / 100), true);
  }
  function has(tabId) { return records.has(tabId); }
  return {prepare,bind,zoom,forget,has,supported};
}
if (typeof module !== "undefined") module.exports = {validateView,createViewPolicy};
