"use strict";

// This function is serialized into the active service tab by scripting.executeScript.
function playerMediaVolume(mode, requested) {
  const media = [...document.querySelectorAll("audio,video")]
    .filter(element => !element.paused && !element.ended && !element.muted);
  if (!media.length) return null;
  if (mode === "set") {
    if (!Number.isInteger(requested) || requested < 0 || requested > 100) return null;
    for (const element of media) element.volume = requested / 100;
  }
  return Math.round(media[0].volume * 100);
}

if (typeof module !== "undefined") module.exports = {playerMediaVolume};
