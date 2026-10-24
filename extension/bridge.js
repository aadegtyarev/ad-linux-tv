"use strict";
const BRIDGE_BASE = "http://127.0.0.1:8765";
const BRIDGE = "X-AD-Linux-TV-Bridge";
const BRIDGE_VALUE = "ad-linux-tv-v1";

function createBridgeController(tabs, fetcher = fetch, logger = console) {
  let inFlight = null;
  async function pollOnce() {
    await tabs.restore();
    const headers = {[BRIDGE]: BRIDGE_VALUE};
    const response = await fetcher(`${BRIDGE_BASE}/extension/poll`, {headers});
    if (!response.ok) throw new Error("bridge poll rejected");
    for (const item of await response.json()) {
      try {
        const result = await tabs.execute(item);
        if (result.retry) return;
        const ack = await fetcher(`${BRIDGE_BASE}/extension/ack`, {
          method: "POST", headers: {...headers, "Content-Type": "application/json"},
          body: JSON.stringify({id: item.id, outcome: result.outcome, reason: result.reason || null}),
        });
        if (!ack.ok) {
          logger.error("Browser command acknowledgement failed; command remains queued.");
          return;
        }
      } catch (_) {
        logger.error("Browser command failed; command remains queued for retry.");
        return;
      }
    }
  }

  function wake() {
    if (inFlight) return inFlight;
    inFlight = pollOnce().catch(() => {}).finally(() => { inFlight = null; });
    return inFlight;
  }
  return {wake};
}

if (typeof module !== "undefined") module.exports = {createBridgeController, BRIDGE, BRIDGE_VALUE};
