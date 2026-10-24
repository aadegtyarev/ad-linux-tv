"use strict";
const ownedFactory = typeof module !== "undefined"
  ? require("./owned_tabs.js").createOwnedTabs : createOwnedTabs;
const ledgerFactory = typeof module !== "undefined"
  ? require("./command_ledger.js").createCommandLedger : createCommandLedger;
const PermanentError = typeof module !== "undefined"
  ? require("./owned_tabs.js").PermanentCommandError : PermanentCommandError;
const PREPARE_LIMIT = typeof module !== "undefined"
  ? require("./command_ledger.js").MAX_PREPARE_ATTEMPTS : MAX_PREPARE_ATTEMPTS;

function createTabController(api, fetcher = fetch) {
  const owned = ownedFactory(api, fetcher);
  const ledger = ledgerFactory(api.storage.session, api.storage.local);
  async function failed(id, reason) {
    try { return await ledger.fail(id, reason); }
    catch (_) { return {outcome:"uncertain", reason:"interrupted"}; }
  }

  async function run(item) {
    let decision;
    try { decision = await ledger.begin(item.id); }
    catch (_) { return {outcome:"failed", reason:"operation"}; }
    if (!decision.execute) return decision;
    let prepared;
    try { prepared = await owned.prepare(item); }
    catch (error) {
      if (error instanceof PermanentError)
        return failed(item.id, error.message === "no_media" ? "no_media" : "invalid_command");
      try { return await ledger.retry(item.id, "preparation"); }
      catch (_) { return {outcome:"failed", reason:"operation"}; }
    }
    try {
      await ledger.claim(item.id);
      const result = await owned.execute(item, prepared);
      if (result?.service_id) await owned.openService(result.service_id);
      return await ledger.complete(item.id, result?.volume);
    } catch (error) {
      return failed(item.id, error instanceof PermanentError && error.message === "no_media" ?
        "no_media" : "operation");
    }
  }
  async function restore() {
    await Promise.all([owned.restore(), ledger.restore()]);
  }

  const execute = run;
  return {
    restore,
    ensureLauncher:owned.ensureLauncher,
    execute,
    onRemoved:owned.onRemoved,
    getState:() => ({...owned.getState(), commands:ledger.getState(), maxPrepareAttempts:PREPARE_LIMIT}),
  };
}
if (typeof module !== "undefined") module.exports = {createTabController};
