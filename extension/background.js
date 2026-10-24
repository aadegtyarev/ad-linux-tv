const BASE = "http://127.0.0.1:8765";
let launcher = null;
async function services() { return (await (await fetch(`${BASE}/api/services`)).json()).services; }
async function launcherTab() { if (launcher && await browser.tabs.get(launcher).catch(() => null)) return launcher; const t = await browser.tabs.create({url: BASE}); launcher = t.id; return t.id; }
async function execute(item) {
  const active = (await browser.tabs.query({active:true,currentWindow:true}))[0];
  if (item.command === "open") { const service = (await services()).find(s=>s.id===item.service_id); if (!service) return; const managed = (await browser.tabs.query({})).find(t=>t.url===service.url); if (managed) await browser.tabs.update(managed.id,{active:true}); else await browser.tabs.create({url:service.url,active:true}); return; }
  if (item.command === "home") { const managed=(await services()).some(s=>active && active.url && new URL(active.url).origin===new URL(s.url).origin); if (managed) await browser.tabs.remove(active.id); await browser.tabs.update(await launcherTab(),{active:true}); }
  else if (item.command === "back" && active) await browser.tabs.goBack(active.id).catch(()=>{});
  else if (item.command === "refresh" && active) await browser.tabs.reload(active.id);
  else if (["up","down","left","right","ok"].includes(item.command)) { const tabs=await browser.tabs.query({}); const t=tabs.find(x=>x.id===launcher); if(t) await browser.tabs.sendMessage(t.id,{command:item.command}).catch(()=>{}); }
}
async function poll() { try { const r=await fetch(`${BASE}/extension/poll`); for(const item of await r.json()) await execute(item); await fetch(`${BASE}/extension/heartbeat`); } catch (_) {} }
browser.alarms.create("poll",{periodInMinutes:0.05});browser.alarms.onAlarm.addListener(poll);browser.runtime.onStartup.addListener(launcherTab);browser.runtime.onInstalled.addListener(launcherTab);poll();
