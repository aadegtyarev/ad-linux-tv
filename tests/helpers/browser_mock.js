"use strict";
const BASE = "http://127.0.0.1:8765";
const services = [
  {id:"one", url:"https://same.example/watch/one"},
  {id:"two", url:"https://same.example/watch/two"},
];

function browserMock(initial = []) {
  const tabs = new Map(initial.map(tab => [tab.id, {...tab}]));
  let nextId = Math.max(0, ...tabs.keys()) + 1;
  const calls = [];
  const storage = {};
  let activeId = initial.find(tab => tab.active)?.id ?? initial[0]?.id;
  const api = {
    storage: {local: {
      get: async key => ({[key]: storage[key]}),
      set: async value => Object.assign(storage, value),
    }},
    windows: {update: async (id, value) => calls.push(["window", id, value])},
    tabs: {
      query: async query => {
        if (query.url) return [...tabs.values()].filter(tab => tab.url.startsWith(BASE));
        if (query.active) return tabs.has(activeId) ? [tabs.get(activeId)] : [];
        return [...tabs.values()];
      },
      get: async id => {
        if (!tabs.has(id)) throw new Error("missing tab");
        return tabs.get(id);
      },
      create: async value => {
        const tab = {id:nextId++, windowId:1, ...value};
        tabs.set(tab.id, tab);
        if (value.active) activeId = tab.id;
        calls.push(["create", tab.id, value]);
        return tab;
      },
      update: async (id, value) => {
        const tab = Object.assign(tabs.get(id), value);
        if (value.active) activeId = id;
        calls.push(["update", id, value]);
        return tab;
      },
      remove: async id => { tabs.delete(id); calls.push(["remove", id]); },
      goBack: async id => calls.push(["back", id]),
      reload: async id => calls.push(["reload", id]),
      sendMessage: async (id, message) => calls.push(["message", id, message]),
    },
  };
  const fetcher = async (url, options = {}) => {
    calls.push(["fetch", url, options]);
    return {ok:true, json:async () => ({services})};
  };
  return {api, fetcher, tabs, calls, storage};
}

module.exports = {browserMock, services};
