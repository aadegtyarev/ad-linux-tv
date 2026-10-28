"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const initial = {available:true,media_id:"a".repeat(32),title:"A long track name",playing:true,
  position:30,duration:120,can_play:true,can_pause:true,can_seek:true,
  can_next:false,can_previous:true};
const reply = (state, status = 200) => ({ok:status === 200,status,json:async () => ({...state})});
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise,resolve};
}
function fixture(handler) {
  class Element {
    constructor() {
      this.hidden = false;
      this.disabled = false;
      this.value = "0";
      this.innerHTML = "";
      this.listeners = {};
      this.classes = new Set();
      this.classList = {add:value => this.classes.add(value),remove:value => this.classes.delete(value)};
    }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    setAttribute(name, value) { this[name] = value; }
  }
  const ids = ["#media-panel", "#remote-face", "#media-title", "#media-elapsed",
    "#media-duration", "#media-position", "#media-previous", "#media-play", "#media-next", "#media-feedback"];
  const elements = Object.fromEntries(ids.map(id => [id,new Element()]));
  let state = {...initial}, now = 1000, auth = 0;
  const calls = [], feedbackTimers = new Map(); let timerId = 0;
  const context = {document:{querySelector:id => elements[id]},
    Date:class extends Date { static now() { return now; } },
    setInterval:() => 1,clearInterval:() => {},
    setTimeout:fn=>{const id=++timerId;feedbackTimers.set(id,fn);return id;},
    clearTimeout:id=>feedbackTimers.delete(id),
    request:async (method,path,body) => {
      const call = {method,path,body}; calls.push(call);
      if (handler) return handler(call, () => state);
      if (method === "POST") {
        if (body.action === "pause") state = {...state,playing:false};
        if (body.action === "play") state = {...state,playing:true};
        if (body.action === "seek") state = {...state,position:body.position};
      }
      return reply(state);
    },
    onAuth:() => { auth += 1; },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("src/ad_linux_tv/static/media_controls.js", "utf8"),context);
  const media = vm.runInContext("new PhoneMediaControls(request, onAuth)",context);
  return {media,elements,calls,setState:value => { state = {...value}; },
    setTime:value => { now = value; },auth:() => auth,
    expireFeedback:()=>{const jobs=[...feedbackTimers.values()];feedbackTimers.clear();jobs.forEach(fn=>fn());}};
}
test("media notice expires without being reopened by periodic snapshots", async () => {
  const f=fixture();await f.media.refresh();
  f.media.message="Плеер не подтвердил команду";f.media.render(initial);
  assert.equal(f.elements["#media-feedback"].textContent,"Плеер не подтвердил команду");
  f.expireFeedback();assert.equal(f.elements["#media-feedback"].textContent,"");
  await f.media.refresh();assert.equal(f.elements["#media-feedback"].textContent,"");
  f.media.stop();
});

test("resume retires a stuck GET and restores the active player without playback commands", async () => {
  const old = deferred(); let reads = 0;
  const f = fixture(call => { assert.equal(call.method,"GET"); return ++reads === 1 ? old.promise : reply(initial); });
  void f.media.refresh();
  f.media.reconcile(); await flush();
  assert.equal(f.elements["#media-panel"].hidden,false);
  old.resolve(reply({available:false})); await flush();
  assert.equal(f.elements["#media-panel"].hidden,false);
  assert.equal(f.media.state.media_id,initial.media_id);
  assert.equal(f.calls.length,2);
});

test("new page restores media snapshot after stop/start, with no player event or command", async () => {
  const f=fixture();f.media.start();await flush();f.media.stop();
  assert.equal(f.elements["#media-panel"].hidden,true);
  f.media.start();await flush();
  assert.equal(f.elements["#media-panel"].hidden,false);
  assert.ok(f.calls.every(call=>call.method==="GET"));
  f.media.stop();f.media.reconcile();assert.equal(f.calls.length,2);
});

const isPlay = element => /data-icon="play"/.test(element.innerHTML);

test("media follows Firefox capabilities and uses consistent vector controls", async () => {
  const f = fixture(), e = f.elements;
  await f.media.refresh();
  assert.equal(e["#media-panel"].hidden,false);
  assert.equal(e["#media-title"].textContent,initial.title);
  assert.equal(e["#media-next"].disabled,true);
  assert.equal(e["#media-previous"].disabled,false);
  assert.equal(e["#media-position"].value,30);
  assert.equal(e["#media-duration"].textContent,"2:00");
  e["#media-position"].value = "45";
  e["#media-position"].onchange(); await flush();
  assert.equal(f.calls.filter(c => c.method === "POST").at(-1).body.position,45);
  e["#media-play"].onclick(); await flush();
  const sent = f.calls.filter(c => c.method === "POST").at(-1).body;
  assert.equal(sent.action,"pause"); assert.equal(sent.media_id,initial.media_id);
  assert.equal(isPlay(e["#media-play"]),true);
  const html = fs.readFileSync("src/ad_linux_tv/static/remote.html","utf8");
  assert.match(html, /id="media-play"[^>]*><svg/);
  assert.doesNotMatch(html, /[⏸⏮⏭]/u);
  const css = fs.readFileSync("src/ad_linux_tv/static/style.css","utf8");
  assert.match(css, /@keyframes media-confirm-pulse/);
  assert.match(css, /prefers-reduced-motion:reduce/);
  f.setState({available:false}); await f.media.refresh();
  assert.equal(e["#media-panel"].hidden,true);
  assert.equal(e["#remote-face"].classes.has("has-media"),false);
});

test("seek retains target until fresh player observation, not POST receipt", async () => {
  const gate = deferred();
  const f = fixture(async (call,state) => call.method === "POST" ? gate.promise : reply(state()));
  await f.media.refresh();
  const slider = f.elements["#media-position"];
  slider.value = "50"; slider.oninput(); slider.onchange();
  assert.equal(slider.value,"50");
  gate.resolve(reply({...initial,position:50})); await flush();
  assert.equal(slider.value,"50");
  await f.media.refresh(); assert.equal(slider.value,"50");
  f.setState({...initial,position:50}); await f.media.refresh();
  assert.equal(slider.value,50);
  f.setState({...initial,position:51}); await f.media.refresh();
  assert.equal(slider.value,51);
});

test("pause gives immediate pending feedback and ignores rapid duplicate taps", async () => {
  const gate = deferred();
  const f = fixture(async (call,state) => call.method === "POST" ? gate.promise : reply(state()));
  await f.media.refresh();
  const job = f.media.command("pause");
  assert.equal(isPlay(f.elements["#media-play"]),true);
  assert.equal(f.elements["#media-play"].disabled,true);
  assert.equal(f.elements["#media-panel"]["aria-busy"],"true");
  assert.equal(f.elements["#media-play"]["data-pending"],"true");
  assert.match(f.elements["#media-feedback"].textContent,/Ожидаем/);
  await f.media.command("pause");
  assert.equal(f.calls.filter(c => c.method === "POST").length,1);
  gate.resolve(reply(initial)); await job; await flush(); // MPRIS still reports old status.
  assert.equal(isPlay(f.elements["#media-play"]),true);
  assert.equal(f.media.state.playing,true); // Provisional icon does not falsify observed state.
  f.setState({...initial,playing:false}); await f.media.refresh();
  assert.equal(f.elements["#media-panel"]["aria-busy"],"false");
  assert.equal(f.elements["#media-play"]["data-pending"],"false");
  assert.equal(f.elements["#media-play"].disabled,false);
});

test("unconfirmed playback expires visibly without resending the command", async () => {
  const f = fixture(async (_call,state) => reply(state()));
  await f.media.refresh(); await f.media.command("pause"); await flush();
  f.setTime(7000); await f.media.refresh();
  assert.match(f.elements["#media-feedback"].textContent,/не подтвердил/);
  assert.equal(isPlay(f.elements["#media-play"]),false);
  assert.equal(f.elements["#media-play"]["data-pending"],"false");
  assert.equal(f.calls.filter(c => c.method === "POST").length,1);
});

test("failed command reconciles read-only, never retries an uncertain action", async () => {
  const f = fixture(async (call,state) => {
    if (call.method === "POST") throw new Error("connection lost");
    return reply(state());
  });
  await f.media.refresh(); await f.media.command("pause"); await flush();
  assert.match(f.elements["#media-feedback"].textContent,/не подтверждена/);
  assert.equal(f.calls.filter(c => c.method === "POST").length,1);
});

test("old GET cannot overwrite newer pause result or block reconciliation", async () => {
  const old = deferred(); let getCount = 0;
  const f = fixture(async call => {
    if (call.method === "GET" && ++getCount === 1) return old.promise;
    return reply({...initial,playing:false});
  });
  f.media.render(initial);
  const polling = f.media.refresh();
  await f.media.command("pause"); await flush();
  old.resolve(reply(initial)); await polling;
  assert.equal(isPlay(f.elements["#media-play"]),true);
  assert.equal(f.media.state.playing,false);
});

test("stop fences late command and auth callbacks without restarting polling", async () => {
  const gate = deferred();
  const f = fixture(async (call,state) => call.method === "POST" ? gate.promise : reply(state()));
  await f.media.refresh(); const job = f.media.command("pause");
  f.media.stop(); const count = f.calls.length;
  gate.resolve(reply({},403)); await job; await flush();
  assert.equal(f.auth(),0); assert.equal(f.calls.length,count);
  assert.equal(f.elements["#media-panel"].hidden,true);
});

test("new lifecycle is not blocked by an old uncompleted command", async () => {
  const gate = deferred();
  const f = fixture(async (call,state) => call.method === "POST" ? gate.promise : reply(state()));
  await f.media.refresh(); const old = f.media.command("pause");
  f.media.stop(); f.media.start(); await flush();
  assert.equal(f.elements["#media-panel"].hidden,false);
  gate.resolve(reply({...initial,playing:false})); await old; await flush();
  assert.equal(f.media.state.playing,true);
  f.media.stop();
});

test("new media identity clears old desired state without applying it to new player", async () => {
  const f = fixture(async (_call,state) => reply(state()));
  await f.media.refresh(); await f.media.command("pause"); await flush();
  f.setState({...initial,media_id:"b".repeat(32),title:"Other player"});
  await f.media.refresh();
  assert.equal(f.media.pendingPlayback,null);
  assert.match(f.elements["#media-feedback"].textContent,/Источник/);
  assert.equal(isPlay(f.elements["#media-play"]),false);
  assert.equal(f.calls.filter(c => c.method === "POST").length,1);
});

test("missing identity cannot confirm an identity-bound pause or seek", async () => {
  for (const action of ["pause","seek"]) {
    const f=fixture(async (_call,state)=>reply(state()));
    await f.media.refresh();
    await f.media.command(action, action === "seek" ? 45 : undefined); await flush();
    const unidentified={...initial,playing:false,position:45}; delete unidentified.media_id;
    f.setState(unidentified); await f.media.refresh();
    assert.equal(f.media.pendingPlayback,null); assert.equal(f.media.pendingSeek,null);
    assert.match(f.elements["#media-feedback"].textContent,/Источник/);
    assert.equal(f.calls.filter(call=>call.method === "POST").length,1);
  }
});

test("overlapping polls coalesce; late decoded body after stop stays invisible", async () => {
  const decoded = deferred();
  const f = fixture(async () => ({ok:true,status:200,json:() => decoded.promise}));
  const first = f.media.refresh(); await flush();
  await f.media.refresh(); assert.equal(f.calls.length,1);
  f.media.stop(); decoded.resolve(initial); await first;
  assert.equal(f.elements["#media-panel"].hidden,true);
});
