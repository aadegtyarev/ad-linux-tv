"use strict";
const LIMIT = 256;
const MAX_PREPARE_ATTEMPTS = 3;
const TERMINAL = new Set(["completed", "failed", "uncertain"]);

function createCommandLedger(sessionStorage, durableStorage = sessionStorage) {
  let records = {};
  let restored = null;
  let writes = Promise.resolve();

  function save() {
    const copy = Object.fromEntries(Object.entries(records).map(([id, item]) => [id, {...item}]));
    writes = writes.catch(() => {}).then(async () => {
      await durableStorage.set({commandLedger: copy});
      if (durableStorage !== sessionStorage) await sessionStorage.set({commandLedger: copy});
    });
    return writes;
  }

  async function restore() {
    if (!restored) restored = Promise.all([
      sessionStorage.get("commandLedger"), durableStorage.get("commandLedger"),
    ]).then(([session, durable]) => {
      records = {...(session.commandLedger || {}), ...(durable.commandLedger || {})};
    }).catch(error => { restored = null; throw error; });
    return restored;
  }

  function room() {
    while (Object.keys(records).length >= LIMIT) {
      const oldest = Object.keys(records).find(id => TERMINAL.has(records[id].state));
      if (!oldest) throw new Error("command ledger is full");
      delete records[oldest];
    }
  }

  async function begin(id) {
    await restore();
    if (typeof id !== "string" || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
      return {outcome:"failed", reason:"invalid_id"};
    }
    const existing = records[id];
    if (existing?.state === "completed") return {outcome:"completed"};
    if (existing?.state === "failed" || existing?.state === "uncertain") {
      return {outcome:existing.state, reason:existing.reason};
    }
    if (existing?.state === "claimed") {
      existing.state = "uncertain";
      existing.reason = "interrupted";
      await save();
      return {outcome:"uncertain", reason:"interrupted"};
    }
    if (!existing) room();
    const attempts = (existing?.attempts || 0) + 1;
    records[id] = {state:"preparing", attempts};
    await save();
    return {execute:true, attempts};
  }

  async function claim(id) {
    records[id].state = "claimed";
    await save();
  }

  async function complete(id) {
    records[id].state = "completed";
    delete records[id].reason;
    await save();
    return {outcome:"completed"};
  }

  async function retry(id, reason) {
    const record = records[id];
    if (record.attempts >= MAX_PREPARE_ATTEMPTS) {
      record.state = "failed";
      record.reason = "retry_exhausted";
      await save();
      return {outcome:"failed", reason:"retry_exhausted"};
    }
    record.state = "retry";
    record.reason = reason;
    await save();
    return {retry:true};
  }

  async function fail(id, reason) {
    records[id].state = "failed";
    records[id].reason = reason;
    await save();
    return {outcome:"failed", reason};
  }

  return {restore, begin, claim, complete, retry, fail, getState:() => records, limit:LIMIT};
}
if (typeof module !== "undefined") module.exports = {createCommandLedger, LIMIT, MAX_PREPARE_ATTEMPTS};
