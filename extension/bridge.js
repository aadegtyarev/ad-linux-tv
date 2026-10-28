"use strict";
const BRIDGE_BASE = "http://127.0.0.1:8765";
const BRIDGE = "X-AD-Linux-TV-Bridge";
const BRIDGE_VALUE = "ad-linux-tv-v1";

function createBridgeController(tabs, fetcher = fetch, logger = console) {
  let inFlight = null;
  let sequence = 0;
  async function reportMedia() {
    if (!tabs.mediaSnapshot) return; // Legacy/test controller compatibility.
    try {
      let timer;
      let media;
      try {
        media = await Promise.race([tabs.mediaSnapshot(), new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error("snapshot timeout")), 1000);
        })]);
      } finally { clearTimeout(timer); }
      sequence = Math.max(Date.now(), sequence + 1);
      await fetcher(`${BRIDGE_BASE}/extension/media`, {
        method:"POST", signal:AbortSignal.timeout(1500),
        headers:{[BRIDGE]:BRIDGE_VALUE, "Content-Type":"application/json"},
        body:JSON.stringify({protocol:1, sequence, sent_at:Date.now(),
          capabilities:tabs.capabilities ? tabs.capabilities() : ["html_media_v1"], media}),
      });
    } catch (_) { /* Optional capability unavailable: never block legacy commands. */ }
  }
  async function pollOnce() {
    await tabs.restore();
    await reportMedia();
    const headers = {[BRIDGE]: BRIDGE_VALUE};
    const response = await fetcher(`${BRIDGE_BASE}/extension/poll`, {headers, signal:AbortSignal.timeout(1500)});
    if (!response.ok) throw new Error("bridge poll rejected");
    for (const item of await response.json()) {
      try {
        const result = await tabs.execute(item);
        if (result.retry) return;
        const ack = await fetcher(`${BRIDGE_BASE}/extension/ack`, {
          method: "POST", signal:AbortSignal.timeout(1500), headers: {...headers, "Content-Type": "application/json"},
          body: JSON.stringify({id: item.id, outcome: result.outcome, reason: result.reason || null,
            ...(Number.isInteger(result.volume) ? {volume:result.volume} : {})}),
        });
        await reportMedia();
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
