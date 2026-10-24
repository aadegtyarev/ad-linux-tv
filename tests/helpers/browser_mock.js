"use strict";
const services = [
  {id:"one", url:"https://same.example/watch/one"},
  {id:"two", url:"https://same.example/watch/two"},
];

function browserMock(initial = []) {
  const tabs = new Map(initial.map(tab => [tab.id, {...tab}]));
  let nextId = Math.max(0, ...tabs.keys()) + 1;
  const calls = [];
  const local = {};
  const session = {};
  function area(data) {
    return {
      get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, data[key]])),
      set: async values => Object.assign(data, values),
    };
  }
  let activeId = initial.find(tab => tab.active)?.id ?? initial[0]?.id;
  let scriptingResults = [{result:75}];
  const api = {
    storage: {local:area(local), session:area(session)},
    scripting: {executeScript: async options => {
      calls.push(["script", options]);
      return scriptingResults;
    }},
    windows: {update: async (id, value) => calls.push(["window", id, value])},
    tabs: {
      query: async query => {
        if (query.url) {
          calls.push(["query", query]);
          const authority = query.url.split("://")[1].split("/")[0];
          if (authority.includes(":")) throw new Error("unsupported match-pattern port");
          return [...tabs.values()].filter(tab => tab.url.startsWith("http://127.0.0.1:"));
        }
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
      sendMessage: async (id, message) => {
        calls.push(["message", id, message]);
        return message.command === "ok" ? {service_id:"one"} : undefined;
      }
    },
  };
  const fetcher = async (url, options = {}) => {
    calls.push(["fetch", url, options]);
    return {ok:true, json:async () => ({services})};
  };
  return {api, fetcher, tabs, calls, storage:{local, session},
    setScriptingResults:value => { scriptingResults = value; }};
}

module.exports = {browserMock, services};
