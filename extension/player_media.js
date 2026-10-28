"use strict";

// Serialized, fixed code in the extension's isolated world of an owned service tab.
// No page URLs, titles, credentials, arbitrary selectors or script text leave this function.
async function playerMedia(action = "status", expected = null, position = null, deadline = null) {
  if (!["status", "play", "pause", "seek"].includes(action)) return null;
  const elements = [...document.querySelectorAll("audio,video")];
  if (elements.length > 64) return null;
  const registry = document.__adLinuxTvTiming ||= {items:new WeakMap(), last:null};
  const candidates = elements.filter(element => !element.ended &&
    typeof element.currentSrc === "string" && element.currentSrc.length <= 8192 &&
    Number.isFinite(element.duration) && element.duration > 0 && element.duration <= 86400 &&
    Number.isFinite(element.currentTime) && element.currentTime >= 0 && element.currentTime <= element.duration + 1);
  function identity(element) {
    const fingerprint = `${element.currentSrc}\n${element.duration}`;
    let record = registry.items.get(element);
    if (!record || record.fingerprint !== fingerprint) {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      record = {fingerprint, id:[...bytes].map(value => value.toString(16).padStart(2,"0")).join("")};
      registry.items.set(element, record);
    }
    return record.id;
  }
  const playing = candidates.filter(element => !element.paused);
  let element;
  if (action === "status") {
    if (playing.length === 1) element = playing[0];
    else if (playing.length > 1) return null;
    else if (candidates.includes(registry.last)) element = registry.last;
    else if (candidates.length === 1) element = candidates[0];
  } else {
    if (!/^[0-9a-f]{32}$/.test(expected || "") || !Number.isSafeInteger(deadline) ||
        Date.now() > deadline || deadline > Date.now() + 6000) return null;
    element = candidates.find(value => identity(value) === expected);
  }
  if (!element) return null;
  const id = identity(element);
  const ranges = element.seekable;
  const canSeek = Number.isInteger(ranges?.length) && ranges.length > 0 && ranges.length <= 16;
  if (action === "seek") {
    if (!Number.isInteger(position) || position < 0 || position > element.duration || !canSeek) return null;
    let allowed = false;
    for (let i = 0; i < ranges.length; i++) {
      if (Number.isFinite(ranges.start(i)) && Number.isFinite(ranges.end(i)) &&
          position >= ranges.start(i) && position <= ranges.end(i)) allowed = true;
    }
    if (!allowed) return null;
    element.currentTime = position;
  } else if (action === "play") await element.play();
  else if (action === "pause") element.pause();
  registry.last = element;
  return {media_id:id, playing:!element.paused && !element.ended,
    position:Math.min(Math.round(element.currentTime), Math.round(element.duration)),
    duration:Math.max(1, Math.round(element.duration)), can_seek:canSeek};
}

// Injected only into the currently owned tab. Visible service-page timers keep
// Firefox's event background responsive without scanning unmanaged tabs.
function pulseOwnedMedia() {
  if (document.__adLinuxTvMediaPulse) return;
  document.__adLinuxTvMediaPulse = true;
  const pulse = () => {
    if (!document.hidden) browser.runtime.sendMessage({type:"managed-media-pulse"}).catch(() => {});
  };
  pulse(); setInterval(pulse, 1000);
}

if (typeof module !== "undefined") module.exports = {playerMedia, pulseOwnedMedia};
